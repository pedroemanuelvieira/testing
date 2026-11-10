"""Monthly plan variance and descriptive cohort retention. No causal claims."""
import numpy as np
import pandas as pd
from scipy.stats import norm
from .contract import ContractError, validate_sales, known_customers, normalize_ids


def plan_variance(sales, plan, asof, kind='budget', allow_empty_months=False):
    """Closed months only; missing plan is unknown, not zero. Plan grain: month/product.
    Requires period, product_id, planned_qty, planned_revenue. Forecast additionally
    requires issued_at strictly before the planned month, avoiding hindsight revisions.
    """
    sales = validate_sales(sales)
    if kind not in ('budget', 'forecast'):
        raise ContractError('kind deve ser budget ou forecast')
    required = ['period','product_id','planned_qty','planned_revenue']
    if not set(required).issubset(plan):
        raise ContractError('plan: faltam colunas '+str(required))
    p = plan.copy()
    p['product_id'] = normalize_ids(p['product_id'])   # v0.4: mesmo formato de ids que as vendas
    if p['product_id'].isna().any():
        raise ContractError('plan: product_id vazio')
    p['period'] = pd.to_datetime(p.period).dt.to_period('M').dt.to_timestamp()
    if p[required].isna().any().any() or p.duplicated(['period','product_id']).any():
        raise ContractError('plan: nulos ou duplicados')
    for c in ['planned_qty','planned_revenue']:
        p[c] = pd.to_numeric(p[c], errors='raise')
        if not np.isfinite(p[c]).all() or (p[c]<0).any():
            raise ContractError('plan: valores invalidos')
    if kind == 'forecast':
        if 'issued_at' not in p:
            raise ContractError('forecast: issued_at obrigatorio')
        issued = pd.to_datetime(p.issued_at)
        if issued.isna().any() or (issued >= p.period).any():
            raise ContractError('forecast: emissao deve anteceder periodo')
    closed = pd.Timestamp(asof).to_period('M').to_timestamp()
    s = sales[sales.date < closed].copy()
    s['period'] = s.date.dt.to_period('M').dt.to_timestamp()
    a = s.groupby(['period','product_id'],as_index=False).agg(actual_qty=('qty','sum'),actual_revenue=('revenue','sum'))
    # v0.3 (Grok): perda de cobertura. Um mes do plano sem NENHUMA venda no extrato
    # e quase sempre extrato incompleto, nao venda zero; na v0.2 virava -100% silencioso.
    pp = p[p.period < closed]
    covered = set(s.period.unique())
    gaps = sorted(set(pp.period.unique()) - covered)
    if gaps and not allow_empty_months:
        raise ContractError('sales: extrato sem qualquer venda em meses do plano '
                            + str([str(g.date()) for g in gaps])
                            + ' (confirmar cobertura ou usar allow_empty_months=True)')
    if len(pp) and not set(pp.product_id) & set(a.product_id):
        raise ContractError('plan: nenhum product_id do plano coincide com as vendas (formato de codigos?). '
                            f'Plano: {sorted(set(pp.product_id))[:5]}; vendas: {sorted(set(a.product_id))[:5]}')
    out = a.merge(pp,on=['period','product_id'],how='outer',indicator=True)
    # Caller certifies sales extract covers all closed months, including zero-sales months.
    for c in ['actual_qty','actual_revenue']:
        out[c] = out[c].fillna(0)
    for unit in ['qty','revenue']:
        out['delta_'+unit] = out['actual_'+unit]-out['planned_'+unit]
        out['delta_pct_'+unit] = out['delta_'+unit]/out['planned_'+unit].replace(0,np.nan)
    out['status'] = out['_merge'].map({'left_only':'missing_plan','right_only':'no_sales','both':'matched'}).astype(str)
    out['kind'] = kind
    return out.drop(columns='_merge')


def cohort_retention(sales, asof):
    """First OBSERVED purchase cohorts; only fully closed months. Descriptive repeat
    purchase, not permanent survival. Requires complete transaction observation.
    """
    s = known_customers(validate_sales(sales))  # v0.4: anonimos excluidos com aviso
    end = pd.Timestamp(asof).to_period('M')
    s = s[s.date < end.start_time].copy()
    if s.empty:
        return pd.DataFrame(columns=['cohort','month_age','customers','active','retention','revenue'])
    s['month'] = s.date.dt.to_period('M')
    first = s.groupby('customer_id').month.min()
    s['cohort'] = s.customer_id.map(first)
    rows=[]
    for cohort, members in first.groupby(first):
        group = s[s.customer_id.isin(members.index)]
        for age,month in enumerate(pd.period_range(cohort,end-1,freq='M')):
            window=group[group.month==month]
            active=window.customer_id.nunique()
            rows.append(dict(cohort=str(cohort),month_age=age,customers=len(members),active=active,retention=active/len(members),revenue=float(window.revenue.sum())))
    return pd.DataFrame(rows)


def controlled_incremental(outcome, controls, intervention_index):
    """Experimental counterfactual: OLS on pre-period, trend and external controls.
    Outcome MUST aggregate target plus known cannibalised products. Controls MUST
    be unaffected by treatment. Returns point estimate only, no causal guarantee/CI.
    Ordered regular-time arrays, no missing observations; not integrated into runner.
    """
    y=np.asarray(outcome,dtype=float); c=np.asarray(controls,dtype=float)
    if c.ndim==1:c=c[:,None]
    k=intervention_index
    if y.ndim!=1 or c.ndim!=2 or len(y)!=len(c) or not 10<=k<len(y):
        raise ContractError('ROI: dimensions or pre-period invalid')
    if not np.isfinite(y).all() or not np.isfinite(c).all():
        raise ContractError('ROI: nonfinite input')
    x=np.column_stack([np.ones(len(y)),np.arange(len(y))/k,c])
    if k<=x.shape[1]+2 or np.linalg.matrix_rank(x[:k])<x.shape[1]:
        raise ContractError('ROI: pre-period design not identifiable')
    beta=np.linalg.lstsq(x[:k],y[:k],rcond=None)[0]
    pred=x[k:]@beta
    return {'incremental':float((y[k:]-pred).sum()),'counterfactual':pred,
            'method':'experimental_preperiod_ols_trend_controls'}



def _ratio_incremental(y, c, k):
    """v0.9 (Grok, OBJ-003): estimador de racio SEM intercepto nem tendencia, y ~ c @ b no pre.
    So faz sentido com holdout aleatorizado (tratados e holdout partilham a dinamica): um choque
    MULTIPLICATIVO comum cancela-se aqui, mas enviesa o OLS com intercepto/tendencia (residuo ~12% do choque)."""
    if k <= c.shape[1] + 2 or np.linalg.matrix_rank(c[:k]) < c.shape[1]:
        raise ContractError('ROI: racio nao identificavel')
    b = np.linalg.lstsq(c[:k], y[:k], rcond=None)[0]
    return float((y[k:] - c[k:] @ b).sum())


def _placebo_time_ci(est_fn, y, c, k, alpha, min_train):
    H = len(y) - k; errs = []
    for j in range(min_train, k - H + 1):
        try:
            errs.append(est_fn(y[:j + H], c[:j + H], j))
        except ContractError:
            continue
    errs = np.sort(np.array(errs)); n = len(errs)
    base = est_fn(y, c, k)
    if n < 10:
        return base, (np.nan, np.nan), n
    k_hi = min(n, int(np.ceil((n + 1) * (1 - alpha / 2)))) - 1
    k_lo = max(0, int(np.floor((n + 1) * (alpha / 2))) - 1)
    return base, (base - errs[k_hi], base - errs[k_lo]), n


def _control_shift_z(c_col, k):
    """z da media pos-intervencao de UM controlo contra a extrapolacao linear do seu pre.
    v0.4: o erro-padrao inclui a incerteza da extrapolacao da tendencia (o da v0.3 usava sd/sqrt(H):
    alarmes falsos de 8% em dados iid e 53% com sazonalidade)."""
    n = len(c_col); t = np.arange(n); H = n - k
    X = np.column_stack([np.ones(k), t[:k]])
    b = np.linalg.lstsq(X, c_col[:k], rcond=None)[0]
    sd = (c_col[:k] - X @ b).std(ddof=2) if k > 2 else np.nan
    if not (np.isfinite(sd) and sd > 0):
        return np.nan
    Xp = np.column_stack([np.ones(H), t[k:]]); xbar = Xp.mean(axis=0)
    se = sd * np.sqrt(1.0 / H + xbar @ np.linalg.inv(X.T @ X) @ xbar)
    return float((c_col[k:] - Xp @ b).mean() / se)


def _space_placebo(c, k, alpha=0.30, min_train=20):
    """Placebo no ESPACO (v0.7): cada controlo e tratado como pseudo-alvo e previsto pelos restantes; ha alarme se
    |desvio pos-intervencao| > z x RMS dos erros placebo no tempo (z = Phi^-1(1 - alpha/(2K)), Bonferroni).
    Choques comuns a todos os controlos nao disparam; contaminacao de um so, sim.
    Regra de escala em vez de intervalo min-max: os placebos sobrepoem-se muito e os extremos sub-cobriam
    (22,5% de alarmes falsos em controlos iid). alpha=0,30 porque um falso 'valido' custa mais que um falso alarme.
    Medido (K=3, 80 mundos cada): alarmes falsos 9% (controlos iid), 0% (sazonal comum), 1% (dinamica comum nao
    linear); deteta +8 em 99% (iid, 1,6 desvios), 90% (nao linear, 2,7 desvios) e 41% (sazonalidade forte).
    O teste z do proprio controlo dava 43% de alarmes falsos com dinamica nao linear."""
    K = c.shape[1]
    if K < 2:
        return False, []
    zc = norm.ppf(1 - alpha / (2 * K)); flagged = []
    for j in range(K):
        y, co = c[:, j], np.delete(c, j, axis=1); H = len(y) - k; errs = []
        for t0 in range(min_train, k - H + 1):
            try:
                errs.append(controlled_incremental(y[:t0 + H], co[:t0 + H], t0)['incremental'])
            except ContractError:
                continue
        if len(errs) < 10:
            continue
        try:
            est = controlled_incremental(y, co, k)['incremental']
        except ContractError:
            continue
        if abs(est) > zc * np.sqrt(np.mean(np.square(errs))):
            flagged.append(j)
    return bool(flagged), flagged


def controlled_incremental_ci(outcome, controls, intervention_index, alpha=0.10,
                              min_train=20, shift_z=3.0, loo_ratio=1.0, min_controls=3,
                              pre_per_param=8, holdout=False):
    """Estimativa + IC por placebo-no-tempo + diagnosticos de validade (v0.4, OBJ-003).

    IC: pseudo-intervencoes j no pre-periodo (treino [0,j), avaliacao [j, j+H), H = duracao do
    pos-periodo); o erro da SOMA da o IC (quantis conformais). Calibrado em dados iid/AR/sazonais
    (cobertura 0,83-0,93, falso positivo sob efeito nulo 12%); alarga honestamente quando o modelo
    esta mal especificado (sazonalidade omitida).

    `valido=False` se: (1) leave-one-control-out: retirar algum controlo muda a estimativa mais do
    que loo_ratio x semi-largura do IC (a conclusao depende de um controlo; alarmes falsos 0-3%);
    (2) v0.7, placebo no espaco (K>=2): um controlo desvia-se dos restantes mais do que o ruido
    permite (ver _space_placebo; alarmes falsos 0-9%, deteta 90% de +2,7 desvios sem sazonalidade forte); (3) so quando nao ha
    placebo no espaco (K=1) e nao e holdout: |z| do controlo > shift_z (alarmes falsos altos com
    dinamica nao linear, mas com K=1 a decisao ja se abstem por `verificavel`); (4) menos de 10 placebos.
    O z do proprio controlo passou a INFORMATIVO para K>=2: tratava um choque de mercado comum como
    contaminacao (bloqueio de 100%) e dava 43% de alarmes falsos com dinamica comum nao linear.
    `holdout=True` (v0.7): os controlos SAO unidades de holdout reservadas ANTES da campanha (atribuicao
    aleatoria). A identificacao vem da aleatorizacao e nao da redundancia: `verificavel` exige so
    pre >= pre_per_param x (K+2), e aceita K=1. Medido (6 regioes, 3 tratadas e 3 holdout, choque de
    mercado +10% em todas, efeito zero): vies ~12% do choque e IC exclui 0 em 15-23% das vezes (nominal
    10%); sem holdout o choque so no alvo era 100% atribuido a campanha.
    Sem holdout: `verificavel` = K >= min_controls e pre >= pre_per_param x (K+2); NAO afirmar efeito.
    Com sazonalidade forte a contaminacao e pouco detetavel: 'valido' = ausencia de alarme, nao prova.
    Nao prova causalidade por si; so `roi_decision` com holdout=True e desenho declarado fala em causa.
    """
    y = np.asarray(outcome, dtype=float); c = np.asarray(controls, dtype=float)
    if c.ndim == 1:
        c = c[:, None]
    k = intervention_index
    base = controlled_incremental(y, c, k)
    H = len(y) - k
    errs = []
    for j in range(min_train, k - H + 1):
        try:
            r = controlled_incremental(y[:j + H], c[:j + H], j)
        except ContractError:
            continue
        errs.append(r['incremental'])  # verdade placebo = 0
    errs = np.sort(np.array(errs))
    n = len(errs)
    if n >= 10:
        k_hi = min(n, int(np.ceil((n + 1) * (1 - alpha / 2)))) - 1
        k_lo = max(0, int(np.floor((n + 1) * (alpha / 2))) - 1)
        ci = (base['incremental'] - errs[k_hi], base['incremental'] - errs[k_lo])
    else:
        ci = (np.nan, np.nan)
    K = c.shape[1]
    zs = [_control_shift_z(c[:, col], k) for col in range(K)]
    contaminated = [i for i, z in enumerate(zs) if np.isfinite(z) and abs(z) > shift_z]
    espaco_flag, espaco_idx = (False, [])
    if K >= 2 and n >= 10:
        espaco_flag, espaco_idx = _space_placebo(c, k, min_train=min_train)
    z_gate = bool(contaminated) and K < 2 and not holdout     # so quando nao ha placebo no espaco
    loo_spread = np.nan; loo_flag = False
    if K >= 2 and np.isfinite(ci[0]):
        half = (ci[1] - ci[0]) / 2
        spreads = []
        for j in range(K):
            try:
                spreads.append(abs(controlled_incremental(y, np.delete(c, j, axis=1), k)['incremental']
                                   - base['incremental']))
            except ContractError:
                continue
        if spreads:
            loo_spread = float(max(spreads)); loo_flag = loo_spread > loo_ratio * half
    verificavel = bool((holdout or K >= min_controls) and k >= pre_per_param * (K + 2))
    warnings_ = []
    if n < 10:
        warnings_.append('pre-periodo curto: sem IC (placebos < 10)')
    if contaminated:
        warnings_.append(f'(informativo) controlos {contaminated} mudam face a propria tendencia (|z|>{shift_z}); '
                         'pode ser choque de mercado comum' + ('' if not z_gate else ': unico teste disponivel com K=1'))
    if espaco_flag:
        warnings_.append(f'placebo no espaco: controlos {espaco_idx} desviam-se dos restantes no pos-periodo '
                         '(possivel contaminacao/spillover ou choque so nesses controlos)')
    if loo_flag:
        warnings_.append(f'sensibilidade aos controlos: retirar um controlo move a estimativa {loo_spread:.3g} '
                         f'(> {loo_ratio} x semi-largura do IC): a conclusao depende de um controlo')
    if not verificavel:
        warnings_.append(f'identificacao fraca: {K} controlos e {k} semanas de pre '
                         f'(minimo {1 if holdout else min_controls} controlos e {pre_per_param}x(K+2) semanas); '
                         'contaminacao nao verificavel')
    robust = {}
    if holdout:
        # v0.9 (Grok, OBJ-003): segunda especificacao (racio) com o mesmo IC de placebo no tempo.
        try:
            inc_r, ci_r, n_r = _placebo_time_ci(_ratio_incremental, y, c, k, alpha, min_train)
            robust = {'incremental_racio': float(inc_r), 'ic_racio': tuple(float(v) for v in ci_r), 'n_placebos_racio': n_r}
        except ContractError:
            robust = {'incremental_racio': np.nan, 'ic_racio': (np.nan, np.nan), 'n_placebos_racio': 0}
    return {**base, **robust, 'ic': tuple(float(v) for v in ci), 'nivel_ic': 1 - alpha, 'n_placebos': n,
            'controls_shift_z': zs, 'loo_spread': loo_spread, 'loo_flag': bool(loo_flag),
            'espaco_flag': bool(espaco_flag), 'espaco_controlos': espaco_idx, 'holdout': bool(holdout),
            'verificavel': verificavel,
            'valido': not z_gate and not loo_flag and not espaco_flag and n >= 10, 'avisos': warnings_,
            'method': 'preperiod_ols_trend_controls+placebo_time_ci+loo+placebo_space'}


DESENHOS_CAUSAIS = ("aleatorizado", "holdout_geografico", "holdout_clientes")


def roi_decision(res, spend, margin_rate, desenho=None):
    """Converte o resultado de controlled_incremental_ci em ROI e numa decisao prudente.

    v0.6 (Grok, OBJ-003): a serie de controlos NAO identifica o efeito causal. Um choque externo que so
    afeta o alvo (prova ChatGPT ciclo02: efeito zero, 3/3 sementes 'positivo', valido e verificavel) e
    estatisticamente indistinguivel de um efeito de campanha. Nenhum diagnostico nos dados resolve isto.
    Por isso a decisao causal so e emitida quando o utilizador DECLARA um desenho que garante
    a atribuicao (`desenho` em DESENHOS_CAUSAIS): grupos de controlo definidos ANTES da campanha e nao
    expostos. Sem desenho, o maximo e 'indicio_estatistico_positivo/negativo' com `causal=False` e o
    aviso explicito de que NAO serve para decidir renovacao.

    ROI = (margem incremental - gasto) / gasto, IC propagado do IC do incremental; margin_rate in (0, 1].
    'nao_afirmar' se nao valido/verificavel ou inputs nao finitos; 'positivo'/'negativo' pelo limite do IC;
    senao 'inconclusivo'."""
    if not (0 < margin_rate <= 1) or spend <= 0:
        raise ContractError('roi_decision: margin_rate em (0,1] e spend > 0')
    if desenho is not None and desenho not in DESENHOS_CAUSAIS:
        raise ContractError(f'roi_decision: desenho deve ser um de {DESENHOS_CAUSAIS} ou None')
    # v0.7 (Claude, OBJ-003): a etiqueta so vale se o ESTIMADOR foi corrido com os controlos = holdout.
    # Antes, declarar --desenho com controlos quaisquer dava 'positivo, causal' em 13/30 simulacoes com efeito zero.
    if desenho is not None and not res.get('holdout', False):
        raise ContractError('roi_decision: desenho declarado exige que os controlos sejam as unidades de holdout '
                            '(estimar com controlled_incremental_ci(..., holdout=True); CLI: colunas holdout_*)')
    if desenho is None and res.get('holdout', False):
        raise ContractError('roi_decision: estimativa com holdout exige declarar o desenho (--desenho)')
    f = lambda inc: (inc * margin_rate - spend) / spend
    lo, hi = res['ic']
    roi = f(res['incremental']); roi_ic = (f(lo), f(hi))
    avisos = list(res['avisos'])
    if not res['valido'] or not res.get('verificavel', False) or not np.isfinite([lo, hi, spend, margin_rate]).all():
        dec = 'nao_afirmar'
    elif roi_ic[0] > 0:
        dec = 'positivo'
    elif roi_ic[1] < 0:
        dec = 'negativo'
    else:
        dec = 'inconclusivo'
    # v0.9 (Grok, OBJ-003): com holdout, a decisao exige que a especificacao de racio concorde (mesmo sinal com IC).
    # Medido (_hw de Claude, 80 mundos/celula, efeito 0): 'positivo' OLS sozinho 17,5% (choque mult.) e 17,5% (aditivo);
    # exigindo concordancia: 0,0% e 7,5%; sem choque 0,0%. Potencia com efeito +25 inalterada (61-66%).
    roi_ic_racio = (np.nan, np.nan); concordancia = None
    if res.get('holdout', False) and dec in ('positivo', 'negativo'):
        lr, hr = res.get('ic_racio', (np.nan, np.nan))
        roi_ic_racio = (f(lr), f(hr))
        if not np.isfinite(roi_ic_racio).all():
            concordancia = False
        else:
            concordancia = bool(roi_ic_racio[0] > 0) if dec == 'positivo' else bool(roi_ic_racio[1] < 0)
        if not concordancia:
            avisos.append('especificacoes discordam (OLS com tendencia vs racio sem intercepto): resultado depende da '
                          'forma do choque de mercado (aditivo/multiplicativo), que os dados nao identificam -> inconclusivo')
            dec = 'inconclusivo'
    causal = desenho is not None
    if causal:
        avisos.append('inferencia exploratoria sobre series agregadas, nao sobre as unidades de aleatorizacao: '
                      'concordancia OLS/racio nao garante calibracao. Claude ciclo04 reportou 27,5% de falsos '
                      'positivos e 15% de decisoes negativas sob efeito zero numa '
                      'simulacao com poucas regioes, holdout agregado K=1 e choques regionais heterogeneos. '
                      'Estas taxas descrevem esse cenario, nao sao garantias gerais. Confirmar desenho, '
                      'numero de unidades e inferencia ao nivel da aleatorizacao antes de usar na decisao humana.')
        avisos.append('causal CONDICIONADO a o desenho declarado ser verdadeiro (unidades de holdout reservadas '
                      'ANTES da campanha e nao expostas): o pacote nao consegue verificar a atribuicao. Choque de '
                      'mercado comum deixa residuo (medido ~12% do choque no OLS; com a regra de concordancia v0.9, falsos positivos 0-7,5% em simulacao).')
    if not causal and dec in ('positivo', 'negativo'):
        dec = 'indicio_estatistico_' + dec
        avisos.append('sem desenho declarado (aleatorizado/holdout): incremento relativo ao contrafactual, '
                      'NAO atribuivel a campanha; choques externos dao o mesmo resultado. Nao usar para renovar.')
    # v0.9 (Grok, OBJ-003, ChatGPT ciclo 03): separar evidencia estatistica de autorizacao operacional.
    # O pacote NUNCA autoriza renovar: `pode_decidir_renovacao` e sempre False; `evidencia_para_revisao` diz se ha
    # evidencia condicionada ao desenho que um humano pode usar, depois de confirmar atribuicao e nao exposicao.
    evid = bool(causal and dec in ('positivo', 'negativo'))
    if evid:
        avisos.append('autorizacao operacional e HUMANA: confirmar (1) atribuicao aleatoria documentada antes da campanha, '
                      '(2) holdout nao exposto, (3) unidade de aleatorizacao e tamanho; so depois decidir renovar/cortar.')
    return {'roi': float(roi), 'roi_ic': tuple(float(v) for v in roi_ic), 'decisao': dec, 'causal': causal,
            'roi_ic_racio': tuple(float(v) for v in roi_ic_racio), 'concordancia_especificacoes': concordancia,
            'evidencia_para_revisao': evid, 'autorizacao': 'humana_obrigatoria',
            'desenho': desenho, 'pode_decidir_renovacao': False,
            'verificavel': res['verificavel'], 'avisos': avisos}
