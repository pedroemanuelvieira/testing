# Neo-Edo Data Foundry · escritório de IA para a equipa de BI e ML

Um escritório com doze funcionários de IA que complementam o trabalho da equipa: triam pedidos, vigiam refreshes e dados, reveem modelos Power BI, documentam, analisam KPIs e correm os módulos de ML. Funciona sobre o Claude Code, com as contas Claude da equipa, sem chaves de API.

Três peças, todas neste repositório:

- **A equipa** (`CLAUDE.md`, `.claude/agents/`, `.claude/skills/`): uma orquestradora, onze funcionários e 32 skills.
- **O motor local** (`foundry/`): interface web, escalonador de rotinas, registo em SQLite e ferramentas determinísticas. Só Python, sem dependências.
- **O cérebro partilhado** (`cerebro/`): regras da casa, glossário de métricas, fontes vigiadas, decisões e lições, versionados em git.

Nada é publicado nem enviado: todo o trabalho fica em `out/` à espera de uma pessoa.

## Começar

Precisas do [Claude Code](https://claude.com/claude-code) com sessão iniciada e de Python 3.10 ou superior.

```bash
git clone <este repositório>
cd <pasta>
python -m foundry preparar      # ou: bash setup.sh
python -m foundry demo          # opcional: copia dados fictícios para inbox/
python -m foundry servir        # abre http://localhost:8765
```

Para experimentar sem gastar utilização do Claude: `python -m foundry servir --simulado`.

O motor ML precisa de mais quatro pacotes: `python -m pip install -r motor_ml/requirements.txt`.

## Três formas de usar

**1. Conversa.** Abre o Claude Code nesta pasta (`claude`, a aplicação ou claude.ai/code) e escreve o que precisas. A Amaterasu escolhe o funcionário.

- "morning"
- "Há pedidos novos em inbox, faz a triagem."
- "Revê o modelo em inbox/modelos/vendas e diz-me se posso publicar."
- "O refresh falhou esta noite, o que se passa?"
- "Previsão de procura a 8 semanas para compras."
- "A partir de agora, todas as medidas têm de ter pasta de apresentação."

**2. Interface.** Em `http://localhost:8765` escolhes um funcionário ou uma rotina e carregas em Executar. Vês as rotinas e o último resultado, o quadro de tarefas, o diário, a telemetria e a fábrica em 3D. `Ctrl+K` abre a paleta de comandos.

**3. Sozinho.** Com o motor ligado, o escalonador dispara as rotinas à hora, uma de cada vez. Uma rotina sem entradas é ignorada sem gastar uma execução.

## A equipa

| N.º | Funcionário | Faz | Skills |
|---|---|---|---|
| D01 | **Amaterasu** | Orquestra, verifica e entrega; briefing diário | briefing-bi, novo-funcionario, instalar-rotinas |
| D02 | **Tsukuyomi** | Triagem de pedidos | triagem-pedidos |
| D03 | **Susanoo** | Deriva de dados e anomalias | drift-anomalias |
| D04 | **Hachiman** | KPIs e análises a pedido | kpis-semanais, analise-adhoc |
| D05 | **Benkei** | Revisão de DAX, modelo e RLS | revisor-dax, testes-rls |
| 900 | **Kenshin** | Refreshes, qualidade das fontes, SQL e Power Query, implementação | monitor-refresh, qualidade-dados, sql-powerquery |
| 901 | **Tetsuo** | ML: supervisor dos módulos 910 a 919 | ml-qualidade, ml-ciclo-vida, ml-churn, ml-procura, ml-ruturas, ml-desvios, ml-basket, ml-roi, ml-abc-xyz, ml-coortes |
| 902 | **Sakura** | User stories, sprint, notas de publicação | user-stories, release-notes |
| 903 | **Raiden** | Dicionário de modelos e dashboards | documentador-modelo, dashboard |
| 800 | **Auditor** | Auditoria independente | auditoria |
| ASS | **Tomoshibi** | Morning, fecho do dia, atas | morning, fecho-do-dia, ata-reuniao |
| PRG | **Kioku** | Resumo semanal, lições, higiene | resumo-semanal, higiene |

Os nomes são de apresentação. A correspondência com os perfis de origem (Arquimedes, Turing, Minerva, Atlas BI e outros) está em `escritorio/HIERARQUIA.md`.

## Rotinas

Declaradas em `escritorio/rotinas.json`, na hora local da máquina. `python -m foundry agenda` mostra as próximas execuções.

| Quando | Rotina | Quem | Precisa de |
|---|---|---|---|
| Dias úteis 08:30 | Morning audit | Tomoshibi | — |
| Dias úteis 08:47 | 910 · Qualidade dos dados de vendas | Tetsuo | `inbox/dados/vendas/sales.csv` |
| Dias úteis 09:08 | Refreshes e pipelines | Kenshin | `inbox/refresh/*.csv` |
| Dias úteis 09:26 | Briefing de BI | Amaterasu | — |
| Dias úteis 09:04, 12:04, 15:04, 17:04 | Triagem de pedidos | Tsukuyomi | `inbox/pedidos/*` |
| Dias úteis 10:15 | Deriva e anomalias | Susanoo | `inbox/dados/*.csv` |
| Dias úteis 17:30 | Fecho do dia | Tomoshibi | — |
| Segunda 09:21 | Consolidação semanal de KPIs | Hachiman | `inbox/dados/*.csv` |
| Segunda 09:40 | 911 · Ciclo de vida do cliente | Tetsuo | `sales.csv` |
| Quarta 10:30 | Revisão de modelos Power BI | Benkei | `inbox/modelos/**/*.tmdl` |
| Quarta 11:00 | Dicionário dos modelos | Raiden | `inbox/modelos/**/*.tmdl` |
| Sexta 16:00 | Resumo semanal | Kioku | — |
| Sexta 16:45 | Higiene e fronteira de dados | Kioku | — |
| Dia 3, 10:10 | 915 · Desvios preço-volume-mix | Tetsuo | `sales.csv` |
| Dia 1, 14:00 | Auditoria mensal do escritório | Auditor | — |
| A pedido | Ata de reunião, preparar sprint, 913 · previsão de procura | Tomoshibi, Sakura, Tetsuo | — |

Outras formas de agendar (crontab, tarefas agendadas do Claude): pede "instala as rotinas" ou vê a skill `instalar-rotinas`.

## Onde pôr o que chega

| Pasta | O quê |
|---|---|
| `inbox/pedidos/` | Pedidos de negócio (texto, email colado) |
| `inbox/dados/` | CSV com KPIs e amostras; registar em `cerebro/fontes.md` |
| `inbox/dados/vendas/` | Extratos para ML: `sales.csv`, `stock.csv`, `csv_options.json` |
| `inbox/modelos/` | Projetos Power BI em formato PBIP (TMDL) |
| `inbox/refresh/` | Registos de refreshes e pipelines exportados |
| `inbox/reunioes/` | Notas de reunião |

`inbox/`, `out/`, `done/` e a base de dados local nunca são versionados.

## Ferramentas

Os funcionários não calculam de cabeça: usam ferramentas que dão sempre o mesmo resultado para os mesmos dados. Também as podes correr à mão.

```bash
python -m foundry perfil inbox/dados/vendas_semanais.csv --chave semana,regiao,categoria --data semana
python -m foundry kpis inbox/dados/vendas_semanais.csv --data semana --valor receita --dim regiao
python -m foundry drift anomalias inbox/dados/vendas_semanais.csv --data semana --valor receita --grupo regiao
python -m foundry drift psi inbox/dados/referencia.csv inbox/dados/atual.csv
python -m foundry refresh inbox/refresh/refresh_log.csv
python -m foundry tmdl lint inbox/modelos/modelo_exemplo     # também: doc, rls
python -m foundry fronteira                                  # dados sensíveis no que é partilhado
python -m foundry ml demo                                    # motor ML com dados sintéticos
python -m foundry ajuda
```

## Motor ML

`motor_ml/` contém o pacote `bi_ml` 0.10.0 copiado sem alterações de `bi_ml_v0.10.zip` da Source_of_truth (SHA-256 do arquivo: `18c051c4…db9086`), com os seus 97 testes. O manifesto original (`MANIFEST_v0.10.sha256`) foi mantido tal como veio: confirma os 29 ficheiros incluídos e lista também 7 ficheiros de histórico dos ciclos de revisão que não foram copiados por não serem necessários à execução. As dez skills `ml-*` são geradas a partir dele (`python motor_ml/gerar_skills.py`) e usam todas `python -m foundry ml <comando>`.

Limites que o Tetsuo transmite sempre: validado apenas com dados sintéticos; previsão até 8 semanas, com intervalo; o cesto só recomenda com limiar de materialidade definido antes; o ROI é exploratório e nunca autoriza uma renovação. Detalhe em `motor_ml/README_V010.md`.

## Ensinar o escritório

- **Regras:** diz "a partir de agora…" e a regra entra em `cerebro/regras.md`. Depois do commit, vale para toda a equipa.
- **Métricas e fontes:** `cerebro/glossario.md` e `cerebro/fontes.md`. Os exemplos que lá estão são fictícios: substitui-os pelos da equipa.
- **Skills:** quando um passo falha repetidamente, o Claude propõe a alteração ao `SKILL.md` e só grava depois do teu OK.
- **Funcionário ou skill nova:** pede "quero um funcionário para…" (skill `novo-funcionario`): blueprint, ficheiros, registo, testes e estado inicial.
- **Lições:** a Kioku propõe-as no resumo semanal; a equipa aprova as que entram em `cerebro/licoes.md`.

## Segurança

- Os funcionários só podem ler, correr as ferramentas `python -m foundry …` e escrever em `out/`. Alterar a equipa, as skills, o cérebro ou o motor, fazer commit e fazer push pedem confirmação. Apagar ficheiros, `curl`, `wget` e lançar outras execuções estão bloqueados (`.claude/settings.json`).
- Nas rotinas automáticas, tudo o que pede confirmação é recusado.
- O motor só escuta em `localhost`. Para o partilhar numa rede interna é obrigatório indicar um segredo de acesso (`python -m foundry servir --host 0.0.0.0 --token <SEGREDO>`).
- **Fronteira de dados:** este repositório é o modelo, só com dados fictícios. Antes de usar dados reais, copia-o para o controlo de versões interno da organização e confirma a política de IA da empresa. Detalhe em `escritorio/FRONTEIRA_DE_DADOS.md`.
- Skills de terceiros: lê-as antes de as instalar, ou pede ao Claude que liste os ficheiros, comandos e chamadas de rede de cada uma.

## Estrutura

```
CLAUDE.md                 a orquestradora e as regras do escritório
.claude/agents/           11 funcionários
.claude/skills/           32 skills (22 de escritório e BI, 10 de ML)
.claude/settings.json     permissões
escritorio/               equipa.json, rotinas.json, hierarquia, fronteira de dados, promoção
cerebro/                  regras, glossário, fontes, catálogo, decisões, lições
foundry/                  motor: servidor, escalonador, base de dados, ferramentas, interface
motor_ml/                 bi_ml 0.10.0, testes e gerador das skills ML
exemplos/                 dados fictícios: modelo TMDL, pedidos, séries, registo de refresh
testes/                   testes do motor
inbox/ out/ done/         o que chega, o que sai, o que já foi tratado
```

## O que está verificado e o que falta

Verificado neste repositório:

- 52 testes do motor: `python -m unittest discover -s testes` (cron, escalonador, executor, API, permissões de origem, ferramentas sobre os dados de exemplo, fronteira).
- 97 testes do `bi_ml` com as dependências fixadas em `motor_ml/requirements-test.txt`.
- Interface em Chromium, em ecrã largo e telemóvel, com o estado gerado pelo motor em modo simulado.

Por verificar no ambiente da equipa:

- **Uma execução real através do Claude Code CLI.** Primeiro passo: `python -m foundry correr morning-audit`.
- Windows, dados reais, conectores de dados e tarefas agendadas na nuvem.
- Todos os funcionários estão no estado `configurado`. A subida a `instalado`, `verificado` e `producao` segue `escritorio/PROMOCAO.md` e exige evidência.

## Origem

- Estrutura de pastas, skills com scripts, cérebro partilhado e permissões inspirados em [bekhruztbx/ai-creative-team](https://github.com/bekhruztbx/ai-creative-team) (série "Build Your AI Team").
- Hierarquia, perfis 800 e 9xx, catálogo da equipa BI, estados de promoção e fronteira de dados: Source_of_truth do Pedro Vieira.
- Interface: evolução de `Interface da Fábrica de Dados`, agora ligada a dados reais do motor.
