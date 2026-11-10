import io
import numpy as np
import pandas as pd
import pytest
from bi_ml import prepare,planning
from bi_ml.contract import ContractError
from bi_ml.abc_xyz import classify

def test_ambiguous_date_requires_format():
 with pytest.raises(ContractError):prepare.parse_dates(pd.Series(['03/04/2025']))
 assert prepare.parse_dates(pd.Series(['03/04/2025']),'%d/%m/%Y').iloc[0]==pd.Timestamp('2025-04-03')

def test_portuguese_csv_and_leading_zero(tmp_path):
 p=tmp_path/'v.csv';p.write_bytes('date;order_id;customer_id;product_id;qty;revenue;note\n03/04/2025;0001;C;001;1,5;12,50;ação\n'.encode('latin-1'))
 d=prepare.read_erp_csv(p,sep=';',decimal=',',encoding='latin-1',date_format='%d/%m/%Y')
 s,_,_=prepare.prepare_sales(d)
 assert s.qty.iloc[0]==1.5 and s.revenue.iloc[0]==12.5
 assert s.product_id.iloc[0]=='001' and s.order_id.iloc[0]=='0001'
 assert s.date.iloc[0]==pd.Timestamp('2025-04-03')

def test_roi_unverifiable_abstains():
 r=dict(incremental=1000,ic=(900,1100),valido=True,verificavel=False,avisos=[])
 assert planning.roi_decision(r,100,.5)['decisao']=='nao_afirmar'

def test_abc_xyz_truth():
 rows=[]
 for month in range(1,7):
  for p,rev,q in [('A',80,10),('B',15,2),('C',5,1 if month==1 else 0)]:
   if q: rows.append([f'2025-{month:02d}-01',f'{p}{month}','K',p,q,rev])
 s=pd.DataFrame(rows,columns=['date','order_id','customer_id','product_id','qty','revenue'])
 r=classify(s,'2025-01-01','2025-07-01').set_index('product_id')
 assert r.loc['A','class']=='AX';assert r.loc['C','xyz']=='Z'
 assert abs(r.loc['C','cv']-np.sqrt(5))<1e-8

def test_roi_cli_rejects_unsorted_dates(tmp_path):
 from bi_ml.cli import run
 pd.DataFrame(dict(date=['2025-01-01'],order_id=['1'],customer_id=['C'],product_id=['P'],qty=[1],revenue=[1])).to_csv(tmp_path/'sales.csv',index=False)
 f=tmp_path/'series.csv'
 pd.DataFrame(dict(date=['2025-02-01','2025-01-01'],outcome=[10,20],control_1=[1,2])).to_csv(f,index=False)
 with pytest.raises(ContractError,match='ordenadas'):
  run('roi-series',str(tmp_path),str(tmp_path/'out'),series=str(f),intervention_date='2025-02-01',spend=1,margin_rate=.5)
