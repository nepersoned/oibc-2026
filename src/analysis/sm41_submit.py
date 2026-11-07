"""Materialize exactly the selected SM41 submission; never upload."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scoring as sc
from analysis.sm39_group_site_integration import redistribute
p=argparse.ArgumentParser(); p.add_argument('--choice',required=True,choices=['sm40','base_ensemble','f2','f2_ensemble']); a=p.parse_args()
out=Path('outputs/sm41'); out.mkdir(parents=True,exist_ok=True); sub=Path('submissions'); sub.mkdir(exist_ok=True)
cpath=sub/'composition_sm41_final.csv'; fpath=sub/'forecast_sm41_final.csv'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
if a.choice=='sm40':
 shutil.copyfile(sub/'composition_sm40_noext_ensemble.csv',cpath); shutil.copyfile(sub/'forecast_sm40_noext_ensemble.csv',fpath)
else:
 feature=a.choice.startswith('f2'); seeds=(7,21,42) if a.choice.endswith('ensemble') else (7,)
 paths=[]
 for seed in seeds:
  if not feature and seed==7:
   paths.append(Path('outputs/sm40/site_test.parquet')); continue
  tag=f'sm41_final_{"f2" if feature else "base"}_{seed}'
  pred=Path(f'outputs/test_{tag}_sites.parquet'); manifest=out/f'{tag}.json'
  cache=json.loads(manifest.read_text()) if manifest.exists() else {}
  if not (pred.exists() and cache.get('sha256')==sha(pred)):
   script='src/analysis/sm41_cloud_experiment.py' if feature else 'src/pipeline.py'
   cmd=[sys.executable,script,'--mode','submit','--fset','rich','--train-years','2','--ext','none','--drop-features','site_code','--params',json.dumps({'random_state':seed}),'--tag',tag]
   with (out/f'{tag}.log').open('w',encoding='utf-8') as log: subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=os.environ.copy(),check=True)
   manifest.write_text(json.dumps({'sha256':sha(pred),'command':cmd},indent=2))
   for prefix in ('composition','forecast'):
    tmp=sub/f'{prefix}_{tag}.csv'
    if tmp.exists(): tmp.unlink()
  paths.append(pred)
 base=pd.read_parquet(paths[0]).sort_values(['site_id','ts']).reset_index(drop=True)
 for path in paths[1:]:
  d=pd.read_parquet(path).sort_values(['site_id','ts']).reset_index(drop=True)
  if not base[['site_id','ts']].equals(d[['site_id','ts']]): raise ValueError('seed keys differ')
  base['kwh']+=d.kwh
 base['kwh']/=len(paths)
 sites=sc.load_sites(); comp=sc.reference_composition(sites); pa,pb=sc.window('2025-06-01','2026-06-01'); times=pd.date_range(pa,pb,freq='h')
 pred=redistribute(base,pd.read_parquet('outputs/sm40/group_test.parquet'),sites,comp,.2,times)
 pred.to_parquet(out/'final_site_predictions.parquet',index=False)
 f=pred.assign(group=pred.site_id.map(comp)).groupby(['group','ts'],as_index=False).kwh.sum().rename(columns={'kwh':'forecast_kwh'}).sort_values(['group','ts'])
 f['ts']=f.ts.dt.strftime('%Y-%m-%d %H:%M:%S%z').str.replace(r'(\d{2})(\d{2})$',r'\1:\2',regex=True)
 comp.rename('group').rename_axis('site_id').reset_index().to_csv(cpath,index=False); f.to_csv(fpath,index=False)
subprocess.run([sys.executable,'src/validate_submission.py','--composition',str(cpath),'--forecast',str(fpath)],check=True)
(out/'final_manifest.json').write_text(json.dumps({'choice':a.choice,'composition_sha256':sha(cpath),'forecast_sha256':sha(fpath),'upload':False},indent=2))
print('validated',a.choice,sha(cpath),sha(fpath))
