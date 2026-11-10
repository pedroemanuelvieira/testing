"""Grok ciclo 02 (v0.6): testes contra verdade injetada para OBJ-003, 026, 027, 028, 029, 030."""
import json
import numpy as np
import pandas as pd
import pytest
from bi_ml import prepare, planning, cli
from bi_ml.abc_xyz import classify
from bi_ml.contract import ContractError

COLS = ['date', 'order_id', 'customer_id', 'product_id', 'qty', 'revenue']


def _shock(seed, shock=20.0, n=160, k=130):
    rng = np.random.default_rng(seed)
    c = rng.normal(100, 5, (n, 3)); y = c.sum(1) * 0.5 + rng.normal(0, 3, n); y[k:] += shock
    return y, c, k


@pytest.mark.parametrize('seed', [0, 1, 2])
def test_obj003_external_shock_zero_effect_is_not_causal(seed):
    y, c, k = _shock(seed)
    res = planning.controlled_incremental_ci(y, c, k)
    d = planning.roi_decision(res, 100, .5)
    assert d['decisao'] == 'indicio_estatistico_positivo'       # estatistica ve o choque (inevitavel)
    assert d['causal'] is False and d['pode_decidir_renovacao'] is False
    assert any('NAO atribuivel' in a for a in d['avisos'])


def test_obj003_declared_design_allows_decision_and_bad_design_rejected():
    # v0.7 (Claude): declarar o desenho sem que o estimador tenha sido corrido com holdout deixa de desbloquear a decisao
    y, c, k = _shock(0)
    res = planning.controlled_incremental_ci(y, c, k)
    with pytest.raises(ContractError):
        planning.roi_decision(res, 100, .5, desenho='aleatorizado')
    # v0.9 (Grok, OBJ-003): alterado DE PROPOSITO. Com holdout, a decisao exige concordancia do racio, e o pacote
    # nunca autoriza renovar (pode_decidir_renovacao sempre False); evidencia_para_revisao vai para decisao humana.
    h = dict(incremental=1000, ic=(900, 1100), ic_racio=(850, 1150), valido=True, verificavel=True, avisos=[], holdout=True)
    d = planning.roi_decision(h, 100, .5, desenho='aleatorizado')
    assert d['decisao'] == 'positivo' and d['evidencia_para_revisao'] and d['pode_decidir_renovacao'] is False
    with pytest.raises(ContractError):
        planning.roi_decision(h, 100, .5, desenho='confio')


def test_obj026_unverifiable_still_abstains_even_with_design():
    r = dict(incremental=1000, ic=(900, 1100), valido=True, verificavel=False, avisos=[], holdout=True)
    assert planning.roi_decision(r, 100, .5, desenho='aleatorizado')['decisao'] == 'nao_afirmar'


def _sales_dir(tmp_path):
    pd.DataFrame(dict(date=['2025-01-01'], order_id=['1'], customer_id=['C'], product_id=['P'], qty=[1],
                      revenue=[1])).to_csv(tmp_path / 'sales.csv', index=False)


def test_obj027_roi_cli_full_command_end_to_end(tmp_path):
    _sales_dir(tmp_path)
    y, c, k = _shock(1)
    dates = pd.date_range('2023-01-02', periods=len(y), freq='W-MON')
    s = pd.DataFrame({'date': dates.strftime('%Y-%m-%d'), 'outcome': y, **{f'control_{i+1}': c[:, i] for i in range(3)}})
    f = tmp_path / 'series.csv'; s.to_csv(f, index=False)
    out = tmp_path / 'out'
    rc = cli.main(['roi-series', '--data', str(tmp_path), '--out', str(out), '--series', str(f),
                   '--intervention-date', str(dates[k].date()), '--spend', '100', '--margin-rate', '0.5'])
    assert rc == 0
    rep = json.load(open(out / 'relatorio_roi-series.json'))
    assert rep['decisao'] == 'indicio_estatistico_positivo' and rep['causal'] is False
    rc = cli.main(['roi-series', '--data', str(tmp_path), '--out', str(out), '--series', str(f),
                   '--intervention-date', '2030-01-01', '--spend', '100', '--margin-rate', '0.5'])
    assert rc == 2                                               # data fora da serie: falha explicita


def test_legacy_roi_not_run_by_default(tmp_path):
    from bi_ml import synth
    sales, stock, invest, _ = synth.make()
    sales.to_csv(tmp_path / 'sales.csv', index=False); invest.to_csv(tmp_path / 'invest.csv', index=False)
    out = tmp_path / 'o'
    assert cli.main(['all', '--data', str(tmp_path), '--out', str(out)]) == 0
    assert not (out / 'roi_campanhas_legado.csv').exists()


def test_obj028_old_product_without_sales_in_first_month_is_not_U():
    rows = []
    for m in range(1, 13):
        rows.append([f'2024-{m:02d}-05', f'a{m}', 'K', 'P1', 10, 100])
        if m not in (4, 5): rows.append([f'2024-{m:02d}-05', f'b{m}', 'K', 'P2', 10, 100])
    rows.append(['2024-06-05', 'n', 'K', 'NEW', 5, 50])
    r = classify(pd.DataFrame(rows, columns=COLS), '2024-04-01', '2024-10-01').set_index('product_id')
    assert r.loc['P2', 'xyz'] != 'U' and not r.loc['P2', 'history_incomplete']
    assert r.loc['NEW', 'xyz'] == 'U'


def test_obj029_repeated_seasonality_is_predictable():
    rng = np.random.default_rng(0); pat = [1, 1, 1, 2, 5, 20, 30, 20, 5, 2, 1, 1]; rows = []
    for y in (2022, 2023, 2024):
        for m in range(1, 13):
            q = pat[m - 1] * 10 * (1 + rng.normal(0, .05))
            rows.append([f'{y}-{m:02d}-05', f's{y}{m}', 'K', 'S', q, q * 10])
            rows.append([f'{y}-{m:02d}-05', f'r{y}{m}', 'K', 'R', rng.choice([0.01, 300]), 1000])
    r = classify(pd.DataFrame(rows, columns=COLS), '2022-01-01', '2025-01-01').set_index('product_id')
    assert r.loc['S', 'xyz'] == 'Z' and r.loc['S', 'xyz_sazonal'] == 'X'   # sazonal repetido: previsivel
    assert r.loc['R', 'xyz_sazonal'] == 'Z'                               # aleatorio continua Z
    short = classify(pd.DataFrame(rows, columns=COLS), '2024-01-01', '2025-01-01')
    assert (short.xyz_sazonal == 'NA').all()


def test_obj030_discounts_and_credit_notes_reconcile_and_dont_inflate_returns():
    d = pd.DataFrame(dict(date=['2025-01-02'] * 5, order_id=['1', '1', '2', '3', '4'], customer_id=['C'] * 5,
                          product_id=['P'] * 5, qty=[10, 1, -2, 0, 0], revenue=[100, -10, -20, -15, 0]))
    s, ret, rel = prepare.prepare_sales(d)
    assert rel['devolucoes_unidades'] == 2 and rel['devolucoes_valor'] == 20     # v0.5 dava 3 unidades
    assert rel['ajustes_valor_liquido'] == -25 and rel['ajustes_valor_linhas'] == 2
    assert rel['receita_bruta'] == 100 and rel['receita_liquida'] == d.revenue.sum() == 55
    assert len(ret.attrs['ajustes_valor']) == 2 and rel['linhas_qty_zero_removidas'] == 1
    d2 = d.copy(); d2.loc[3, 'qty'] = 0; d2.loc[3, 'revenue'] = 7                  # nota de debito so valor
    _, _, rel2 = prepare.prepare_sales(d2)
    assert rel2['receita_liquida'] == d2.revenue.sum()
