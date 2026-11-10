"""Regressoes ciclo04: limites comunicados e elegibilidade comercial. Dados sinteticos."""
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from bi_ml import basket_roi as br, cli, planning
from bi_ml.contract import ContractError, DataQualityWarning


def orders():
    groups = [(100, 'AB'), (50, 'A'), (50, 'B'), (200, 'C')]
    rows = []
    n = 0
    for count, products in groups:
        for _ in range(count):
            rows.extend({'order_id': str(n), 'product_id': p} for p in products)
            n += 1
    return pd.DataFrame(rows)


def test_no_business_threshold_is_exploration_only():
    with pytest.warns(DataQualityWarning, match='limiar de efeito'):
        pairs = br.basket_pairs(orders())
    assert pairs.significativo.any(), 'o teste tem de incluir associacao significativa'
    assert pairs.material.isna().all() and not pairs.elegivel.any()
    assert set(pairs.loc[pairs.significativo, 'motivo_exclusao']) == {'limiar_material_nao_declarado'}
    assert br.recommend(pairs, 'A').empty
    material = br.basket_pairs(orders(), min_lift=1.5)
    assert br.recommend(material, 'A').sugerir.tolist() == ['B']
    assert br.recommend(br.basket_pairs(orders(), min_lift=2.0), 'A').empty


def test_legacy_table_cannot_bypass_materiality():
    pairs = br.basket_pairs(orders(), min_lift=1.5).drop(columns='elegivel')
    with pytest.raises(ContractError, match='limiar de negocio'):
        br.recommend(pairs, 'A')


def test_no_pairs_returns_empty_recommendations():
    pairs = br.basket_pairs(orders(), min_count=500)
    result = br.recommend(pairs, 'A')
    assert result.empty and list(result.columns) == ['sugerir', 'confianca', 'lift']


@pytest.mark.parametrize('valid', [True, False])
def test_holdout_warning_survives_positive_and_abstained_decisions(valid):
    result = dict(incremental=1000, ic=(900, 1100), ic_racio=(850, 1150),
                  valido=valid, verificavel=True, avisos=[], holdout=True)
    d = planning.roi_decision(result, 100, .5, desenho='aleatorizado')
    assert d['decisao'] == ('positivo' if valid else 'nao_afirmar')
    assert not d['pode_decidir_renovacao'] and d['autorizacao'] == 'humana_obrigatoria'
    assert any('27,5%' in a and 'K=1' in a and 'exploratoria' in a for a in d['avisos'])
    assert result['avisos'] == []  # nao alterar o objeto do chamador


@pytest.mark.parametrize('cmd', ['abc-xyz', 'cohorts'])
@pytest.mark.parametrize('declared', [False, True])
def test_revenue_outputs_have_fiscal_context(tmp_path, cmd, declared):
    data = tmp_path / 'data'; data.mkdir()
    sales = pd.DataFrame([dict(date=d, order_id=str(i), product_id='A', customer_id='C', qty=1, revenue=2)
                          for i, d in enumerate(pd.date_range('2024-01-01', '2024-06-30'))])
    sales.to_csv(data / 'sales.csv', index=False)
    if declared:
        (data / 'csv_options.json').write_text(json.dumps({'revenue_basis':'sem_imposto', 'currency':'EUR'}))
    out = tmp_path / 'out'
    args = [cmd, '--data', str(data), '--out', str(out)]
    if cmd == 'abc-xyz': args += ['--start', '2024-01-01', '--end', '2024-07-01']
    assert cli.main(args) == 0
    r = json.loads((out / f'relatorio_{cmd}.json').read_text())
    warnings = r['qualidade_dados']['avisos_fiscais']
    if declared:
        assert not warnings
    else:
        assert any('base fiscal' in a for a in warnings)
        assert any('moeda nao declarada' in a for a in warnings)


def test_generated_basket_runs_outside_project_and_keeps_guard(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import build_skills
    build_skills.build(str(tmp_path / 'skills'))
    basket = tmp_path / 'skills' / 'bi-ml-basket-analysis'
    if not basket.exists():
        basket = next(p.parent for p in (tmp_path/'skills').glob('*/SKILL.md')
                      if 'basket_pares.csv' in p.read_text())
    doc = (basket / 'SKILL.md').read_text()
    assert 'elegivel=False' in doc and 'elegivel = significativo, com aviso' not in doc
    roi = (tmp_path/'skills'/'bi-ml-roi-incremental'/'SKILL.md').read_text()
    assert '27,5%' in roi and 'K=1' in roi
    data = tmp_path/'data'; data.mkdir()
    sales = orders().assign(date='2024-01-01', customer_id='C', qty=1, revenue=2)
    sales.to_csv(data/'sales.csv', index=False)
    out = tmp_path/'out'
    p = subprocess.run([sys.executable, str(basket/'scripts'/'run.py'), 'basket', '--data', str(data),
                        '--out', str(out)], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    report = json.loads((out/'relatorio_basket.json').read_text())
    assert report['pares_significativos'] > 0 and report['pares_elegiveis'] == 0
