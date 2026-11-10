"""ABC by gross revenue, XYZ by monthly demand CV. Explicit observation window.
No inventory recommendation; thresholds are configurable business choices.
"""
import numpy as np
import pandas as pd
from .contract import validate_sales, ContractError

def classify(sales, start, end, abc=(.8,.95), xyz=(.5,1.0)):
    s=validate_sales(sales)
    start,end=pd.Timestamp(start),pd.Timestamp(end)
    if start != start.to_period('M').start_time or end != end.to_period('M').start_time or end<=start:
        raise ContractError('ABC-XYZ: janela [start,end) exige inicios de meses')
    if not 0<abc[0]<abc[1]<1 or not 0<=xyz[0]<xyz[1]:
        raise ContractError('ABC-XYZ: limiares invalidos')
    first_ever=s.groupby('product_id').date.min().dt.to_period('M')  # v0.6 (OBJ-028): historia completa, nao so a janela
    s=s[(s.date>=start)&(s.date<end)].copy()
    if s.empty:raise ContractError('ABC-XYZ: sem vendas na janela')
    months=pd.period_range(start,end-pd.Timedelta(days=1),freq='M')
    if len(months)<3:raise ContractError('ABC-XYZ: minimo 3 meses completos')
    s['month']=s.date.dt.to_period('M')
    out=s.groupby('product_id').revenue.sum().rename('revenue').reset_index()
    if (out.revenue<0).any() or out.revenue.sum()<=0:raise ContractError('ABC: receita total deve ser positiva')
    out=out.sort_values(['revenue','product_id'],ascending=[False,True])
    out['share']=out.revenue/out.revenue.sum()
    # Crossing item stays in preceding class; ties broken by product_id, documented.
    before=out.share.cumsum()-out.share
    out['abc']=np.select([before<abc[0],before<abc[1]],['A','B'],default='C')
    q=s.groupby(['month','product_id']).qty.sum().unstack().reindex(months).fillna(0)
    cv=q.std(ddof=0)/q.mean().replace(0,np.nan)
    out['cv']=out.product_id.map(cv)
    out['xyz']=np.select([out.cv<=xyz[0],out.cv<=xyz[1]],['X','Y'],default='Z')
    # v0.6 (Grok, OBJ-028): 'U' so se o produto NAO vendia antes do inicio da janela. A v0.5 usava a
    # 1.a venda DENTRO da janela: um produto antigo sem vendas no 1.o mes ficava 'U' (falso).
    out['history_incomplete']=out.product_id.map(first_ever)>months[0]
    out.loc[out.history_incomplete,'xyz']='U'
    out['class']=out.abc+out.xyz
    # v0.6 (Grok, OBJ-029): CV alto nao implica imprevisivel se o padrao e sazonal e repetido.
    # Com >= 24 meses, mede o CV do residuo apos remover o perfil mes-do-ano (indice multiplicativo
    # estimado na propria janela). Com < 24 meses, nao e avaliavel: NaN e nota, nunca um palpite.
    if len(months)>=24:
        # Perfil leave-one-year-out: cada mes e comparado com a media do MESMO mes nos OUTROS anos.
        # (Perfil in-sample sobreajusta: com 3 anos, 12 parametros em 36 pontos fazem ruido parecer sazonal.)
        moy=q.index.month
        tot=q.groupby(moy).transform('sum'); cnt=q.groupby(moy).transform('count')
        prof=(tot-q)/(cnt-1)
        resid=(q/prof.replace(0,np.nan))
        cv_s=resid.std(ddof=0)/resid.mean()
        out['cv_dessazonalizado']=out.product_id.map(cv_s)
        out['xyz_sazonal']=np.select([out.cv_dessazonalizado<=xyz[0],out.cv_dessazonalizado<=xyz[1]],['X','Y'],default='Z')
        out.loc[out.history_incomplete,'xyz_sazonal']='U'
        out['nota_sazonal']=np.where((out.xyz!=out.xyz_sazonal)&~out.history_incomplete,
                                     'padrao sazonal repetido: usar xyz_sazonal para planeamento','')
    else:
        out['cv_dessazonalizado']=np.nan; out['xyz_sazonal']='NA'
        out['nota_sazonal']='janela < 24 meses: sazonalidade nao avaliavel; CV alto pode ser sazonal'
    return out.reset_index(drop=True)
