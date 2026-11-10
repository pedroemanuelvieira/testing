"""Compatibilidade: equivale a `python -m bi_ml.cli all`. Sem --data usa dados sinteticos (demonstracao)."""
import argparse, os, sys, tempfile
import pandas as pd
from bi_ml import cli, synth


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data"); ap.add_argument("--out", default="saida")
    a = ap.parse_args()
    data = a.data
    if not data:
        data = tempfile.mkdtemp(prefix="bi_ml_demo_")
        sales, stock, invest, _ = synth.make()
        sales.to_csv(os.path.join(data, "sales.csv"), index=False); stock.to_csv(os.path.join(data, "stock.csv"), index=False)
        invest.to_csv(os.path.join(data, "invest.csv"), index=False)
    return cli.main(["all", "--data", data, "--out", a.out])


if __name__ == "__main__":
    sys.exit(main())
