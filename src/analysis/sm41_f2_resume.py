"""Resume seed-7 F2 only when registered files and code hashes are unchanged."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
out=Path('outputs/sm41'); out.mkdir(parents=True,exist_ok=True); manifest=out/'f2_resume_manifest.json'
cache=json.loads(manifest.read_text()) if manifest.exists() else {}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
code=sha('src/analysis/sm41_cloud_experiment.py')
for year in (2023,2024):
 suffix='_2023' if year==2023 else ''; p=Path(f'outputs/val_sm41_cloud{suffix}_sites.parquet'); key=str(year)
 if p.exists() and key in cache and cache[key]['sha256']==sha(p) and cache[key]['code_sha256']==code:
  print(f'{year}: verified cache',flush=True); continue
 cmd=[sys.executable,'src/analysis/sm41_cloud_experiment.py','--mode','val','--fset','rich','--ext','none','--train-years','2','--drop-features','site_code','--params',json.dumps({'random_state':7}),'--val-start',f'{year}-06-01','--val-end',f'{year+1}-06-01','--tag','sm41_cloud']
 t=time.time()
 with (out/f'f2-{year}.log').open('w',encoding='utf-8') as f: subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,env=os.environ.copy())
 cache[key]={'sha256':sha(p),'code_sha256':code,'path':str(p),'seconds':time.time()-t,'command':cmd}; manifest.write_text(json.dumps(cache,indent=2),encoding='utf-8')
