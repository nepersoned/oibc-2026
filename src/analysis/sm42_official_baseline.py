"""Run official participant baseline functions on two strictly historical windows."""
import argparse,hashlib,importlib.util,json,os,platform,sys,time
from pathlib import Path
import lightgbm as lgb, numpy as np, pandas as pd, pyarrow
sys.path.insert(0,str(Path(__file__).resolve().parents[1])); import scoring as sc

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--year',type=int,choices=[2023,2024],required=True); a=ap.parse_args()
 source=Path(sc.DATA)/'baseline.py'; spec=importlib.util.spec_from_file_location('official_baseline',source); b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
 out=Path('outputs/sm42');out.mkdir(parents=True,exist_ok=True); dest=out/f'baseline_{a.year}_sites.parquet'; meta=out/f'baseline_{a.year}_manifest.json'
 start,end=sc.window(f'{a.year}-06-01',f'{a.year+1}-06-01'); train_start=start-pd.DateOffset(years=2)
 inputs=[source,Path(sc.DATA)/'sites.csv',Path(sc.DATA)/'train'/'generation.parquet',Path(sc.DATA)/'train'/'forecast_wa.parquet',Path(sc.DATA)/'train'/'forecast_wb.parquet',Path(sc.DATA)/'train'/'smp.csv',Path(__file__)]
 hashes={str(p):sha(p) for p in inputs}; env={'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'pyarrow':pyarrow.__version__,'lightgbm':lgb.__version__}
 if dest.exists() and meta.exists():
  old=json.loads(meta.read_text());
  if old['inputs']==hashes and old['environment']==env and old['prediction_sha256']==sha(dest): print('verified cache');return
 sites=pd.read_csv(Path(sc.DATA)/'sites.csv')[["site_id","current_group","capacity_kw","lat","lon","wa_station","wb_station"]]
 gen=pd.read_parquet(Path(sc.DATA)/'train'/'generation.parquet');gen['ts']=sc.to_ts(gen.ts);gen=gen[(gen.ts>=train_start)&(gen.ts<start)]
 fa=pd.read_parquet(Path(sc.DATA)/'train'/'forecast_wa.parquet',columns=['wa_station','round','ts']+b.WA_COLS);fb=pd.read_parquet(Path(sc.DATA)/'train'/'forecast_wb.parquet',columns=['wb_station','round','ts']+b.WB_COLS)
 for f in (fa,fb): f['ts']=sc.to_ts(f.ts)
 times=pd.date_range(start,end,freq='h'); preds=[]; started=time.time()
 for r in b.ROUNDS:
  d=b.features(gen,sites,fa,fb,None,r);d=d[d.elev>0];y=(d.energy/d.cap).clip(0,1.2).astype('float32');X=d[b.FEATS].astype('float32')
  m=lgb.LGBMRegressor(n_estimators=600,learning_rate=.06,num_leaves=127,min_child_samples=200,subsample=.8,subsample_freq=1,colsample_bytree=.8,verbose=-1,n_jobs=-1).fit(X,y);del d,X,y
  d=b.features(None,sites,fa,fb,times,r); X=d[b.FEATS].astype('float32'); pred=np.where(d.elev.to_numpy()>0,m.predict(X),0); d['kwh']=np.clip(pred,0,None)*d.cap.to_numpy();preds.append(d[['site_id','ts','kwh']]);del d,X,m
  print(f'year={a.year} round={r} complete {time.time()-started:.1f}s',flush=True)
 pred=pd.concat(preds).groupby(['site_id','ts'],as_index=False).kwh.mean();pred.to_parquet(dest,index=False)
 actual=sc.load_actual(f'{a.year}-06-01',f'{a.year+1}-06-01');score=sc.score(pred,sc.reference_composition(sites),actual,sc.load_smp())
 data={'year':a.year,'W':score['W'],'site_hours':score['site_hours'],'hours':score['hours'],'inputs':hashes,'environment':env,'prediction_sha256':sha(dest),'train_start':str(train_start),'train_end_exclusive':str(start),'reference':'official baseline functions + historical window adapter','seconds':time.time()-started}
 meta.write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2),flush=True)
if __name__=='__main__':main()
