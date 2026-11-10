import numpy as np,pandas as pd,pytest
from bi_ml import demand

def test_baseline_default_h8_independent_truth():
 q=np.arange(1,101,dtype=float)
 s=pd.DataFrame(dict(date=pd.date_range('2023-01-02',periods=100,freq='W-MON'),product_id='A',qty=q))
 f=demand.forecast_all(s,h=8)
 assert len(f)==8 and set(f.method)=={'media_13s'}
 assert np.allclose(f.forecast,94.0)
 assert set(f.selection_horizon)=={8}
 assert np.allclose(f.wape_holdout,f.wape_holdout_media_13s)

def test_future_does_not_change_past_forecast():
 s=pd.DataFrame(dict(date=pd.date_range('2023-01-02',periods=100,freq='W-MON'),product_id='A',qty=np.arange(1,101)))
 a=demand.forecast_all(s.iloc[:90],h=8);s.loc[90:,'qty']=999999
 b=demand.forecast_all(s.iloc[:90],h=8);pd.testing.assert_frame_equal(a,b)

def test_invalid_policy_rejected():
 with pytest.raises(ValueError):demand.forecast_all(pd.DataFrame(),selection_policy='unknown')
