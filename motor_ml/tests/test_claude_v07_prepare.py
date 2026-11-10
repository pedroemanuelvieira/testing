import warnings
import numpy as np, pandas as pd, pytest
from bi_ml import prepare
from bi_ml.contract import DataQualityWarning


def _extract(n=120):
    rows = []
    for o in range(n):
        for p in ("A", "B", "C", "D", "E", "F")[o % 6: o % 6 + 2]:
            rows.append((f"2025-01-{1 + o % 28:02d}", f"O{o}", p, 2, 20.0, 12.0, f"C{o % 15}"))
    df = pd.DataFrame(rows, columns=["date", "order_id", "product_id", "qty", "revenue", "cost", "customer_id"])
    ship = df.drop_duplicates("order_id").assign(product_id="PORTES", qty=1, revenue=5.0, cost=3.0)
    return pd.concat([df, ship], ignore_index=True)


def test_freight_line_is_flagged_and_excluded_with_exact_reconciliation():
    ext = _extract()
    with pytest.warns(DataQualityWarning, match="PORTES"):
        s, _, rel = prepare.prepare_sales(ext)
    assert rel["possivel_nao_produto"] == ["PORTES"] and (s.product_id == "PORTES").any()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DataQualityWarning)
        s2, _, rel2 = prepare.prepare_sales(ext, exclude_products=["PORTES"])
    assert not (s2.product_id == "PORTES").any()
    assert abs(rel2["receita_liquida"] + rel2["nao_produto_valor"] - ext.revenue.sum()) < 1e-6


def test_dropped_duplicates_still_reconcile():
    ext = _extract()
    ext = pd.concat([ext, ext.iloc[:10]], ignore_index=True)
    s, _, rel = prepare.prepare_sales(ext, duplicates="drop", exclude_products=["PORTES"])
    assert rel["duplicados_removidos"] == 10 and rel["reconciliado_com_entrada"]
    assert abs(rel["receita_liquida"] + rel["nao_produto_valor"] + rel["duplicados_valor"] - ext.revenue.sum()) < 1e-6
