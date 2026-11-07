"""SM42 training driver: verified cache and hard 21:15 KST training cutoff."""
import argparse,datetime,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from zoneinfo import ZoneInfo

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for x in iter(lambda:f.read(1024*1024),b''):h.update(x)
 return h.hexdigest()
ap=argparse.ArgumentParser(); ap.add_argument('--family',choices=['f3','f4'],required=True);ap.add_argument('--year',type=int,choices=[2023,2024],required=True);ap.add_argument('--seed',type=int,choices=[7,21,42],required=True);a=ap.parse_args()
out=Path('outputs/sm42');out.mkdir(parents=True,exist_ok=True);tag=f'sm42_{a.family}_seed{a.seed}';suffix='_2023' if a.year==2023 else ''; pred=Path(f'outputs/val_{tag}{suffix}_sites.parquet');meta=out/f'{a.family}_{a.year}_{a.seed}.json'
inputs=[Path(x) for x in ['src/analysis/sm42_features.py','src/features.py','src/pipeline.py','src/model.py','src/scoring.py','SM42_PREREGISTRATION.md']]
inputs += [Path('data/handover 2/01_participant_dataset')/p for p in ['sites.csv','train/generation.parquet','train/forecast_wa.parquet','train/forecast_wb.parquet','train/smp.csv']]
hashes={str(p):sha(p) for p in inputs}
if pred.exists() and meta.exists():
 m=json.loads(meta.read_text());
 if m['inputs']==hashes and m['sha256']==sha(pred): print('verified cache',flush=True);sys.exit(0)
now=datetime.datetime.now(datetime.timezone.utc).astimezone(ZoneInfo('Asia/Seoul'))
if now.time()>=datetime.time(21,15): raise SystemExit(f'No training starts after 21:15 KST: {now}')
env=os.environ.copy();env.update(OIBC_SM42_FEATURES=a.family,OIBC_EXT_SOURCES='no_openmeteo',OIBC_SPATIAL='none',OIBC_PHYSICS='none',OIBC_SRC='prov',OIBC_CAL='1');env.pop('OIBC_WX2',None)
cmd=[sys.executable,'src/analysis/sm42_features.py','--mode','val','--fset','rich','--train-years','2','--ext','none','--drop-features','site_code','--params',json.dumps({'random_state':a.seed}),'--val-start',f'{a.year}-06-01','--val-end',f'{a.year+1}-06-01','--tag',tag]
t=time.time();print('starting',a.family,a.year,a.seed,str(now),flush=True)
with (out/f'{a.family}_{a.year}_{a.seed}.log').open('w',encoding='utf-8') as f: subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,check=True)
meta.write_text(json.dumps({'inputs':hashes,'sha256':sha(pred),'prediction':str(pred),'seconds':time.time()-t,'command':cmd,'started_kst':str(now)},indent=2),encoding='utf-8');print('completed',a.family,a.year,a.seed,flush=True)
