"""Run baseline multi-seed models only when no verified output is cached."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
out=Path('outputs/sm41'); out.mkdir(parents=True,exist_ok=True)
manifest=out/'seed_manifest.json'
cache=json.loads(manifest.read_text()) if manifest.exists() else {}
for year in (2023,2024):
 for seed in (21,42):
  tag=f'sm41_baseseed{seed}'
  suffix='_2023' if year==2023 else ''
  path=Path(f'outputs/val_{tag}{suffix}_sites.parquet')
  key=f'{year}-{seed}'
  sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
  if path.exists() and key in cache and cache[key]['sha256']==sha(path):
   print(f'{key}: verified cache',flush=True); continue
  cmd=[sys.executable,'src/pipeline.py','--mode','val','--fset','rich','--ext','none','--train-years','2','--drop-features','site_code','--params',json.dumps({'random_state':seed}),'--val-start',f'{year}-06-01','--val-end',f'{year+1}-06-01','--tag',tag]
  print(f'{key}: start',flush=True); t=time.time()
  with (out/f'{key}.log').open('w',encoding='utf-8') as f: subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,env=os.environ.copy())
  cache[key]={'sha256':sha(path),'seconds':time.time()-t,'path':str(path),'command':cmd}
  manifest.write_text(json.dumps(cache,indent=2),encoding='utf-8')
  print(f'{key}: complete {cache[key]["seconds"]:.1f}s',flush=True)
