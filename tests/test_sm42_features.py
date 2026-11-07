import sys
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from analysis import sm42_features as f

def test_spatial_percent_and_one_station():
    ts=pd.to_datetime(['2024-01-01','2024-01-01','2024-01-02'],utc=True)
    a=pd.DataFrame({'wa_station':['a','b','a'],'ts':ts,'wa_cloud':[0.,100.,50.]})
    b=pd.DataFrame({'wb_station':['a','b','a'],'ts':ts,'wb_cloud':[20.,60.,30.]})
    x=f.spatial_features(a,b)
    assert np.isclose(x.sm42_wa_cloud_std.iloc[0],np.sqrt(5000))
    assert np.isclose(x.sm42_wa_cloud_p90_p10.iloc[0],80.)
    assert np.isnan(x.sm42_wa_cloud_std.iloc[1])
    assert x.sm42_wa_cloud_p90_p10.iloc[1]==0

def test_revision_missing_and_disagreement():
    d=pd.DataFrame({'wa_cloud_d10':[10.,np.nan],'wb_cloud_d10':[-5.,2.],'wa_cloud':[40.,np.nan],'wb_cloud':[60.,10.]})
    z=f.disagreement_features(d)
    assert z.sm42_wa_cloud_revision_abs.iloc[0]==10
    assert np.isnan(z.sm42_wa_cloud_revision_abs.iloc[1])
    assert z.sm42_wb_cloud_revision_abs.iloc[0]==5
    assert z.sm42_wa_wb_cloud_disagreement.iloc[0]==20
    assert np.isnan(z.sm42_wa_wb_cloud_disagreement.iloc[1])

def test_off_preserves_original():
    f.configure('none')
    assert f.F.region_means is f._orig_region
    assert f.F.build_rich is f._orig_build

def test_feature_columns_equal_for_train_test():
    time=pd.to_datetime(['2024-01-01'],utc=True)
    a=pd.DataFrame({'wa_station':['a'],'ts':time,'wa_cloud':[50.]})
    b=pd.DataFrame({'wb_station':['b'],'ts':time,'wb_cloud':[60.]})
    assert list(f.spatial_features(a,b).columns)==list(f.spatial_features(a.copy(),b.copy()).columns)
    d=pd.DataFrame({'wa_cloud_d10':[np.nan],'wb_cloud_d10':[1.],'wa_cloud':[40.],'wb_cloud':[60.]})
    assert list(f.disagreement_features(d).columns)==list(f.disagreement_features(d.copy()).columns)

def test_duplicate_station_time_rejected():
    time=pd.to_datetime(['2024-01-01','2024-01-01'],utc=True)
    a=pd.DataFrame({'wa_station':['a','a'],'ts':time,'wa_cloud':[50.,60.]})
    b=pd.DataFrame({'wb_station':['b'],'ts':time[:1],'wb_cloud':[60.]})
    import pytest
    with pytest.raises(ValueError,match='duplicate'):f.spatial_features(a,b)
