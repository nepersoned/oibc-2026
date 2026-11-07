"""Audit forecast-only SM42 distributions, no target values."""
import json,sys,time
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scoring as sc
from analysis.sm42_features import spatial_features,disagreement_features
out=Path('outputs/sm42');out.mkdir(exist_ok=True,parents=True);sites=sc.load_sites(); all_stats={}
def describe(df,cols):
 res={}
 for c in cols:
  s=df[c];q=s.quantile([.05,.5,.95]);res[c]={'missing_pct':float(s.isna().mean()*100),'mean':float(s.mean()),'p05':float(q.loc[.05]),'p50':float(q.loc[.5]),'p95':float(q.loc[.95])}
 return res
for split in ('train','test'):
 start=time.time(); frames=[]
 for prov in ('wa','wb'):
  st=prov+'_station'; col=prov+'_cloud';x=pd.read_parquet(Path(sc.DATA)/split/f'forecast_{prov}.parquet',columns=[st,'ts','round',col]);x['ts']=sc.to_ts(x.ts)
  if x.duplicated([st,'ts','round']).any():raise ValueError('duplicate forecast keys')
  r17=x[x['round']==17].set_index([st,'ts'])[col];r10=x[x['round']==10].set_index([st,'ts'])[col];idx=r17.index.union(r10.index);r17=r17.reindex(idx);r10=r10.reindex(idx)
  f=pd.DataFrame({col:r17.fillna(r10),col+'_d10':r17-r10}).reset_index();frames.append(f)
 fa,fb=frames;sp=spatial_features(fa,fb);t=pd.DatetimeIndex(sp.ts);n1=fa.groupby('ts').wa_cloud.count().rename('wa_count');n2=fb.groupby('ts').wb_cloud.count().rename('wb_count');sp=sp.merge(n1,on='ts',how='left').merge(n2,on='ts',how='left')
 years=sorted(pd.DatetimeIndex(sp.ts).year.unique().tolist()); result={}
 for year in years:
  ss=sp[pd.DatetimeIndex(sp.ts).year==year];result[str(year)]={'spatial':describe(ss,[c for c in ss if c.startswith('sm42_')]),'station_counts':describe(ss,['wa_count','wb_count'])}
 # Expand one calendar year at a time to limit memory usage.
 for year in years:
  ax=fa[pd.DatetimeIndex(fa.ts).year==year]; bx=fb[pd.DatetimeIndex(fb.ts).year==year]
  left=sites[['site_id','wa_station','wb_station']].merge(ax,on='wa_station',how='left').merge(bx,on=['wb_station','ts'],how='left')
  f3=disagreement_features(left)
  result[str(year)]['disagreement']=describe(f3,list(f3.columns))
  del left,f3
 result['seconds']=time.time()-start;all_stats[split]=result;print(split,'seconds',result['seconds'],flush=True)
(out/'feature_audit.json').write_text(json.dumps(all_stats,indent=2),encoding='utf-8')
