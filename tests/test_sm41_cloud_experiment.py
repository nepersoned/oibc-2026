import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from analysis import sm41_cloud_experiment as experiment


def test_cloud_proxy_bounds_missing_and_provider_independence(monkeypatch):
    frame=pd.DataFrame({'ghi_cs':[100.,100.,100.,0.], 'wa_cloud':[0.,100.,np.nan,120.], 'wb_cloud':[100.,0.,50.,-5.]})
    monkeypatch.setattr(experiment,'_original_build',lambda *a,**k:frame.copy())
    got=experiment.build()
    np.testing.assert_allclose(got.sm41_wa_cloud_ghi_proxy.iloc[:2],[100,25])
    assert np.isnan(got.sm41_wa_cloud_ghi_proxy.iloc[2])
    np.testing.assert_allclose(got.sm41_wb_cloud_ghi_proxy.iloc[:2],[25,100])
    assert got.sm41_wa_cloud_ghi_proxy.iloc[3]==0
    assert got.sm41_wb_cloud_ghi_proxy.iloc[3]==0
