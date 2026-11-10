"""Ponte para o motor analítico bi_ml 0.10.0 (pasta motor_ml/), supervisionado pelo Tetsuo (901).

  python -m foundry ml <comando> --data PASTA --out PASTA [opções do bi_ml]
      comandos: check, lifecycle, churn, forecast, stockout, variance, basket, cohorts, abc-xyz, roi-series, all
  python -m foundry ml demo [--out out/ml/demo]     corre os módulos com dados sintéticos (demonstração)
  python -m foundry ml versao

Requer pandas, numpy, scipy e scikit-learn: python -m pip install -r motor_ml/requirements.txt
Código de saída 2 = erro de dados com mensagem (reportar, não contornar); 3 = dependências em falta.
"""
from __future__ import annotations
import importlib.util
import os
import sys
import tempfile
from .. import config

MOTOR = config.RAIZ / "motor_ml"


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "ajuda"):
        print(__doc__)
        return 0
    em_falta = [m for m in ("pandas", "numpy", "scipy", "sklearn") if importlib.util.find_spec(m) is None]
    if em_falta:
        print(f"Motor ML indisponível: faltam {', '.join(em_falta)}.\nInstalar com: python -m pip install -r motor_ml/requirements.txt")
        return 3
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    sys.path.insert(0, str(MOTOR))
    import bi_ml
    from bi_ml import cli
    if argv[0] == "versao":
        print(f"bi_ml {bi_ml.__version__}")
        return 0
    if argv[0] == "demo":
        from bi_ml import synth
        out = argv[argv.index("--out") + 1] if "--out" in argv and argv.index("--out") + 1 < len(argv) else str(config.RAIZ / "out" / "ml" / "demo")
        dados = tempfile.mkdtemp(prefix="foundry_ml_demo_")
        vendas, stock, invest, _ = synth.make()
        vendas.to_csv(os.path.join(dados, "sales.csv"), index=False)
        stock.to_csv(os.path.join(dados, "stock.csv"), index=False)
        invest.to_csv(os.path.join(dados, "invest.csv"), index=False)
        print(f"Dados SINTÉTICOS em {dados} · resultados em {out}")
        return cli.main(["all", "--data", dados, "--out", out]) or 0
    return cli.main(argv) or 0
