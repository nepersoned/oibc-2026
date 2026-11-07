"""Opt-in SM42 forecast features. Off by default; inputs are available forecasts only."""
from __future__ import annotations
import os,sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import features as F
import pipeline

_orig_region=F.region_means
_orig_build=F.build_rich

def spatial_features(fa,fb):
    result=None
    for provider,frame in [('wa',fa),('wb',fb)]:
        col=provider+'_cloud'
        if frame.duplicated([provider+'_station','ts']).any(): raise ValueError('duplicate station/time')
        group=frame.groupby('ts')[col]
        sub=pd.DataFrame({f'sm42_{provider}_cloud_std':group.std(ddof=1), f'sm42_{provider}_cloud_p90_p10':group.quantile(.9)-group.quantile(.1)})
        result=sub if result is None else result.join(sub,how='outer')
    return result.astype('float32').reset_index()

def disagreement_features(d):
    out=pd.DataFrame(index=d.index)
    for provider in ('wa','wb'):
        out[f'sm42_{provider}_cloud_revision_abs']=d[f'{provider}_cloud_d10'].abs().astype('float32')
    out['sm42_wa_wb_cloud_disagreement']=(d.wa_cloud-d.wb_cloud).abs().astype('float32')
    return out

def configure(mode):
    if mode not in ('none','f3','f4'): raise ValueError('OIBC_SM42_FEATURES must be none, f3 or f4')
    if mode=='f4':
        def region(fa,fb):
            return _orig_region(fa,fb).merge(spatial_features(fa,fb),on='ts',how='left',validate='one_to_one')
        F.region_means=region
    elif mode=='f3':
        def build(*args,**kwargs):
            d=_orig_build(*args,**kwargs)
            for c,v in disagreement_features(d).items(): d[c]=v
            return d
        F.build_rich=build

if __name__=='__main__':
    configure(os.environ.get('OIBC_SM42_FEATURES','none'))
    pipeline.main()
