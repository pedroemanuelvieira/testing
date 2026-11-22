"""Geradores determinísticos de dados sintéticos realistas para demonstração.

Cada tabela imita um modelo semântico típico de uma área de negócio e contém
sinal real (relações plausíveis entre variáveis e alvo), ruído, valores em
falta, outliers e — em alguns casos — armadilhas didáticas (ex.: colunas que
causam data leakage), para que a equipa possa treinar o fluxo completo.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Callable

import numpy as np
import pandas as pd

REF_DATE = pd.Timestamp("2024-12-31")

PT_HOLIDAYS = pd.to_datetime([
    "2022-01-01", "2022-04-15", "2022-04-25", "2022-05-01", "2022-06-10", "2022-06-16", "2022-08-15",
    "2022-10-05", "2022-11-01", "2022-12-01", "2022-12-08", "2022-12-25",
    "2023-01-01", "2023-04-07", "2023-04-25", "2023-05-01", "2023-06-08", "2023-06-10", "2023-08-15",
    "2023-10-05", "2023-11-01", "2023-12-01", "2023-12-08", "2023-12-25",
    "2024-01-01", "2024-03-29", "2024-04-25", "2024-05-01", "2024-05-30", "2024-06-10", "2024-08-15",
    "2024-10-05", "2024-11-01", "2024-12-01", "2024-12-08", "2024-12-25",
])

REGIOES = ["Norte", "Centro", "Lisboa", "Alentejo", "Algarve", "Ilhas"]
REGIOES_P = [0.32, 0.20, 0.30, 0.07, 0.06, 0.05]


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def _calibrate(z: np.ndarray, rate: float) -> np.ndarray:
    """Desloca o logit para que a probabilidade média seja ``rate``."""
    z = np.asarray(z, dtype=float)
    lo, hi = -30.0, 30.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _sigmoid(z + mid).mean() > rate:
            hi = mid
        else:
            lo = mid
    return z + (lo + hi) / 2


def _draw(rng: np.random.Generator, z: np.ndarray, rate: float) -> np.ndarray:
    return (rng.random(len(z)) < _sigmoid(_calibrate(z, rate))).astype(int)


def _choice(rng, values, n, p=None):
    return rng.choice(np.array(values), size=n, p=p)


# =============================================================================== CRM
def clientes(n: int = 6000) -> pd.DataFrame:
    rng = np.random.default_rng(101)
    segmento = _choice(rng, ["Particular", "PME", "Empresa"], n, [0.70, 0.22, 0.08])
    regiao = _choice(rng, REGIOES, n, REGIOES_P)
    canal = _choice(rng, ["Loja", "Online", "Parceiro", "Televendas"], n, [0.35, 0.35, 0.18, 0.12])
    plano = _choice(rng, ["Básico", "Standard", "Premium"], n, [0.45, 0.38, 0.17])
    empresa = segmento != "Particular"
    idade = np.clip(rng.normal(44, 13, n), 18, 88).round()
    idade = np.where(empresa, np.nan, idade)
    genero = np.where(empresa, "N/A", _choice(rng, ["F", "M"], n, [0.52, 0.48]))
    # arquétipos comportamentais latentes: 0 Campeões, 1 Leais, 2 Novos, 3 Em risco, 4 Adormecidos
    arq = rng.choice(5, size=n, p=[0.14, 0.26, 0.18, 0.22, 0.20])
    antig_base = np.choose(arq, [rng.exponential(40, n) + 18, rng.exponential(55, n) + 30, rng.uniform(1, 9, n),
                                 rng.exponential(30, n) + 8, rng.exponential(35, n) + 14])
    antig = np.clip(antig_base.astype(int) + 1, 1, 180)
    data_adesao = REF_DATE - pd.to_timedelta(antig * 30.4, unit="D")
    base_m = pd.Series(plano).map({"Básico": 19.9, "Standard": 34.9, "Premium": 59.9}).to_numpy()
    seg_f = pd.Series(segmento).map({"Particular": 1.0, "PME": 1.6, "Empresa": 2.8}).to_numpy()
    mensalidade = np.round(base_m * seg_f * rng.uniform(0.92, 1.08, n), 2)
    n_produtos = 1 + rng.poisson(0.6 + 0.7 * (plano == "Premium") + 0.5 * empresa)
    consumo = np.round(rng.gamma(4, 12, n) * seg_f, 1)
    usa_app = (rng.random(n) < np.where(canal == "Online", 0.7, 0.38)).astype(int)
    fatura_el = (rng.random(n) < 0.62).astype(int)
    metodo = _choice(rng, ["Débito Direto", "Multibanco", "Cartão", "Transferência"], n, [0.45, 0.25, 0.2, 0.1])
    reclam = rng.poisson(0.45, n)
    contactos = rng.poisson(0.8 + 0.9 * reclam)
    atrasos = rng.poisson(np.where(metodo == "Multibanco", 0.5, 0.2))
    desconto = (rng.random(n) < 0.25).astype(int)
    fim_fid = np.where(rng.random(n) < 0.3, 0, rng.integers(1, 25, n))
    freq_base = np.choose(arq, [24.0, 13.0, 5.0, 7.0, 2.0])
    n_compras = rng.poisson(freq_base * (1 + 0.3 * (plano == "Premium") + 0.25 * empresa + 0.15 * usa_app))
    ticket = rng.gamma(3, 1.0, n) * np.choose(arq, [42.0, 26.0, 30.0, 28.0, 18.0]) * seg_f
    valor_compras = np.round(n_compras * ticket, 2)
    sat = np.clip(np.round(rng.normal(7.4 - 0.9 * reclam, 1.6)), 1, 10)
    sat = np.where(rng.random(n) < 0.22, np.nan, sat)

    # latentes de comportamento → churn
    var_consumo = rng.normal(0.0, 0.14, n)
    risk = (0.6 * reclam + 1.5 * (fim_fid <= 1) - 0.016 * antig + 0.45 * atrasos - 0.45 * usa_app
            - 0.3 * n_produtos + 0.35 * (plano == "Básico") + 0.3 * (canal == "Online") - 0.5 * desconto
            - 0.2 * np.nan_to_num(sat - 7.4) + np.choose(arq, [-0.6, -0.3, 0.1, 0.6, 0.8]) + rng.normal(0, 0.6, n))
    churn = _draw(rng, risk, 0.18)
    # comportamento recente reflete a intenção de saída (sinal legítimo mas imperfeito)
    var_consumo = var_consumo - 0.22 * churn * rng.uniform(0.3, 1.2, n)
    rec_base = np.choose(arq, [7.0, 18.0, 14.0, 60.0, 140.0])
    dias_ult = np.round(rng.exponential(rec_base) * (1 + 1.2 * churn * rng.random(n))).astype(int)

    cross_z = (0.9 * usa_app + 0.004 * valor_compras / seg_f - 0.5 * (n_produtos >= 3)
               + 0.6 * (plano == "Standard") + 0.04 * n_compras - 0.8 * churn + rng.normal(0, 0.7, n))
    cross = _draw(rng, cross_z, 0.12)
    clv = ((mensalidade * 12 * (0.85 + 0.08 * n_produtos) + 0.35 * valor_compras)
           * rng.lognormal(0, 0.25, n) * np.where(churn == 1, rng.uniform(0.0, 0.35, n), 1.0))

    df = pd.DataFrame({
        "cliente_id": [f"C{100000 + i}" for i in range(n)],
        "data_adesao": data_adesao.normalize(),
        "regiao": regiao, "segmento": segmento, "canal_aquisicao": canal, "plano": plano,
        "idade": idade, "genero": genero, "antiguidade_meses": antig, "mensalidade": mensalidade,
        "n_produtos": n_produtos, "consumo_medio_3m": consumo, "variacao_consumo_3m": np.round(var_consumo, 3),
        "n_reclamacoes_6m": reclam, "contactos_apoio_3m": contactos, "dias_desde_ultima_compra": dias_ult,
        "n_compras_12m": n_compras, "valor_compras_12m": valor_compras, "usa_app": usa_app,
        "fatura_eletronica": fatura_el, "metodo_pagamento": metodo, "atrasos_pagamento_12m": atrasos,
        "satisfacao_ultimo_inquerito": sat, "desconto_ativo": desconto, "fim_fidelizacao_meses": fim_fid,
        "churn": churn, "valor_futuro_12m": np.round(clv, 2), "aderiu_cross_sell": cross,
    })
    # duplicados acidentais (problema de qualidade didático)
    dup = df.sample(25, random_state=7)
    return pd.concat([df, dup], ignore_index=True)


def leads(n: int = 5000) -> pd.DataFrame:
    rng = np.random.default_rng(202)
    origem = _choice(rng, ["Website", "Feira", "Referência", "LinkedIn", "Campanha Email", "Outbound"], n,
                     [0.28, 0.1, 0.12, 0.15, 0.2, 0.15])
    setor = _choice(rng, ["Retalho", "Indústria", "Serviços", "Saúde", "Tecnologia", "Construção", "Público"], n)
    dimensao = _choice(rng, ["Micro", "Pequena", "Média", "Grande"], n, [0.35, 0.33, 0.22, 0.1])
    cargo = _choice(rng, ["Diretor", "Gestor", "Técnico", "Administrador"], n, [0.2, 0.35, 0.35, 0.1])
    interacoes = rng.poisson(3, n)
    emails = rng.poisson(2 + 0.5 * interacoes)
    visitas = rng.poisson(4, n)
    demo = (rng.random(n) < 0.22).astype(int)
    dias_contacto = np.round(rng.exponential(3, n), 1)
    valor = np.round(rng.lognormal(8.5, 0.9, n) * pd.Series(dimensao).map(
        {"Micro": 0.4, "Pequena": 0.8, "Média": 1.6, "Grande": 3.5}).to_numpy(), 0)
    comercial = _choice(rng, [f"C{i:02d}" for i in range(1, 13)], n)
    z = (1.6 * demo + 0.22 * interacoes + 0.1 * emails + 0.06 * visitas - 0.18 * dias_contacto
         + pd.Series(origem).map({"Referência": 1.0, "Feira": 0.4, "Website": 0.2, "LinkedIn": 0.0,
                                  "Campanha Email": -0.2, "Outbound": -0.7}).to_numpy()
         + pd.Series(cargo).map({"Diretor": 0.5, "Administrador": 0.6, "Gestor": 0.1, "Técnico": -0.4}).to_numpy()
         + pd.Series(dimensao).map({"Micro": -0.3, "Pequena": 0.0, "Média": 0.3, "Grande": 0.2}).to_numpy()
         + pd.Series(setor).map({"Tecnologia": 0.3, "Saúde": 0.2, "Público": -0.5}).fillna(0).to_numpy()
         + rng.normal(0, 0.7, n))
    conv = _draw(rng, z, 0.22)
    datas = REF_DATE - pd.to_timedelta(rng.integers(90, 720, n), unit="D")
    return pd.DataFrame({
        "lead_id": [f"L{50000 + i}" for i in range(n)], "data_criacao": datas.normalize(), "origem": origem,
        "setor": setor, "dimensao_empresa": dimensao, "regiao": _choice(rng, REGIOES, n, REGIOES_P),
        "cargo_contacto": cargo, "n_interacoes": interacoes, "n_emails_abertos": emails,
        "visitas_website": visitas, "pediu_demo": demo, "dias_ate_primeiro_contacto": dias_contacto,
        "valor_estimado": valor, "comercial_responsavel": comercial, "converteu": conv,
    })


def campanhas(n: int = 8000) -> pd.DataFrame:
    rng = np.random.default_rng(303)
    campanha = _choice(rng, ["Primavera", "Verão", "Black Friday", "Natal"], n)
    canal = _choice(rng, ["Email", "SMS", "App", "Correio"], n, [0.45, 0.25, 0.2, 0.1])
    segmento = _choice(rng, ["Particular", "PME"], n, [0.8, 0.2])
    idade = np.clip(rng.normal(45, 14, n), 18, 85).round()
    antig = np.clip(rng.exponential(30, n).astype(int) + 1, 1, 180)
    compras = rng.poisson(7, n)
    valor = np.round(compras * rng.gamma(3, 25, n), 2)
    rec = np.round(rng.exponential(45, n)).astype(int)
    resp_ant = (rng.random(n) < 0.15).astype(int)
    desconto = rng.choice([0, 5, 10, 15, 20, 25], n)
    hora = rng.integers(8, 23, n)
    dia = _choice(rng, ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"], n)
    z = (1.7 * resp_ant + 0.05 * desconto - 0.012 * rec + 0.05 * compras
         + pd.Series(canal).map({"App": 0.7, "Email": 0.1, "SMS": 0.2, "Correio": -0.6}).to_numpy()
         + pd.Series(campanha).map({"Black Friday": 0.6, "Natal": 0.3, "Verão": -0.1, "Primavera": 0.0}).to_numpy()
         + 0.35 * ((hora >= 18) & (hora <= 21)) - 0.01 * np.abs(idade - 38) + rng.normal(0, 0.8, n))
    return pd.DataFrame({
        "cliente_id": [f"C{100000 + int(i)}" for i in rng.integers(0, 6000, n)], "campanha": campanha,
        "canal": canal, "segmento": segmento, "idade": idade, "antiguidade_meses": antig,
        "n_compras_12m": compras, "valor_compras_12m": valor, "dias_desde_ultima_compra": rec,
        "respondeu_campanha_anterior": resp_ant, "desconto_oferecido_pct": desconto.astype(int),
        "hora_envio": hora, "dia_semana_envio": dia, "respondeu": _draw(rng, z, 0.09),
    })


# =============================================================================== VENDAS
LOJAS = {"Lisboa Centro": (1.45, 0.0), "Porto Baixa": (1.2, -1.0), "Braga": (0.8, -2.0),
         "Coimbra": (0.72, -0.5), "Faro": (0.65, 3.0)}
FAMILIAS = {  # unidades base, preço base, elasticidade
    "Mercearia": (420, 3.2, -1.2), "Frescos": (380, 4.1, -0.6), "Bebidas": (260, 2.6, -2.0),
    "Higiene": (150, 5.5, -1.5), "Casa": (90, 9.8, -1.8),
}


def vendas_diarias() -> pd.DataFrame:
    rng = np.random.default_rng(404)
    dates = pd.date_range("2023-01-01", "2024-12-31", freq="D")
    t = np.arange(len(dates))
    dow_f = np.array([0.86, 0.88, 0.92, 0.98, 1.15, 1.32, 0.9])[dates.dayofweek]
    doy = dates.dayofyear.to_numpy()
    is_hol = dates.isin(PT_HOLIDAYS)
    rows = []
    for loja, (lf, temp_off) in LOJAS.items():
        temp = 17 + 7 * np.sin(2 * np.pi * (doy - 110) / 365) + temp_off + rng.normal(0, 2, len(dates))
        for fam, (u0, p0, el) in FAMILIAS.items():
            promo = np.zeros(len(dates), dtype=int)
            starts = rng.choice(len(dates) - 7, size=14, replace=False)
            for s in starts:
                promo[s:s + 7] = 1
            desc = np.where(promo == 1, rng.choice([10, 15, 20, 25, 30], len(dates)), 0)
            price = p0 * (1 + 0.03 * t / 365) * (1 - desc / 100) * rng.uniform(0.97, 1.03, len(dates))
            price_ratio = price / (p0 * (1 + 0.03 * t / 365))
            year = np.ones(len(dates))
            year += 0.25 * (dates.month == 12) + 0.08 * (dates.month == 11)
            if loja == "Faro":
                year += 0.45 * dates.month.isin([7, 8]) + 0.15 * dates.month.isin([6, 9])
            temp_eff = 1 + (0.022 * (temp - 18) if fam == "Bebidas" else 0.004 * (temp - 18))
            hol = np.where(is_hol, 0.6, 1.0)
            hol = np.where((dates.month == 12) & (dates.day == 25) | (dates.month == 1) & (dates.day == 1), 0.12, hol)
            mu = (u0 * lf * dow_f * year * (1 + 0.06 * t / 365) * temp_eff * hol * price_ratio ** el
                  * (1 + 0.08 * promo))
            units = np.maximum(0, np.round(mu * rng.lognormal(0, 0.09, len(dates)))).astype(int)
            rows.append(pd.DataFrame({
                "data": dates, "loja": loja, "familia": fam, "unidades": units,
                "preco_medio": np.round(price, 2), "receita": np.round(units * price, 2),
                "em_promocao": promo, "desconto_pct": desc.astype(int), "feriado": is_hol.astype(int),
                "temperatura": np.round(temp, 1),
            }))
    return pd.concat(rows, ignore_index=True)


PRODUTOS = {
    "Pão": ("Padaria", 1.2, 0.55), "Manteiga": ("Laticínios", 2.4, 0.12), "Leite": ("Laticínios", 0.9, 0.5),
    "Queijo": ("Laticínios", 3.8, 0.15), "Iogurtes": ("Laticínios", 2.6, 0.25), "Cereais": ("Mercearia", 3.1, 0.12),
    "Café": ("Mercearia", 4.5, 0.18), "Açúcar": ("Mercearia", 1.1, 0.08), "Massa": ("Mercearia", 1.3, 0.2),
    "Molho de tomate": ("Mercearia", 1.6, 0.08), "Arroz": ("Mercearia", 1.4, 0.2), "Azeite": ("Mercearia", 7.9, 0.1),
    "Cerveja": ("Bebidas", 4.9, 0.18), "Batatas fritas": ("Snacks", 1.9, 0.12), "Vinho tinto": ("Bebidas", 5.5, 0.12),
    "Água": ("Bebidas", 2.2, 0.35), "Refrigerante": ("Bebidas", 1.8, 0.18), "Gin": ("Bebidas", 18.5, 0.03),
    "Água tónica": ("Bebidas", 2.9, 0.04), "Fraldas": ("Bebé", 11.9, 0.05), "Toalhitas": ("Bebé", 2.7, 0.04),
    "Hambúrgueres": ("Talho", 4.2, 0.08), "Pão de hambúrguer": ("Padaria", 1.7, 0.04), "Frango": ("Talho", 5.6, 0.2),
    "Fruta": ("Frescos", 2.8, 0.45), "Legumes": ("Frescos", 2.2, 0.4), "Ovos": ("Frescos", 2.3, 0.25),
    "Detergente roupa": ("Casa", 8.9, 0.06), "Amaciador": ("Casa", 4.3, 0.04), "Papel higiénico": ("Casa", 4.9, 0.15),
    "Champô": ("Higiene", 3.9, 0.08), "Pasta de dentes": ("Higiene", 2.5, 0.1), "Chocolate": ("Snacks", 1.6, 0.15),
    "Bolachas": ("Snacks", 1.4, 0.18),
}
ASSOCIACOES = [("Pão", "Manteiga", 0.32), ("Cerveja", "Batatas fritas", 0.5), ("Massa", "Molho de tomate", 0.5),
               ("Café", "Açúcar", 0.35), ("Fraldas", "Toalhitas", 0.55), ("Vinho tinto", "Queijo", 0.4),
               ("Cereais", "Leite", 0.55), ("Hambúrgueres", "Pão de hambúrguer", 0.6),
               ("Detergente roupa", "Amaciador", 0.4), ("Gin", "Água tónica", 0.7)]


def linhas_talao(n_taloes: int = 6000) -> pd.DataFrame:
    rng = np.random.default_rng(505)
    names = list(PRODUTOS)
    pop = np.array([PRODUTOS[p][2] for p in names])
    rows = []
    dates = pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 366, n_taloes), unit="D")
    lojas = _choice(rng, list(LOJAS), n_taloes)
    for i in range(n_taloes):
        basket = {p for p in names if rng.random() < pop[names.index(p)] * 0.55}
        if not basket:
            basket = {names[int(rng.integers(len(names)))]}
        for a, b, prob in ASSOCIACOES:
            if a in basket and rng.random() < prob:
                basket.add(b)
        for p in basket:
            q = int(rng.integers(1, 4))
            rows.append((f"T{700000 + i}", dates[i], lojas[i], p, PRODUTOS[p][0], q, round(q * PRODUTOS[p][1], 2)))
    return pd.DataFrame(rows, columns=["talao_id", "data", "loja", "produto", "categoria", "quantidade", "valor"])


def stock(n: int = 6000) -> pd.DataFrame:
    rng = np.random.default_rng(606)
    fam = _choice(rng, list(FAMILIAS), n)
    procura = np.round(rng.gamma(3, 9, n), 1)
    cv = rng.uniform(0.1, 0.9, n)
    desvio = np.round(procura * cv, 1)
    stock_atual = np.round(procura * rng.gamma(2.2, 2.5, n)).astype(int)
    cobertura = np.round(stock_atual / np.maximum(procura, 0.5), 1)
    lead = rng.integers(1, 15, n)
    fornecedor = _choice(rng, [f"F{i}" for i in range(1, 9)], n)
    fiab_map = {f"F{i}": v for i, v in enumerate([0.97, 0.95, 0.92, 0.9, 0.88, 0.85, 0.8, 0.74], start=1)}
    fiab = np.clip(pd.Series(fornecedor).map(fiab_map).to_numpy() + rng.normal(0, 0.03, n), 0.5, 1.0)
    pendente = (rng.random(n) < 0.4).astype(int)
    promo = (rng.random(n) < 0.15).astype(int)
    z = (-0.55 * cobertura + 0.22 * lead + 6 * (1 - fiab) + 0.9 * promo + 1.2 * cv - 0.9 * pendente
         + rng.normal(0, 0.6, n))
    datas = pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 366, n), unit="D")
    return pd.DataFrame({
        "registo_id": [f"S{i:06d}" for i in range(n)], "data": datas, "loja": _choice(rng, list(LOJAS), n),
        "produto": [f"SKU-{int(x):04d}" for x in rng.integers(1, 400, n)], "familia": fam,
        "stock_atual": stock_atual, "procura_media_7d": procura, "desvio_procura_7d": desvio,
        "lead_time_fornecedor_dias": lead, "dias_cobertura": cobertura, "encomenda_pendente": pendente,
        "fornecedor": fornecedor, "taxa_cumprimento_fornecedor": np.round(fiab, 3),
        "em_promocao_proxima_semana": promo, "rutura_proximos_7d": _draw(rng, z, 0.15),
    }).sort_values("data").reset_index(drop=True)


# =============================================================================== FINANÇAS
def faturas(n: int = 7000) -> pd.DataFrame:
    rng = np.random.default_rng(707)
    rating = _choice(rng, list("ABCDE"), n, [0.18, 0.32, 0.28, 0.15, 0.07])
    setor = _choice(rng, ["Retalho", "Indústria", "Serviços", "Construção", "Público", "Saúde"], n)
    seg = _choice(rng, ["PME", "Empresa", "Grande Conta"], n, [0.55, 0.35, 0.1])
    prazo = _choice(rng, [30, 60, 90], n, [0.5, 0.35, 0.15])
    valor = np.round(rng.lognormal(7.6, 1.1, n), 2)
    valor[rng.random(n) < 0.004] *= 80  # outliers
    n_atr = rng.poisson(pd.Series(rating).map({"A": 0.2, "B": 0.6, "C": 1.2, "D": 2.4, "E": 4}).to_numpy())
    atr_med = np.round(np.where(n_atr > 0, rng.gamma(2, 9, n) + 3 * n_atr, 0), 1)
    antig = np.round(rng.exponential(5, n), 1)
    plano_pag = (rng.random(n) < 0.08).astype(int)
    latent = (pd.Series(rating).map({"A": -12, "B": -4, "C": 4, "D": 14, "E": 26}).to_numpy()
              + 2.2 * n_atr + 0.35 * atr_med + 3 * np.log1p(valor / 1000) - 1.2 * antig
              + pd.Series(setor).map({"Construção": 10, "Público": 14, "Retalho": 2}).fillna(0).to_numpy()
              + 0.08 * prazo + 6 * plano_pag + rng.normal(0, 14, n))
    shift = 30 - np.quantile(latent, 0.80)
    dias = np.clip(np.round(latent + shift), 0, 365).astype(int)
    emissao = REF_DATE - pd.to_timedelta(rng.integers(30, 720, n), unit="D")
    return pd.DataFrame({
        "fatura_id": [f"FT{2024000 + i}" for i in range(n)],
        "cliente_id": [f"E{int(x):05d}" for x in rng.integers(1, 1800, n)],
        "data_emissao": emissao.normalize(), "valor": valor, "segmento_cliente": seg, "setor": setor,
        "regiao": _choice(rng, REGIOES, n, REGIOES_P), "prazo_pagamento_dias": prazo,
        "n_faturas_atrasadas_historico": n_atr, "atraso_medio_historico_dias": atr_med,
        "rating_interno": rating, "antiguidade_cliente_anos": antig,
        "metodo_pagamento": _choice(rng, ["Transferência", "Débito Direto", "Cheque", "Multibanco"], n, [0.6, 0.2, 0.05, 0.15]),
        "tem_plano_pagamento": plano_pag, "dias_atraso": dias, "atraso_superior_30d": (dias > 30).astype(int),
    })


def fluxos_caixa() -> pd.DataFrame:
    rng = np.random.default_rng(808)
    dates = pd.date_range("2022-01-01", "2024-12-31", freq="D")
    t = np.arange(len(dates))
    bday = (dates.dayofweek < 5) & ~dates.isin(PT_HOLIDAYS)
    month_end = dates.is_month_end | (dates + pd.Timedelta(days=1)).is_month_end | (dates + pd.Timedelta(days=2)).is_month_end
    dom = dates.day.to_numpy()
    base = 120_000 * (1 + 0.08 * t / 365)
    rec = base * np.where(month_end, 1.6, 1.0) * np.where(dom <= 5, 1.2, 1.0)
    rec *= np.where(dates.month == 8, 0.8, 1.0) * np.where(dates.month == 12, 1.15, 1.0)
    rec *= np.where(dates.dayofweek == 0, 1.1, 1.0) * rng.lognormal(0, 0.15, len(dates))
    rec = np.where(bday, rec, 0.0)
    pag = base * 0.55 * rng.lognormal(0, 0.25, len(dates))
    pag += np.where(dom == 25, 900_000 * (1 + 0.05 * t / 365), 0) + np.where(dom == 20, 300_000, 0)
    pag = np.where(bday | (dom == 25), pag, 0.0)
    return pd.DataFrame({"data": dates, "recebimentos": np.round(rec, 2), "pagamentos": np.round(pag, 2),
                         "fluxo_liquido": np.round(rec - pag, 2), "dia_util": bday.astype(int)})


def despesas(n: int = 5000) -> pd.DataFrame:
    rng = np.random.default_rng(909)
    cat_means = {"Viagens": 400, "Software": 1500, "Consultoria": 6000, "Material": 250, "Serviços": 1200, "Formação": 900}
    cc = _choice(rng, ["Marketing", "TI", "Operações", "RH", "Comercial", "Administrativo"], n)
    cc_cat = {"Marketing": ["Serviços", "Consultoria", "Viagens"], "TI": ["Software", "Consultoria", "Material"],
              "Operações": ["Material", "Serviços", "Viagens"], "RH": ["Formação", "Serviços", "Viagens"],
              "Comercial": ["Viagens", "Serviços", "Formação"], "Administrativo": ["Material", "Software", "Serviços"]}
    cat = np.array([rng.choice(cc_cat[c]) for c in cc], dtype=object)
    valor = np.array([rng.lognormal(np.log(cat_means[c]), 0.45) for c in cat])
    hora = np.clip(np.round(rng.normal(13, 2.5, n)), 8, 19).astype(int)
    datas = pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 366, n), unit="D")
    fds = (datas.dayofweek >= 5).astype(int)
    datas = datas.where(fds == 0, datas - pd.to_timedelta(datas.dayofweek - 4, unit="D"))
    fds = np.zeros(n, dtype=int)
    aprov = _choice(rng, [f"A{i:02d}" for i in range(1, 11)], n)
    dias_ap = np.clip(np.round(rng.gamma(2, 1.6, n)), 0, 15).astype(int)
    itens = rng.integers(1, 12, n)
    anom = np.zeros(n, dtype=int)
    idx = rng.choice(n, size=int(0.02 * n), replace=False)
    for j, i in enumerate(idx):
        kind = j % 4
        if kind == 0:
            valor[i] *= rng.uniform(8, 20)
        elif kind == 1:
            fds[i], hora[i], dias_ap[i] = 1, int(rng.choice([0, 1, 2, 22, 23])), 0
            valor[i] *= rng.uniform(2, 5)
        elif kind == 2:
            cat[i] = "Consultoria" if cc[i] in ("RH", "Administrativo") else "Formação"
            valor[i] = rng.uniform(15000, 40000)
        else:
            itens[i] = int(rng.integers(80, 200))
            dias_ap[i] = 0
        anom[i] = 1
    datas = datas.where(fds == 0, datas + pd.to_timedelta(5 - datas.dayofweek, unit="D"))
    fornecedor = np.array([f"{c[:3].upper()}-{int(rng.integers(1, 9))}" for c in cat], dtype=object)
    return pd.DataFrame({
        "lancamento_id": [f"D{30000 + i}" for i in range(n)], "data": datas.normalize(), "centro_custo": cc,
        "fornecedor": fornecedor, "categoria_despesa": cat, "valor": np.round(valor, 2), "n_itens": itens,
        "aprovador": aprov, "dias_aprovacao": dias_ap, "fim_de_semana": fds, "hora_lancamento": hora,
        "anomalia": anom,
    })


# =============================================================================== RISCO
def credito(n: int = 8000) -> pd.DataFrame:
    rng = np.random.default_rng(1001)
    genero = _choice(rng, ["F", "M"], n, [0.47, 0.53])
    idade = np.clip(rng.normal(41, 11, n), 19, 79).round()
    contrato = _choice(rng, ["Efetivo", "Termo", "Independente", "Reformado"], n, [0.58, 0.2, 0.14, 0.08])
    rendimento = np.round(rng.lognormal(7.25, 0.42, n) * np.where(genero == "M", 1.06, 1.0)
                          * pd.Series(contrato).map({"Efetivo": 1.1, "Termo": 0.85, "Independente": 1.0, "Reformado": 0.8}).to_numpy(), 0)
    finalidade = _choice(rng, ["Habitação", "Automóvel", "Pessoal", "Consolidação", "Educação"], n, [0.3, 0.25, 0.25, 0.12, 0.08])
    montante = np.round(np.where(finalidade == "Habitação", rng.lognormal(11.7, 0.4, n), rng.lognormal(9.2, 0.6, n)), -2)
    prazo = np.where(finalidade == "Habitação", rng.choice([240, 300, 360], n), rng.choice([24, 36, 48, 60, 84], n))
    taxa = np.round(np.where(finalidade == "Habitação", rng.uniform(2.5, 4.5, n), rng.uniform(5, 13, n)), 2)
    r = taxa / 1200
    prest = montante * r / (1 - (1 + r) ** -prazo)
    esforco = np.round(np.clip(prest / rendimento * 100 + rng.normal(5, 4, n), 3, 90), 1)
    antig_emp = np.round(np.clip(rng.exponential(7, n), 0, 40), 1)
    n_cred = rng.poisson(0.9, n)
    incump_ant = rng.poisson(0.15, n)
    score = np.clip(np.round(rng.normal(680, 70, n) - 45 * incump_ant), 300, 850)
    habit = _choice(rng, ["Própria", "Arrendada", "Familiares"], n, [0.55, 0.35, 0.1])
    z = (0.055 * esforco + 1.1 * incump_ant - 0.012 * (score - 680) - 0.06 * antig_emp + 0.3 * n_cred
         + pd.Series(contrato).map({"Termo": 0.5, "Independente": 0.45, "Efetivo": 0.0, "Reformado": 0.1}).to_numpy()
         + pd.Series(finalidade).map({"Pessoal": 0.4, "Consolidação": 0.7, "Habitação": -0.6}).fillna(0).to_numpy()
         + 0.35 * (habit == "Arrendada") + 0.0006 * (idade - 42) ** 2 + rng.normal(0, 0.6, n))
    datas = pd.Timestamp("2021-01-01") + pd.to_timedelta(rng.integers(0, 1100, n), unit="D")
    return pd.DataFrame({
        "pedido_id": [f"P{900000 + i}" for i in range(n)], "data_pedido": datas, "montante": montante,
        "prazo_meses": prazo, "taxa_juro": taxa, "finalidade": finalidade, "rendimento_mensal": rendimento,
        "taxa_esforco": esforco, "antiguidade_emprego_anos": antig_emp, "tipo_contrato": contrato,
        "idade": idade, "estado_civil": _choice(rng, ["Solteiro", "Casado", "Divorciado", "Viúvo"], n, [0.35, 0.48, 0.13, 0.04]),
        "n_dependentes": rng.poisson(0.9, n), "n_creditos_ativos": n_cred, "incumprimentos_anteriores": incump_ant,
        "score_externo": score, "habitacao": habit, "regiao": _choice(rng, REGIOES, n, REGIOES_P),
        "genero": genero, "incumprimento": _draw(rng, z, 0.08),
    })


def transacoes(n: int = 20000) -> pd.DataFrame:
    rng = np.random.default_rng(1102)
    fraud = (rng.random(n) < 0.012).astype(int)
    ts = (pd.Timestamp("2024-01-01") + pd.to_timedelta(np.sort(rng.integers(0, 366 * 24 * 60, n)), unit="m"))
    month = ts.month.to_numpy()
    hora_legit = np.clip(np.round(rng.normal(14, 4, n)), 0, 23)
    hora_fraud = rng.choice([0, 1, 2, 3, 4, 5, 22, 23, 12, 15], n)
    hora = np.where(fraud == 1, hora_fraud, hora_legit).astype(int)
    ts = ts.normalize() + pd.to_timedelta(hora, unit="h") + pd.to_timedelta(rng.integers(0, 60, n), unit="m")
    canal_l = _choice(rng, ["POS", "Online", "MB Way", "ATM"], n, [0.55, 0.25, 0.12, 0.08])
    # concept drift: fraude migra para MB Way na segunda metade do ano
    canal_f = np.where(month > 6, _choice(rng, ["Online", "MB Way", "POS"], n, [0.35, 0.5, 0.15]),
                       _choice(rng, ["Online", "MB Way", "POS", "ATM"], n, [0.6, 0.15, 0.15, 0.1]))
    canal = np.where(fraud == 1, canal_f, canal_l)
    cat_l = _choice(rng, ["Supermercado", "Restauração", "Eletrónica", "Viagens", "Combustível", "Jogo", "Moda"], n,
                    [0.32, 0.22, 0.07, 0.05, 0.18, 0.03, 0.13])
    cat_f = _choice(rng, ["Eletrónica", "Viagens", "Jogo", "Moda", "Supermercado"], n, [0.35, 0.2, 0.2, 0.15, 0.1])
    categoria = np.where(fraud == 1, cat_f, cat_l)
    media30 = np.round(rng.lognormal(3.6, 0.6, n), 2)
    racio = np.where(fraud == 1, rng.lognormal(1.6, 0.8, n), rng.lognormal(0, 0.5, n))
    montante = np.round(media30 * racio, 2)
    pais = np.where(fraud == 1, _choice(rng, ["PT", "ES", "FR", "UK", "Outros"], n, [0.45, 0.1, 0.1, 0.1, 0.25]),
                    _choice(rng, ["PT", "ES", "FR", "UK", "Outros"], n, [0.92, 0.04, 0.02, 0.01, 0.01]))
    dist = np.round(np.where(fraud == 1, rng.exponential(300, n), rng.exponential(12, n)), 1)
    n24 = np.where(fraud == 1, rng.poisson(6, n), rng.poisson(2.2, n))
    novo_disp = (rng.random(n) < np.where(fraud == 1, 0.55, 0.04)).astype(int)
    presente = np.where(np.isin(canal, ["POS", "ATM"]), (rng.random(n) < np.where(fraud == 1, 0.4, 0.97)).astype(int), 0)
    pin = np.where(np.isin(canal, ["POS", "ATM"]), np.where(fraud == 1, rng.poisson(1.2, n), rng.poisson(0.05, n)), 0)
    return pd.DataFrame({
        "transacao_id": [f"TX{10_000_000 + i}" for i in range(n)], "data_hora": ts, "montante": montante,
        "canal": canal, "categoria_comerciante": categoria, "pais": pais, "hora": hora,
        "distancia_casa_km": dist, "n_transacoes_24h": n24, "montante_medio_30d": media30,
        "racio_montante_media": np.round(racio, 3), "cartao_presente": presente, "novo_dispositivo": novo_disp,
        "tentativas_pin": pin, "fraude": fraud,
    })


# =============================================================================== LOGÍSTICA
def entregas(n: int = 8000) -> pd.DataFrame:
    rng = np.random.default_rng(1203)
    transp = _choice(rng, ["TransRapido", "LogiNorte", "ExpressoSul", "CargoPT"], n, [0.35, 0.25, 0.2, 0.2])
    zona = _choice(rng, ["Urbana", "Suburbana", "Rural", "Ilhas"], n, [0.45, 0.3, 0.2, 0.05])
    servico = _choice(rng, ["Standard", "Expresso", "Agendado"], n, [0.6, 0.25, 0.15])
    armazem = _choice(rng, ["Azambuja", "Maia", "Carregado"], n)
    distritos = ["Lisboa", "Porto", "Braga", "Setúbal", "Aveiro", "Faro", "Coimbra", "Leiria", "Viseu", "Bragança",
                 "Évora", "Beja", "Funchal", "Ponta Delgada"]
    distrito = np.where(zona == "Ilhas", _choice(rng, ["Funchal", "Ponta Delgada"], n), _choice(rng, distritos[:12], n))
    dist = np.round(np.where(zona == "Ilhas", rng.uniform(900, 1500, n), rng.gamma(2, 80, n) + 5), 1)
    peso = np.round(rng.lognormal(1.6, 0.9, n), 2)
    exp_date = pd.Timestamp("2023-06-01") + pd.to_timedelta(rng.integers(0, 550, n), unit="D")
    dia_sem = exp_date.dayofweek.to_numpy()
    mes = exp_date.month.to_numpy()
    pico = ((mes == 12) | ((mes == 11) & (exp_date.day.to_numpy() > 20))).astype(int)
    chuva = np.round(np.where(np.isin(mes, [11, 12, 1, 2, 3]), rng.exponential(6, n), rng.exponential(1.5, n)), 1)
    base = pd.Series(servico).map({"Expresso": 0.9, "Standard": 2.0, "Agendado": 2.8}).to_numpy()
    lat = (base + dist / 260 + pd.Series(zona).map({"Urbana": 0, "Suburbana": 0.3, "Rural": 1.1, "Ilhas": 2.2}).to_numpy()
           + pd.Series(transp).map({"TransRapido": 0, "LogiNorte": 0.25, "ExpressoSul": 0.55, "CargoPT": 0.35}).to_numpy()
           + 0.25 * (transp == "ExpressoSul") * np.isin(distrito, ["Porto", "Braga", "Bragança", "Viseu"]) * 2
           + 1.1 * pico + 0.06 * chuva + 0.9 * (dia_sem == 4) + 0.04 * peso + rng.gamma(1.3, 0.55, n))
    prometido = (pd.Series(servico).map({"Expresso": 1, "Standard": 3, "Agendado": 4}).to_numpy()
                 + np.where(zona == "Ilhas", 2, 0) + np.where(zona == "Rural", 1, 0))
    # calibra para ~17% de entregas atrasadas (atraso ⇔ round(lat) > prometido)
    shift = 0.5 - np.quantile(lat - prometido, 0.83)
    dias = np.maximum(1, np.round(lat + shift)).astype(int)
    return pd.DataFrame({
        "entrega_id": [f"EN{500000 + i}" for i in range(n)], "data_expedicao": exp_date, "transportadora": transp,
        "zona_destino": zona, "distrito_destino": distrito, "distancia_km": dist, "peso_kg": peso,
        "volume_m3": np.round(peso / rng.uniform(80, 250, n), 3), "n_volumes": 1 + rng.poisson(0.6, n),
        "tipo_servico": servico, "dia_semana": dia_sem, "mes": mes, "armazem_origem": armazem,
        "precipitacao_mm": chuva, "pico_sazonal": pico, "prazo_prometido_dias": prometido,
        "dias_entrega": dias, "atrasada": (dias > prometido).astype(int),
    })


def sensores(n_eq: int = 20, per_eq: int = 600) -> pd.DataFrame:
    rng = np.random.default_rng(1304)
    tipos = {"Prensa": (62, 4.0, 180, 1450, 42), "Compressor": (75, 3.2, 210, 2900, 55),
             "Bomba": (48, 2.4, 160, 1750, 30), "Motor": (68, 2.9, 120, 3000, 38)}
    rows = []
    for e in range(n_eq):
        tipo = list(tipos)[e % 4]
        t0, v0, p0, r0, k0 = tipos[tipo]
        idade = round(float(rng.uniform(1, 15)), 1)
        times = pd.Timestamp("2024-02-01") + pd.to_timedelta(np.arange(per_eq) * 12, unit="h")
        horas, deg = 0.0, 0.0
        cuidado = rng.uniform(0.6, 1.4)  # qualidade da manutenção deste equipamento
        next_maint = rng.uniform(1500, 3200) / cuidado
        fail_at = []
        hist = []
        for i in range(per_eq):
            horas += 12
            deg += rng.uniform(0.003, 0.008) * (1 + idade / 15)
            failed = rng.random() < max(0.0, deg - 0.6) * 0.06
            if failed or horas > next_maint:
                if failed:
                    fail_at.append(i)
                horas, deg = 0.0, 0.0
                next_maint = rng.uniform(1500, 3200) / cuidado
            carga = float(np.clip(rng.normal(72, 12), 20, 100))
            temp = t0 + 14 * deg ** 1.5 + 0.08 * (carga - 72) + rng.normal(0, 1.8)
            vib = v0 * (1 + 1.3 * deg ** 2) + rng.normal(0, 0.25)
            pres = p0 * (1 - 0.06 * deg) + rng.normal(0, 4)
            rot = r0 * (1 - 0.03 * deg) + rng.normal(0, 25)
            kw = k0 * (carga / 72) * (1 + 0.18 * deg) + rng.normal(0, 1.5)
            alarmes = int(rng.poisson(0.1 + 2.0 * deg ** 3))
            hist.append([times[i], f"EQ-{e + 1:02d}", f"L{e % 4 + 1}", tipo, round(horas, 0), round(temp, 2),
                         round(vib, 3), round(pres, 2), round(rot, 0), round(kw, 2), idade, round(carga, 1), alarmes])
        falha = np.zeros(per_eq, dtype=int)
        for f in fail_at:
            falha[max(0, f - 14):f + 1] = 1  # 14 leituras de 12h = 7 dias
        for i, h in enumerate(hist):
            rows.append(h + [int(falha[i])])
    df = pd.DataFrame(rows, columns=["data_hora", "equipamento", "linha_producao", "tipo_equipamento",
                                     "horas_desde_manutencao", "temperatura", "vibracao", "pressao", "rotacao_rpm",
                                     "consumo_energia_kw", "idade_equipamento_anos", "carga_pct", "n_alarmes_24h",
                                     "falha_7d"])
    anom = np.zeros(len(df), dtype=int)
    idx = rng.choice(len(df), size=int(0.03 * len(df)), replace=False)
    sensors = ["temperatura", "vibracao", "pressao", "consumo_energia_kw", "rotacao_rpm"]
    for j, i in enumerate(idx):
        col = sensors[j % len(sensors)]
        df.loc[i, col] = df.loc[i, col] * float(rng.choice([0.35, 1.9, 2.4]))
        anom[i] = 1
    df["anomalia"] = anom
    df.insert(0, "leitura_id", [f"R{i:07d}" for i in range(len(df))])
    return df.sort_values("data_hora").reset_index(drop=True)


# =============================================================================== PESSOAS
def colaboradores(n: int = 3000) -> pd.DataFrame:
    rng = np.random.default_rng(1405)
    dep = _choice(rng, ["Comercial", "Operações", "TI", "Finanças", "RH", "Marketing", "Logística"], n,
                  [0.2, 0.25, 0.15, 0.1, 0.06, 0.09, 0.15])
    nivel = _choice(rng, ["Júnior", "Intermédio", "Sénior", "Chefia", "Direção"], n, [0.3, 0.32, 0.22, 0.12, 0.04])
    idade = np.clip(np.round(rng.normal(38, 10, n) + pd.Series(nivel).map(
        {"Júnior": -8, "Intermédio": -2, "Sénior": 4, "Chefia": 7, "Direção": 11}).to_numpy()), 20, 66)
    genero = _choice(rng, ["F", "M"], n, [0.46, 0.54])
    antig = np.round(np.clip(rng.exponential(6, n), 0.1, np.maximum(idade - 19, 0.5)), 1)
    anos_funcao = np.round(np.minimum(antig, rng.exponential(3, n)), 1)
    anos_promo = np.round(np.minimum(antig, rng.exponential(2.5, n)), 1)
    salario = np.round(pd.Series(nivel).map({"Júnior": 1150, "Intermédio": 1650, "Sénior": 2400, "Chefia": 3300,
                                            "Direção": 5200}).to_numpy() * rng.lognormal(0, 0.15, n)
                       * np.where(dep == "TI", 1.2, 1.0), 0)
    racio_mercado = np.round(rng.normal(0.98, 0.12, n), 2)
    aval = np.clip(np.round(rng.normal(3.4, 0.8, n)), 1, 5).astype(int)
    satisf = np.clip(np.round(rng.normal(3.5, 0.9, n) - 0.3 * (racio_mercado < 0.9)), 1, 5).astype(int)
    horas_extra = np.round(np.clip(rng.gamma(1.4, 6, n) + 6 * (dep == "Operações"), 0, 80), 1)
    dist = np.round(rng.gamma(2, 9, n), 1)
    tele = _choice(rng, ["Não", "Híbrido", "Total"], n, [0.45, 0.45, 0.1])
    tele = np.where(np.isin(dep, ["Operações", "Logística"]), "Não", tele)
    faltas = rng.poisson(2 + 0.05 * horas_extra + 0.04 * dist)
    z = (-6 * (racio_mercado - 0.98) + 0.28 * anos_promo - 0.55 * (satisf - 3.5) + 0.03 * horas_extra + 0.02 * dist
         - 0.06 * antig + 0.55 * (antig < 2) + 0.4 * (tele == "Não") - 0.03 * (idade - 38) + 0.25 * (aval >= 5)
         + pd.Series(nivel).map({"Júnior": 0.3, "Direção": -0.5}).fillna(0).to_numpy()
         + rng.normal(0, 0.6, n))
    saiu = _draw(rng, z, 0.14)
    aus = rng.poisson(np.clip(0.4 + 0.22 * faltas + 0.025 * horas_extra - 0.25 * (satisf - 3.5) + 0.012 * dist, 0.05, None))
    aus = np.where(rng.random(n) < 0.02, aus + rng.integers(10, 40, n), aus)  # baixas prolongadas
    return pd.DataFrame({
        "colaborador_id": [f"COL{10000 + i}" for i in range(n)], "departamento": dep, "funcao_nivel": nivel,
        "idade": idade, "genero": genero,
        "estado_civil": _choice(rng, ["Solteiro", "Casado", "Divorciado"], n, [0.42, 0.48, 0.1]),
        "distancia_casa_km": dist, "antiguidade_anos": antig, "anos_na_funcao_atual": anos_funcao,
        "anos_desde_ultima_promocao": anos_promo, "salario_mensal": salario, "racio_salario_mercado": racio_mercado,
        "avaliacao_desempenho": aval, "satisfacao_trabalho": satisf, "horas_extra_mes": horas_extra,
        "formacoes_ultimo_ano": rng.poisson(2, n), "teletrabalho": tele, "n_faltas_12m": faltas,
        "dias_ausencia_prox_trimestre": aus, "saiu_12m": saiu,
    })


def tickets() -> pd.DataFrame:
    rng = np.random.default_rng(1506)
    dates = pd.date_range("2023-01-01", "2024-12-31", freq="D")
    t = np.arange(len(dates))
    lam = (20 * (1 + 0.1 * t / 365) * np.array([1.35, 1.15, 1.05, 1.0, 0.95, 0.45, 0.3])[dates.dayofweek]
           * np.where(dates.day <= 5, 1.3, 1.0) * np.where(dates.month == 8, 0.85, 1.0)
           * np.where(dates.isin(PT_HOLIDAYS), 0.4, 1.0))
    incident_days = rng.choice(len(dates), 6, replace=False)
    lam[incident_days] *= 2.8
    counts = rng.poisson(lam)
    rows = []
    k = 0
    for d, c in zip(dates, counts):
        for _ in range(int(c)):
            canal = rng.choice(["Telefone", "Email", "Chat", "App", "Loja"], p=[0.38, 0.22, 0.2, 0.12, 0.08])
            categ = rng.choice(["Faturação", "Técnico", "Comercial", "Reclamação", "Informação"],
                               p=[0.3 if d.day <= 5 else 0.2, 0.3, 0.15, 0.15, 0.2 if d.day > 5 else 0.1])
            prio = rng.choice(["Baixa", "Média", "Alta", "Urgente"], p=[0.3, 0.42, 0.2, 0.08])
            nivel = rng.choice(["N1", "N2", "N3"], p=[0.6, 0.3, 0.1])
            seg = rng.choice(["Particular", "PME", "Empresa"], p=[0.7, 0.2, 0.1])
            mu = (np.log(6) + {"Técnico": 0.9, "Reclamação": 0.7, "Faturação": 0.3, "Comercial": 0.0, "Informação": -0.6}[categ]
                  + {"Urgente": -0.8, "Alta": -0.3, "Média": 0.0, "Baixa": 0.3}[prio]
                  + {"Chat": -0.4, "Telefone": -0.2, "Email": 0.4, "App": 0.0, "Loja": 0.1}[canal]
                  + {"N1": 0.0, "N2": 0.35, "N3": 0.8}[nivel] + (-0.2 if seg == "Empresa" else 0.0))
            tres = float(np.round(rng.lognormal(mu, 0.55), 1))
            inter = int(1 + rng.poisson(tres / 8))
            rows.append((f"TK{800000 + k}", d, canal, categ, prio, seg,
                         rng.choice(["Internet", "Móvel", "TV", "Pacote"]), inter,
                         float(np.round(rng.exponential(2 if prio in ("Alta", "Urgente") else 6), 1)), nivel,
                         int(rng.random() < 0.06 + 0.002 * tres), tres, int(tres > 48 or nivel == "N3")))
            k += 1
    return pd.DataFrame(rows, columns=["ticket_id", "data_abertura", "canal", "categoria", "prioridade",
                                       "segmento_cliente", "produto", "n_interacoes", "primeira_resposta_horas",
                                       "agente_nivel", "reaberto", "tempo_resolucao_horas", "escalado"])


def nps(n: int = 4000) -> pd.DataFrame:
    rng = np.random.default_rng(1607)
    qual = np.clip(np.round(rng.normal(3.8, 0.9, n)), 1, 5)
    atend = np.clip(np.round(rng.normal(3.7, 1.0, n)), 1, 5)
    preco = np.clip(np.round(rng.normal(3.1, 1.0, n)), 1, 5)
    app = np.clip(np.round(rng.normal(3.5, 1.1, n)), 1, 5)
    contactos = rng.poisson(1.2, n)
    tres = np.round(rng.gamma(2, 12, n), 1)
    fat = rng.poisson(0.35, n)
    avaria = rng.poisson(0.4, n)
    antig = np.clip(rng.exponential(36, n).astype(int) + 1, 1, 200)
    latent = (1.0 * (qual - 3.8) + 0.8 * (atend - 3.7) + 0.6 * (preco - 3.1) + 0.35 * (app - 3.5)
              - 0.9 * (fat - 0.35) - 0.8 * (avaria - 0.4) - 0.25 * (contactos - 1.2) - 0.015 * (tres - 24)
              + 0.003 * (antig - 37) + rng.normal(0, 0.9, n))
    nota = np.clip(np.round(7.3 + 1.25 * latent), 0, 10).astype(int)
    cat = np.where(nota >= 9, "Promotor", np.where(nota >= 7, "Passivo", "Detrator"))
    datas = pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 366, n), unit="D")
    return pd.DataFrame({
        "resposta_id": [f"N{60000 + i}" for i in range(n)], "data_resposta": datas,
        "cliente_id": [f"C{100000 + int(i)}" for i in rng.integers(0, 6000, n)],
        "segmento": _choice(rng, ["Particular", "PME", "Empresa"], n, [0.72, 0.2, 0.08]),
        "regiao": _choice(rng, REGIOES, n, REGIOES_P),
        "canal_principal": _choice(rng, ["Loja", "Online", "App", "Telefone"], n),
        "antiguidade_meses": antig, "n_contactos_apoio_6m": contactos, "tempo_medio_resolucao_h": tres,
        "problemas_faturacao_6m": fat, "avaria_servico_6m": avaria, "preco_percebido": preco,
        "qualidade_servico": qual, "facilidade_app": app, "atendimento": atend, "nota_nps": nota,
        "categoria_nps": cat,
    })


# =============================================================================== CATÁLOGO DEMO
DEMO_CATALOG: dict[str, dict] = {
    "ws-comercial": {
        "name": "Comercial & Marketing",
        "description": "Modelos semânticos de CRM, campanhas e vendas a retalho.",
        "datasets": {
            "ds-crm": {"name": "CRM e Clientes", "description": "Clientes, leads e resultados de campanhas.",
                       "tables": {"Clientes": clientes, "Leads": leads, "Campanhas": campanhas}},
            "ds-vendas": {"name": "Vendas e Retalho", "description": "Vendas diárias, talões e stock por loja.",
                          "tables": {"VendasDiarias": vendas_diarias, "LinhasTalao": linhas_talao, "Stock": stock}},
        },
    },
    "ws-financas": {
        "name": "Finanças & Risco",
        "description": "Faturação, tesouraria, despesas, crédito e transações.",
        "datasets": {
            "ds-financas": {"name": "Finanças", "description": "Contas a receber, tesouraria e despesas.",
                            "tables": {"Faturas": faturas, "FluxosCaixa": fluxos_caixa, "Despesas": despesas}},
            "ds-risco": {"name": "Risco", "description": "Pedidos de crédito e transações com cartão.",
                         "tables": {"Credito": credito, "Transacoes": transacoes}},
        },
    },
    "ws-operacoes": {
        "name": "Operações & Logística",
        "description": "Entregas e telemetria de equipamentos.",
        "datasets": {
            "ds-logistica": {"name": "Logística", "description": "Ordens de entrega por transportadora.",
                             "tables": {"Entregas": entregas}},
            "ds-fabrica": {"name": "Fábrica", "description": "Leituras de sensores dos equipamentos.",
                           "tables": {"Sensores": sensores}},
        },
    },
    "ws-pessoas": {
        "name": "Pessoas & Cliente",
        "description": "Recursos humanos e apoio ao cliente.",
        "datasets": {
            "ds-rh": {"name": "Recursos Humanos", "description": "Ficha de colaborador (dados pseudonimizados).",
                      "tables": {"Colaboradores": colaboradores}},
            "ds-cliente": {"name": "Apoio ao Cliente", "description": "Tickets e respostas de NPS.",
                           "tables": {"Tickets": tickets, "NPS": nps}},
        },
    },
}


@lru_cache(maxsize=32)
def get_table(table: str) -> pd.DataFrame:
    for ws in DEMO_CATALOG.values():
        for ds in ws["datasets"].values():
            gen: Callable[[], pd.DataFrame] | None = ds["tables"].get(table)
            if gen is not None:
                return gen()
    raise KeyError(table)
