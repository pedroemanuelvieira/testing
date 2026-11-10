"""Testes do motor do escritório. Só biblioteca-padrão: python -m unittest discover -s testes -v

Usam uma base de dados temporária e o modo simulado: nenhum modelo é invocado e nada é escrito no repositório.
"""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
_TMP = tempfile.mkdtemp(prefix="foundry_teste_")
os.environ["FOUNDRY_BD"] = os.path.join(_TMP, "teste.db")
os.environ["FOUNDRY_MOTOR"] = "simulado"
os.environ["FOUNDRY_SIMULADO_ATRASO"] = "0"

from foundry import config, cron, db, runner, server  # noqa: E402
from foundry.tools import comum, drift, fronteira, kpis, perfil, refresh, tmdl  # noqa: E402

EX = RAIZ / "exemplos"


class Cron(unittest.TestCase):
    def test_dias_uteis(self):
        self.assertTrue(cron.coincide("30 8 * * 1-5", datetime(2026, 11, 10, 8, 30)))    # terça
        self.assertFalse(cron.coincide("30 8 * * 1-5", datetime(2026, 11, 14, 8, 30)))   # sábado
        self.assertFalse(cron.coincide("30 8 * * 1-5", datetime(2026, 11, 10, 8, 31)))

    def test_domingo_0_e_7(self):
        domingo = datetime(2026, 11, 15, 9, 0)
        self.assertTrue(cron.coincide("0 9 * * 0", domingo))
        self.assertTrue(cron.coincide("0 9 * * 7", domingo))

    def test_dia_do_mes_ou_dia_da_semana(self):
        self.assertTrue(cron.coincide("0 9 1 * 1", datetime(2026, 11, 2, 9, 0)))   # segunda, não é dia 1
        self.assertTrue(cron.coincide("0 9 1 * 1", datetime(2026, 11, 1, 9, 0)))   # dia 1, domingo
        self.assertFalse(cron.coincide("0 9 1 * 1", datetime(2026, 11, 3, 9, 0)))

    def test_proxima_salta_o_fim_de_semana(self):
        sexta = datetime(2026, 11, 13, 18, 0)
        self.assertEqual(cron.proxima("30 8 * * 1-5", sexta), datetime(2026, 11, 16, 8, 30))
        self.assertEqual(cron.proxima("4 9,12,15,17 * * 1-5", datetime(2026, 11, 10, 12, 4)), datetime(2026, 11, 10, 15, 4))

    def test_passos_listas_e_erros(self):
        self.assertEqual(cron.analisar("*/15 8-10 * * *")[0], {0, 15, 30, 45})
        for mau in ("60 8 * * *", "0 8 * *", "a b c d e", "0 8 32 * *", "*/0 * * * *"):
            with self.assertRaises(ValueError):
                cron.analisar(mau)

    def test_descricao(self):
        self.assertEqual(cron.descrever("30 8 * * 1-5"), "dias úteis · 08:30")
        self.assertIn("seg", cron.descrever("21 9 * * 1"))

    def test_todas_as_rotinas_tem_proxima_execucao(self):
        for r in config.rotinas():
            if r.get("cron"):
                self.assertIsNotNone(cron.proxima(r["cron"], datetime(2026, 11, 10, 12, 0)), r["id"])


class Configuracao(unittest.TestCase):
    def test_arquitetura_coerente(self):
        self.assertEqual(config.validar(), [])

    def test_doze_funcionarios_e_dez_modulos(self):
        eq = config.equipa()
        self.assertEqual(len(eq["agentes"]), 12)
        self.assertEqual(sum(a["tipo"] == "orquestrador" for a in eq["agentes"]), 1)
        self.assertEqual([p["numero"] for p in eq["projetos_ml"]], [str(n) for n in range(910, 920)])

    def test_skills_com_frontmatter_valido(self):
        for f in sorted((RAIZ / ".claude" / "skills").glob("*/SKILL.md")):
            linhas = f.read_text(encoding="utf-8").splitlines()
            self.assertEqual(linhas[0], "---", f)
            self.assertEqual(linhas[1], f"name: {f.parent.name}", f)
            self.assertTrue(linhas[2].startswith('description: "') and linhas[2].endswith('"'), f)
            self.assertLessEqual(len(linhas[2]), 1024 + 16, f)

    def test_agentes_com_frontmatter_valido(self):
        for f in sorted((RAIZ / ".claude" / "agents").glob("*.md")):
            linhas = f.read_text(encoding="utf-8").splitlines()
            self.assertEqual(linhas[1], f"name: {f.stem}", f)
            self.assertIsNotNone(config.agente(f.stem), f"{f.stem} sem entrada em equipa.json")

    def test_nenhum_funcionario_declarado_acima_de_configurado_sem_evidencia(self):
        for a in config.equipa()["agentes"]:
            if a["estado"] in ("instalado", "verificado", "producao"):
                self.assertTrue(a["evidencia"].strip(), f"{a['id']}: estado {a['estado']} sem evidência")


class Executor(unittest.TestCase):
    def test_interpreta_estado_e_resumo(self):
        self.assertEqual(runner.interpretar("texto\nESTADO: avisos\nRESUMO: 2 falhas em 41", False), ("avisos", "2 falhas em 41"))
        self.assertEqual(runner.interpretar("**ESTADO:** ok\n**RESUMO:** tudo bem", False)[0], "ok")

    def test_erro_do_cli_prevalece(self):
        self.assertEqual(runner.interpretar("ESTADO: ok\nRESUMO: x", True)[0], "falhou")

    def test_sem_linha_de_estado_nao_e_sucesso(self):
        estado, resumo = runner.interpretar("fiz umas coisas", False)
        self.assertEqual(estado, "avisos")
        self.assertIn("ESTADO", resumo)

    def test_rotina_sem_entradas_e_ignorada_sem_invocar(self):
        with tempfile.TemporaryDirectory() as d:
            antigo, config.RAIZ = config.RAIZ, Path(d)
            try:
                self.assertIn("sem entradas", runner.entradas_em_falta({"requer": ["inbox/pedidos/*"]}))
                (Path(d) / "inbox" / "pedidos").mkdir(parents=True)
                (Path(d) / "inbox" / "pedidos" / ".gitkeep").write_text("")
                self.assertIsNotNone(runner.entradas_em_falta({"requer": ["inbox/pedidos/*"]}), ".gitkeep não conta como entrada")
                (Path(d) / "inbox" / "pedidos" / "p.md").write_text("x")
                self.assertIsNone(runner.entradas_em_falta({"requer": ["inbox/pedidos/*"]}))
            finally:
                config.RAIZ = antigo

    def test_execucao_simulada_fica_registada_e_identificada(self):
        e = runner.executar("benkei", pedido="revê a medida X", origem="teste")
        self.assertEqual(e["estado"], "ok")
        self.assertIn("SIMULAÇÃO", e["saida"])
        self.assertEqual(e["agente"], "benkei")

    def test_pedidos_invalidos(self):
        for args in (("ninguem", None, "x"), ("benkei", None, ""), ("benkei", "rotina-que-nao-existe", None)):
            with self.assertRaises(ValueError):
                runner.executar(args[0], args[1], args[2])

    def test_prompt_inclui_rotina_e_rodape(self):
        p = runner.montar_prompt(config.agente("tsukuyomi"), config.rotina("triagem"), None, "agenda")
        self.assertIn("triagem-pedidos", p)
        self.assertIn("ESTADO: ok | avisos | falhou", p)

    def test_sem_cli_falha_em_vez_de_simular(self):
        antigo = dict(os.environ)
        os.environ["FOUNDRY_MOTOR"] = "claude"
        os.environ["FOUNDRY_CLAUDE"] = ""
        os.environ["PATH"] = ""
        try:
            r = runner._chamar_claude(config.agente("benkei"), "x", 5)
        finally:
            os.environ.clear()
            os.environ.update(antigo)
        self.assertTrue(r["erro"])
        self.assertIn("não encontrado", r["texto"])


class Escalonador(unittest.TestCase):
    def setUp(self):
        self._rot = config.rotinas
        con = db.ligar()
        con.execute("DELETE FROM meta")
        con.commit()
        con.close()

    def tearDown(self):
        config.rotinas = self._rot

    def test_dispara_uma_vez_por_horario(self):
        config.rotinas = lambda: [{"id": "r1", "agente": "kioku", "cron": "30 8 * * *"}]
        agora, inst = datetime(2026, 11, 10, 8, 30, 5), datetime(2026, 11, 1)
        self.assertEqual([r["id"] for r in server.devidas(agora, agora - timedelta(seconds=20), inst)], ["r1"])
        self.assertEqual(server.devidas(agora + timedelta(seconds=20), agora, inst), [])

    def test_maquina_desligada_nao_repete_sem_recuperar(self):
        config.rotinas = lambda: [{"id": "r2", "agente": "kioku", "cron": "30 8 * * *"}]
        agora = datetime(2026, 11, 10, 11, 0)
        self.assertEqual(server.devidas(agora, agora - timedelta(hours=5), datetime(2026, 11, 1)), [])

    def test_recupera_uma_vez_dentro_da_janela(self):
        config.rotinas = lambda: [{"id": "r3", "agente": "kioku", "cron": "30 8 * * *", "recuperar_h": 3}]
        inst = datetime(2026, 11, 1)
        agora = datetime(2026, 11, 10, 10, 0)
        self.assertEqual(len(server.devidas(agora, agora - timedelta(hours=5), inst)), 1)
        self.assertEqual(server.devidas(agora + timedelta(minutes=1), agora, inst), [])
        self.assertEqual(server.devidas(datetime(2026, 11, 11, 12, 0), datetime(2026, 11, 11, 6, 0), inst), [], "fora da janela de 3 h")

    def test_nao_recupera_antes_da_instalacao(self):
        config.rotinas = lambda: [{"id": "r4", "agente": "kioku", "cron": "30 8 * * *", "recuperar_h": 6}]
        agora = datetime(2026, 11, 10, 10, 0)
        self.assertEqual(server.devidas(agora, agora, datetime(2026, 11, 10, 9, 59)), [])

    def test_rotina_desligada_ou_a_pedido_nao_dispara(self):
        config.rotinas = lambda: [{"id": "r5", "agente": "kioku", "cron": "30 8 * * *", "ativa": False},
                                  {"id": "r6", "agente": "kioku", "cron": None}]
        agora = datetime(2026, 11, 10, 8, 30, 5)
        self.assertEqual(server.devidas(agora, agora - timedelta(seconds=20), datetime(2026, 11, 1)), [])


class Quadro(unittest.TestCase):
    def test_foco_limitado_a_tres(self):
        ids = [db.tarefa_criar(f"tarefa {i}", "kenshin") for i in range(4)]
        for i in ids[:3]:
            db.tarefa_atualizar(i, foco=1)
        with self.assertRaises(ValueError):
            db.tarefa_atualizar(ids[3], foco=1)
        for i in ids:
            db.tarefa_atualizar(i, estado="arquivada")

    def test_valores_invalidos(self):
        with self.assertRaises(ValueError):
            db.tarefa_criar("x", fase="inexistente")
        tid = db.tarefa_criar("y")
        with self.assertRaises(ValueError):
            db.tarefa_atualizar(tid, estado="apagada")
        db.tarefa_atualizar(tid, estado="arquivada")
        self.assertNotIn(tid, [t["id"] for t in db.tarefas()])
        self.assertIn(tid, [t["id"] for t in db.tarefas(incluir_arquivadas=True)], "arquivar não apaga")


class Ferramentas(unittest.TestCase):
    def test_perfil_chave_frescura_e_decimal_portugues(self):
        r = perfil.perfilar(str(EX / "dados" / "vendas_semanais.csv"), ["semana", "regiao", "categoria"], "semana", 7, hoje=date(2026, 11, 20))
        self.assertEqual((r["linhas"], r["colunas"], r["duplicadas"]), (936, 5, 0))
        self.assertTrue(r["chave"]["unica"])
        self.assertEqual(r["frescura"]["dias_de_atraso"], 18)
        self.assertEqual(r["estado"], "avisos")
        receita = next(c for c in r["detalhe_colunas"] if c["coluna"] == "receita")
        self.assertEqual(receita["tipo"], "decimal")
        self.assertGreater(receita["minimo"], 100)

    def test_perfil_deteta_duplicados_nulos_e_chave_repetida(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.csv"
            f.write_text("id,valor,estado\n1,10,A\n1,10,A\n2,,a\n3,abc,B\n4,5,B\n", encoding="utf-8")
            r = perfil.perfilar(str(f), ["id"])
            self.assertEqual(r["duplicadas"], 1)
            self.assertFalse(r["chave"]["unica"])
            self.assertTrue(any("maiúsculas" in a for a in r["avisos"]))
            with self.assertRaises(ValueError):
                perfil.perfilar(str(f), ["nao_existe"])

    def test_numeros_e_datas(self):
        self.assertEqual(comum.num("1.234,56", ","), 1234.56)
        self.assertEqual(comum.num("1,234.56", "."), 1234.56)
        self.assertIsNone(comum.num("n/a"))
        self.assertEqual(comum.data("03/04/2026"), date(2026, 4, 3))
        self.assertEqual(comum.data("2026-04-03T10:00:00"), date(2026, 4, 3))
        self.assertEqual(comum.z_robusto([5, 5, 5, 5, 5, 5]), [None] * 6, "série constante não gera anomalias")

    def test_kpis_periodo_completo_e_contributos(self):
        r = kpis.comparar(str(EX / "dados" / "vendas_semanais.csv"), "semana", ["receita"], ["regiao"])
        self.assertEqual((r["atual"], r["anterior"], r["homologo"]), ("2026-11-02", "2026-10-26", "2025-11-03"))
        m = r["metricas"][0]
        self.assertLess(m["vs_anterior"]["pct"], 0)
        self.assertEqual(m["contributos"]["regiao"][0]["valor"], "Norte", "a quebra plantada no Norte é o maior contributo")
        soma = sum(c["contributo"] for c in m["contributos"]["regiao"])
        self.assertAlmostEqual(soma, m["vs_anterior"]["abs"], delta=0.05)

    def test_kpis_exclui_periodo_aberto(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "d.csv"
            linhas = ["dia,v"] + [f"{date(2026, 10, 1) + timedelta(days=i)},10" for i in range(36)]   # até 5 de novembro
            f.write_text("\n".join(linhas), encoding="utf-8")
            r = kpis.comparar(str(f), "dia", ["v"], [], "mes")
            self.assertEqual(r["atual"], "2026-10-01", "novembro está aberto e não entra")
            self.assertIsNone(r["metricas"][0]["vs_anterior"]["pct"], "sem base não há percentagem")

    def test_anomalia_plantada_e_encontrada(self):
        r = drift.anomalias(str(EX / "dados" / "vendas_semanais.csv"), "semana", "receita", "regiao")
        self.assertEqual([(a["grupo"], a["data"]) for a in r["achados"]], [("Norte", "2026-11-02")])
        self.assertLess(r["achados"][0]["desvio_pct"], -40)

    def test_serie_curta_nao_e_avaliada(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "c.csv"
            f.write_text("d,v\n" + "\n".join(f"2026-01-{i:02d},{i * 100}" for i in range(1, 10)), encoding="utf-8")
            r = drift.anomalias(str(f), "d", "v")
            self.assertEqual((r["anomalias"], r["nao_avaliadas"]), (0, ["total"]))

    def test_psi_deteta_deriva_e_categoria_nova(self):
        r = drift.psi(str(EX / "dados" / "referencia.csv"), str(EX / "dados" / "atual.csv"))
        por = {c["coluna"]: c for c in r["colunas"]}
        self.assertEqual(por["ticket"]["nivel"], "deriva")
        self.assertEqual(por["canal"]["categorias_novas"], ["App"])
        self.assertEqual(por["regiao"]["nivel"], "estavel")
        igual = drift.psi(str(EX / "dados" / "referencia.csv"), str(EX / "dados" / "referencia.csv"))
        self.assertTrue(all(c["psi"] == 0 for c in igual["colunas"]))

    def test_refresh_falhas_repetidas_atrasos_e_lentidao(self):
        r = refresh.analisar(str(EX / "refresh" / "refresh_log.csv"), agora=datetime(2026, 11, 9, 9, 0))
        self.assertEqual(r["estado"], "falhou")
        self.assertEqual(r["falhas_repetidas"], ["Modelo Stocks"])
        self.assertEqual({a["objeto"] for a in r["atrasados"]}, {"Modelo Stocks", "Pipeline Objetivos"})
        self.assertEqual([s["objeto"] for s in r["lentos"]], ["Modelo Financeiro"])

    def test_refresh_exige_colunas(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "r.csv"
            f.write_text("a,b\n1,2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                refresh.analisar(str(f))

    def test_tmdl_leitura_do_modelo(self):
        m = tmdl.ler_modelo(str(EX / "modelo_exemplo"))
        self.assertEqual(set(m["tabelas"]), {"Vendas", "Clientes", "Produtos", "Calendario", "Objetivos"})
        medidas = {x["nome"]: x for x in m["tabelas"]["Vendas"]["medidas"]}
        self.assertEqual(len(medidas), 8)
        self.assertIn("SAMEPERIODLASTYEAR", medidas["Receita Ano Anterior"]["expr"], "expressão em várias linhas")
        self.assertEqual(medidas["Receita Ano Anterior"]["props"]["formatString"], "#,0.00 €")
        self.assertEqual(medidas["Receita"]["descricao"], "Receita líquida sem imposto, em EUR.")
        self.assertEqual(len(m["relacoes"]), 3)
        self.assertEqual({p["nome"] for p in m["papeis"]}, {"Comercial", "Regiao Norte", "Direcao"})

    def test_tmdl_lint_encontra_os_problemas_plantados(self):
        r = tmdl.lint(str(EX / "modelo_exemplo"))
        regras = {(a["regra"], a["objeto"]) for a in r["achados"]}
        for esperado in [("M07", "Vendas[Receita vs Objetivo]"), ("M03", "Vendas[Margem %]"), ("M04", "Vendas[Ticket Médio]"),
                         ("M05", "Vendas[Receita Online]"), ("M01", "Vendas[Receita Online]"), ("C01", "Vendas[DocumentoId]"),
                         ("C02", "Vendas[ClienteId]"), ("C03", "Vendas[MargemLinha]"), ("T02", "Objetivos"), ("S01", "papel Direcao")]:
            self.assertIn(esperado, regras)
        self.assertTrue(any(a["regra"] == "R01" for a in r["achados"]))
        self.assertEqual((r["erros"], r["estado"]), (1, "falhou"))
        self.assertNotIn(("M03", "Vendas[Receita]"), regras, "medida correta não é assinalada")
        self.assertNotIn(("M07", "Vendas[Receita Ano Anterior]"), regras)

    def test_tmdl_divisao_por_constante_e_comentarios_nao_disparam(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "t.tmdl").write_text(
                "table T\n\n\t/// ok\n\tmeasure A = SUM(T[V]) / 100 // a / b em comentário\n\t\tformatString: 0\n\n"
                "\t/// ok\n\tmeasure B = DIVIDE([A], 2) & \"a/b\"\n\t\tformatString: 0\n\n\tcolumn V\n\t\tdataType: decimal\n", encoding="utf-8")
            self.assertEqual([a["regra"] for a in tmdl.lint(d)["achados"] if a["regra"] == "M03"], [])

    def test_tmdl_rls_propaga_por_relacao(self):
        r, md = tmdl.rls(str(EX / "modelo_exemplo"))
        mat = {(x["papel"], x["tabela"]): x["protecao"] for x in r["matriz"]}
        self.assertEqual(mat[("Comercial", "Clientes")], "filtro direto")
        self.assertEqual(mat[("Comercial", "Vendas")], "por relação")
        self.assertEqual(mat[("Comercial", "Produtos")], "por relação", "a relação bidirecional propaga de Vendas para Produtos")
        self.assertEqual(mat[("Comercial", "Objetivos")], "sem filtro")
        self.assertEqual(mat[("Direcao", "Vendas")], "sem filtro")
        self.assertIn("Passou?", md)
        self.assertNotIn("validado", r["estado"])

    def test_tmdl_dicionario_com_dependencias(self):
        r, md = tmdl.doc(str(EX / "modelo_exemplo"))
        margem = next(x for x in r["dicionario_medidas"] if x["medida"] == "Margem %")
        self.assertEqual(margem["depende_de_medidas"], ["Custo", "Receita"])
        self.assertEqual(r["medidas_sem_descricao"], 6)
        self.assertIn("```mermaid", md)

    def test_tmdl_pasta_sem_modelo(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            tmdl.ler_modelo(d)

    def test_fronteira_deteta_e_mascara(self):
        texto = ("contacto: maria.silva@empresa-real.pt\nNIF 501442600\nIBAN PT50000201231234567890154\n"
                 "password = SuperSecreta123\ntelefone 912 345 678\nexemplo: alguem@example.com e <EMAIL_COMERCIAL>\nvalor 123456780\n")
        ach = fronteira.verificar_texto(texto)
        tipos = {a["tipo"] for a in ach}
        self.assertEqual(tipos, {"email", "nif", "iban", "credencial", "telefone"})
        self.assertEqual(sum(a["tipo"] == "email" for a in ach), 1, "endereços de exemplo e marcadores não contam")
        self.assertEqual(sum(a["tipo"] == "nif" for a in ach), 1, "9 dígitos sem dígito de controlo válido não são NIF")
        for a in ach:
            self.assertLessEqual(len(a["amostra"]), 5, "o valor nunca é repetido por inteiro")

    def test_o_que_a_equipa_partilha_esta_limpo(self):
        r = fronteira.verificar(["cerebro", "escritorio", ".claude", "README.md", "CLAUDE.md"])
        self.assertEqual(r["achados"], 0, r["avisos"])


class Servidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.Pedido.token, server.Pedido.com_agenda = None, False
        threading.Thread(target=server._operario, daemon=True).start()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Pedido)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def pedir(self, caminho, corpo=None, cabecalhos=None):
        req = urllib.request.Request(self.base + caminho, data=json.dumps(corpo).encode() if corpo is not None else None,
                                     headers={"Content-Type": "application/json", **(cabecalhos or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_interface_e_estado(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as r:
            html = r.read().decode()
        for ident in ("stats", "seg", "agent-select", "btn-run-agent", "output-area", "board", "bpboard", "numview", "pane", "dock", "palInput"):
            self.assertIn(f'id="{ident}"', html)
        cod, s = self.pedir("/api/estado")
        self.assertEqual(cod, 200)
        self.assertEqual((len(s["agentes"]), len(s["projetos_ml"]), s["erros_config"]), (12, 10, []))
        self.assertEqual(s["motor"]["modo"], "simulado")

    def test_correr_rotina_ate_ao_fim(self):
        cod, r = self.pedir("/api/run-agent", {"rotina": "morning-audit"})
        self.assertEqual((cod, r["status"]), (200, "started"))
        server._fila.join()
        cod, e = self.pedir(f"/api/execucao?id={r['id']}")
        self.assertEqual((e["estado"], e["agente"], e["rotina"]), ("ok", "tomoshibi", "morning-audit"))
        _, s = self.pedir("/api/estado")
        self.assertEqual(next(x for x in s["rotinas"] if x["id"] == "morning-audit")["ultima"]["estado"], "ok")
        self.assertTrue(any(v["agente"] == "tomoshibi" for v in s["eventos"]))

    def test_pedidos_invalidos_devolvem_400(self):
        for corpo in ({"agent_id": "benkei"}, {"agent_id": "fantasma", "pedido": "x"}, {"rotina": "nao-existe"}):
            self.assertEqual(self.pedir("/api/run-agent", corpo)[0], 400)
        self.assertEqual(self.pedir("/api/tarefa", {"acao": "criar", "titulo": "  "})[0], 400)
        self.assertEqual(self.pedir("/api/rotina", {"id": "nao-existe", "ativa": False})[0], 400)

    def test_origem_alheia_e_recusada(self):
        cod, _ = self.pedir("/api/run-agent", {"rotina": "morning-audit"}, {"Origin": "http://pagina-maliciosa.example"})
        self.assertEqual(cod, 403)
        cod, _ = self.pedir("/api/run-agent", {"rotina": "morning-audit"}, {"Host": "atacante.example"})
        self.assertEqual(cod, 403, "protege contra DNS rebinding")

    def test_ficheiros_so_de_out(self):
        for caminho in ("../CLAUDE.md", "CLAUDE.md", "out/../escritorio/equipa.json", "/etc/passwd"):
            self.assertEqual(self.pedir("/api/ficheiro?caminho=" + caminho)[0], 404, caminho)

    def test_tarefas_e_interruptores(self):
        cod, r = self.pedir("/api/tarefa", {"acao": "criar", "titulo": "Rever medida de margem", "agente": "benkei", "fase": "transformacao"})
        self.assertEqual(cod, 200)
        self.assertEqual(self.pedir("/api/tarefa", {"id": r["id"], "estado": "bloqueada"})[0], 200)
        _, s = self.pedir("/api/estado")
        self.assertEqual(next(t for t in s["tarefas"] if t["id"] == r["id"])["estado"], "bloqueada")
        self.pedir("/api/tarefa", {"id": r["id"], "estado": "arquivada"})
        self.assertEqual(self.pedir("/api/rotina", {"id": "triagem", "ativa": False})[0], 200)
        _, s = self.pedir("/api/estado")
        self.assertFalse(next(x for x in s["rotinas"] if x["id"] == "triagem")["ativa"])
        self.pedir("/api/rotina", {"id": "triagem", "ativa": True})

    def test_token_obrigatorio_quando_definido(self):
        server.Pedido.token = "segredo"
        try:
            self.assertEqual(self.pedir("/api/estado")[0], 401)
            self.assertEqual(self.pedir("/api/estado", cabecalhos={"X-Foundry-Token": "segredo"})[0], 200)
        finally:
            server.Pedido.token = None


if __name__ == "__main__":
    unittest.main(verbosity=2)
