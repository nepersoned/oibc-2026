"""Evaluate SM41 candidate with the unchanged SM39 allocation and official scoring."""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.sm39_group_site_integration import redistribute, hourly_penalties, block_bootstrap, sha256
import scoring as sc

out=Path('outputs/sm41'); out.mkdir(parents=True,exist_ok=True)
sites=sc.load_sites(); comp=sc.reference_composition(sites); smp=sc.load_smp()
report={}
for year in (2023,2024):
 start=f'{year}-06-01'; end=f'{year+1}-06-01'
 a,b=sc.window(start,end); times=pd.date_range(a,b,freq='h')
 gp_path=Path(f'outputs/sm39/group_pred_{year}.parquet')
 gp=pd.read_parquet(gp_path); actual=sc.load_actual(start,end)
 paths={'SM40':Path('outputs/val_sm37_noext_repro_2023_sites.parquet' if year==2023 else 'outputs/val_sm37_noext_repro_sites.parquet'), 'F2':Path('outputs/val_sm41_cloud_2023_sites.parquet' if year==2023 else 'outputs/val_sm41_cloud_sites.parquet')}
 details={}; rows={}
 for name,path in paths.items():
  pred=redistribute(pd.read_parquet(path),gp,sites,comp,.2,times)
  det=hourly_penalties(pred,actual,comp,smp).sort_values(['ts','group'])
  w=float(det.pen.sum()); official=sc.score(pred,comp,actual,smp)['W']
  if not np.isclose(w,official,atol=1e-5): raise ValueError('official W mismatch')
  details[name]=det
  rows[name]={'W':w,'W_1115':float(det.loc[det.ts.dt.hour.between(11,15),'pen'].sum()),'group':{str(k):float(v) for k,v in det.groupby('group').pen.sum().items()},'sha256':sha256(path)}
  det.to_parquet(out/f'{year}_{name}_hourly.parquet',index=False)
 base=details['SM40']; cand=details['F2']
 delta=(cand.groupby('ts').pen.sum()-base.groupby('ts').pen.sum()).reindex(times,fill_value=0).to_numpy()
 bm=base.groupby(base.ts.dt.strftime('%Y-%m')).pen.sum(); cm=cand.groupby(cand.ts.dt.strftime('%Y-%m')).pen.sum()
 monthly=pd.DataFrame({'baseline':bm,'candidate':cm}); monthly['delta']=monthly.candidate-monthly.baseline; monthly['pct']=100*monthly.delta/monthly.baseline
 monthly.to_csv(out/f'{year}_monthly.csv')
 report[str(year)]={'models':rows,'bootstrap':block_bootstrap(delta) if year==2024 and rows['F2']['W']<rows['SM40']['W'] else None,'group_input_sha256':sha256(gp_path),'monthly':json.loads(monthly.to_json(orient='index'))}
 print(year,rows,flush=True)
(out/'comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
