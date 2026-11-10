import unittest
import numpy as np
import pandas as pd
from bi_ml import contract
from bi_ml.planning import plan_variance, cohort_retention
class Revision(unittest.TestCase):
 def sales(self):
  return pd.DataFrame(dict(date=pd.to_datetime(['2025-01-01','2025-01-02','2025-02-01']),order_id=['1','2','3'],customer_id=['A','B','A'],product_id=['P']*3,qty=[1,1,1],revenue=[10,10,10]))
 def test_infinite(self):
  s=self.sales();s['qty']=s['qty'].astype(float);s.loc[0,'qty']=np.inf  # v0.3: pandas 3 recusa inf em int64
  with self.assertRaises(contract.ContractError):contract.validate_sales(s)
 def test_returns(self):
  s=self.sales();s['returned_qty']=1
  with self.assertRaises(contract.ContractError):contract.validate_sales(s)
 def test_empty_id(self):
  # v0.4 (OBJ-020): customer_id vazio = venda anonima (balcao), aceite; product_id/order_id vazios continuam a falhar
  for col in ('product_id','order_id'):
   s=self.sales();s.loc[0,col]=' '
   with self.assertRaises(contract.ContractError):contract.validate_sales(s)
  s=self.sales();s.loc[0,'customer_id']=' '
  self.assertTrue(contract.validate_sales(s).customer_id.isna().iloc[0])
 def test_cohort_truth(self):
  r=cohort_retention(self.sales(),'2025-03-01')
  self.assertEqual(r.retention.tolist(),[1,.5]);self.assertEqual(r.revenue.tolist(),[20,10])
 def test_censor_future(self):
  r=cohort_retention(self.sales(),'2025-02-15');self.assertEqual(len(r),1)
 def test_variance_and_zero_plan(self):
  p=pd.DataFrame(dict(period=['2025-01-01','2025-02-01'],product_id=['P','P'],planned_qty=[3,0],planned_revenue=[30,0]))
  r=plan_variance(self.sales(),p,'2025-03-01')
  self.assertEqual(r.delta_revenue.tolist(),[-10,10]);self.assertTrue(np.isnan(r.delta_pct_revenue.iloc[1]))
 def test_duplicate_plan(self):
  p=pd.DataFrame(dict(period=['2025-01-01']*2,product_id=['P']*2,planned_qty=[1,1],planned_revenue=[10,10]))
  with self.assertRaises(contract.ContractError):plan_variance(self.sales(),p,'2025-03-01')
 def test_forecast_vintage(self):
  p=pd.DataFrame(dict(period=['2025-01-01'],product_id=['P'],planned_qty=[1],planned_revenue=[10],issued_at=['2025-01-15']))
  with self.assertRaises(contract.ContractError):plan_variance(self.sales(),p,'2025-03-01',kind='forecast')
if __name__=='__main__':unittest.main()
