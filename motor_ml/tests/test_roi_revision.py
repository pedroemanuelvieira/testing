import numpy as np
from bi_ml.planning import controlled_incremental

def test_trend_and_cannibalisation_known_truth():
 for seed in [1,7,29]:
  rng=np.random.default_rng(seed);t=np.arange(100);ctrl=rng.uniform(10,30,100)
  target=100+2*t+3*ctrl;substitute=80+t+ctrl
  target[70:]+=20;substitute[70:]-=8
  net=controlled_incremental(target+substitute,ctrl,70)
  assert abs(net['incremental']-360)<1e-6
  gross=controlled_incremental(target,ctrl,70)
  assert abs(gross['incremental']-600)<1e-6
  # A target-only model overstates portfolio gain by 240 even with perfect fit.
  assert abs(gross['incremental']-net['incremental']-240)<1e-6
