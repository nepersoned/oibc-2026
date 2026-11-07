"""Build chosen SM42 final candidate only; never upload or touch SM40/41."""
import argparse,datetime,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scoring as sc
from analysis.sm39_group_site_integration import redistribute,sha256
ap=argparse.ArgumentParser();ap.add_argument('--choice',choices=['sm41','f3','f4'],required=True);a=ap.parse_args();out=Path('outputs/sm42');out.mkdir(exist_ok=True,parents=True);sub=Path('submissions'); cp=sub/'composition_sm42_final.csv';fp=sub/'forecast_sm42_final.csv'
if a.choice=='sm41':
 shutil.copyfile(sub/'composition_sm41_final.csv',cp);shutil.copyfile(sub/'forecast_sm41_final.csv',fp)
else:
 paths=[]
 for seed in (7,21,42):
  tag=f'sm42_final_{a.choice}_{seed}';path=Path(f'outputs/test_{tag}_sites.parquet');meta=out/f'{tag}.json';cached=json.loads(meta.read_text()) if meta.exists() else {}
  if not(path.exists() and cached.get('sha256')==sha256(path)):
   now=datetime.datetime.now(datetime.timezone.utc).astimezone(ZoneInfo('Asia/Seoul'))
   if now.time()>=datetime.time(21,15): raise RuntimeError('cannot start new training after 21:15 KST; retain SM41')
   env=os.environ.copy();env.update(OIBC_SM42_FEATURES=a.choice,OIBC_EXT_SOURCES='no_openmeteo',OIBC_SPATIAL='none',OIBC_PHYSICS='none',OIBC_SRC='prov',OIBC_CAL='1');env.pop('OIBC_WX2',None)
   cmd=[sys.executable,'src/analysis/sm42_features.py','--mode','submit','--fset','rich','--train-years','2','--ext','none','--drop-features','site_code','--params',json.dumps({'random_state':seed}),'--tag',tag]
   print('start submission seed',seed,str(now),flush=True);t=time.time()
   with (out/f'{tag}.log').open('w',encoding='utf-8') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,check=True)
   meta.write_text(json.dumps({'sha256':sha256(path),'command':cmd,'started_kst':str(now),'seconds':time.time()-t},indent=2))
   for prefix in ('composition','forecast'):
    tmp=sub/f'{prefix}_{tag}.csv'
    if tmp.exists():tmp.unlink()
  paths.append(path)
 p=pd.read_parquet(paths[0]).sort_values(['site_id','ts']).reset_index(drop=True)
 for path in paths[1:]:
  d=pd.read_parquet(path).sort_values(['site_id','ts']).reset_index(drop=True)
  if not p[['site_id','ts']].equals(d[['site_id','ts']]):raise ValueError('seed key mismatch')
  p['kwh']+=d.kwh
 p['kwh']/=len(paths);sites=sc.load_sites();comp=sc.reference_composition(sites);pa,pb=sc.window('2025-06-01','2026-06-01');times=pd.date_range(pa,pb,freq='h')
 pred=redistribute(p,pd.read_parquet('outputs/sm40/group_test.parquet'),sites,comp,.2,times);pred.to_parquet(out/'final_sites.parquet',index=False)
 f=pred.assign(group=pred.site_id.map(comp)).groupby(['group','ts'],as_index=False).kwh.sum().rename(columns={'kwh':'forecast_kwh'}).sort_values(['group','ts'])
 f['ts']=f.ts.dt.strftime('%Y-%m-%d %H:%M:%S%z').str.replace(r'(\d{2})(\d{2})$',r'\1:\2',regex=True)
 comp.rename('group').rename_axis('site_id').reset_index().to_csv(cp,index=False);f.to_csv(fp,index=False)
 reloaded=pd.read_csv(fp); np.testing.assert_allclose(reloaded.forecast_kwh.to_numpy(),f.forecast_kwh.to_numpy(),rtol=1e-14,atol=1e-8)
subprocess.run([sys.executable,'src/validate_submission.py','--composition',str(cp),'--forecast',str(fp)],check=True)
manifest={'choice':a.choice,'composition_sha256':sha256(cp),'forecast_sha256':sha256(fp),'sm41_original_forecast_sha256':sha256(sub/'forecast_sm41_final.csv'),'portal_upload':False};(out/'final_manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest),flush=True)
