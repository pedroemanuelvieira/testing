"""Gerador de dados sinteticos COM VERDADE CONHECIDA, para testar os modulos.

Nunca usar dados reais da empresa na pasta partilhada: tudo aqui e sintetico.
Verdades injetadas: churn por cliente, rupturas de stock, uplift de campanha,
desvio de preco/volume, pares de produtos associados.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def make(seed=7, n_cust=1500, n_prod=40, days=730, start="2024-01-01"):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=days, freq="D")
    prod = pd.DataFrame({
        "product_id": [f"P{i:03d}" for i in range(n_prod)],
        "price": rng.uniform(5, 80, n_prod).round(2),
        "base_rate": rng.gamma(2.0, 3.0, n_prod),  # procura media diaria
    })
    prod["cost"] = (prod["price"] * rng.uniform(0.5, 0.8, n_prod)).round(2)

    # --- clientes: taxa de compra e hazard de churn (verdade) ---
    cust = pd.DataFrame({
        "customer_id": [f"C{i:05d}" for i in range(n_cust)],
        "freq": rng.gamma(2.0, 0.02, n_cust) + 0.005,       # encomendas/dia
        "churn_day": np.where(rng.random(n_cust) < 0.45,
                              rng.integers(120, days, n_cust), 10**6),
        "first_day": rng.integers(0, days // 2, n_cust),
    })

    # --- stock com rupturas injetadas ---
    stock = []
    ruptura = {}  # (product, day_index) -> True
    for p in prod.product_id:
        s = np.full(days, 200.0)
        for _ in range(3):
            d0 = rng.integers(60, days - 30)
            L = rng.integers(5, 15)
            s[d0:d0 + L] = 0
            for k in range(d0, d0 + L):
                ruptura[(p, k)] = True
        stock.append(pd.DataFrame({"date": dates, "product_id": p, "stock_qty": s}))
    stock = pd.concat(stock, ignore_index=True)

    # --- pares associados (verdade): P000->P001, P002->P003 ---
    pairs = {"P000": "P001", "P002": "P003", "P004": "P005"}

    rows, oid = [], 0
    dow = np.array([1.0, 1.05, 1.1, 1.1, 1.2, 0.7, 0.5])
    for _, c in cust.iterrows():
        ndays = np.arange(int(c.first_day), min(days, int(c.churn_day)))
        buys = ndays[rng.random(len(ndays)) < c.freq]
        for d in buys:
            oid += 1
            n_items = 1 + rng.poisson(1.2)
            chosen = list(rng.choice(prod.product_id, size=min(n_items, 4), replace=False,
                                     p=(prod.base_rate / prod.base_rate.sum())))
            for p0 in list(chosen):
                if p0 in pairs and rng.random() < 0.6 and pairs[p0] not in chosen:
                    chosen.append(pairs[p0])
            for p in chosen:
                if ruptura.get((p, d)):  # sem stock -> venda perdida (nao observada)
                    continue
                pr = prod.set_index("product_id").loc[p]
                q = 1 + rng.poisson(0.8)
                season = 1 + 0.2 * np.sin(2 * np.pi * d / 365)
                if rng.random() < season * dow[(d % 7)] / 1.3:
                    rows.append((dates[d], f"O{oid:07d}", c.customer_id, p, q,
                                 round(q * pr.price * rng.uniform(0.95, 1.0), 2),
                                 round(q * pr.cost, 2)))
    sales = pd.DataFrame(rows, columns=["date", "order_id", "customer_id",
                                        "product_id", "qty", "revenue", "cost"])

    # --- campanhas: uplift verdadeiro de +25% no produto alvo durante a campanha ---
    camp = pd.DataFrame({
        "campaign_id": ["K1", "K2"],
        "start": pd.to_datetime(["2025-03-01", "2025-07-01"]),
        "end": pd.to_datetime(["2025-03-31", "2025-07-31"]),
        "spend": [3000.0, 5000.0],
        "product_id": ["P010", "P011"],
    })
    extra = []
    for _, k in camp.iterrows():
        pr = prod.set_index("product_id").loc[k.product_id]
        for d in pd.date_range(k.start, k.end):
            n = rng.poisson(pr.base_rate * 0.25)
            for _ in range(n):
                oid += 1
                extra.append((d, f"O{oid:07d}", cust.customer_id.sample(1, random_state=int(rng.integers(1e9))).iloc[0],
                              k.product_id, 1, round(pr.price, 2), round(pr.cost, 2)))
    sales = pd.concat([sales, pd.DataFrame(extra, columns=sales.columns)], ignore_index=True)

    truth = {"churn_day": cust.set_index("customer_id")["churn_day"],
             "ruptura": ruptura, "pairs": pairs, "prod": prod}
    return sales, stock, camp, truth


def make_signal(seed=1, n_prod=20, years=3.5, season_amp=0.5, trend=0.25):
    """Mundo de PROCURA com sinal forte (sazonalidade anual + tendencia + dia da semana).

    v0.4: serve para provar que a selecao de metodo de previsao encontra sinal quando ele existe
    (WAPE ~0,17 vs ~0,30 da media de 13 semanas) e para testar a calibracao. Vendas diarias por produto.
    """
    rng = np.random.default_rng(seed)
    days = pd.date_range("2022-01-03", periods=int(365 * years), freq="D")
    dow = np.array([1.1, 1.1, 1.1, 1.1, 1.2, 0.5, 0.4])[days.dayofweek]
    t = np.arange(len(days)) / 365
    rows = []
    for i in range(n_prod):
        base = rng.gamma(3, 2.0) + 1
        lam = (base * (1 + season_amp * np.sin(2 * np.pi * t + rng.uniform(0, 2 * np.pi)))
               * (1 + trend * (t - t.mean()) * rng.choice([-1, 1])))
        q = rng.poisson(np.clip(lam * dow, 0.05, None))
        for d, qq in zip(days, q):
            if qq > 0:
                rows.append((d, f"O{i}_{d.value}", f"C{rng.integers(500)}", f"S{i:02d}", int(qq), float(qq) * 10))
    return pd.DataFrame(rows, columns=["date", "order_id", "customer_id", "product_id", "qty", "revenue"])
