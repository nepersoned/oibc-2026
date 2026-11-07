"""Four-way multi-seed comparison using exactly the same SM39 group model."""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scoring as sc
from analysis.sm39_group_site_integration import redistribute,hourly_penalties,block_bootstrap,sha256
out=Path('outputs/sm41'); sites=sc.load_sites(); comp=sc.reference_composition(sites); smp=sc.load_smp(); report={}
for year in (2023,2024):
 a,b=sc.window(f'{year}-06-01',f'{year+1}-06-01'); times=pd.date_range(a,b,freq='h'); actual=sc.load_actual(f'{year}-06-01',f'{year+1}-06-01'); gp=pd.read_parquet(f'outputs/sm39/group_pred_{year}.parquet'); suffix='_2023' if year==2023 else ''
 base=Path(f'outputs/val_sm37_noext_repro{suffix}_sites.parquet'); feature=Path(f'outputs/val_sm41_cloud{suffix}_sites.parquet')
 def ensemble(paths):
  first=pd.read_parquet(paths[0]).sort_values(['site_id','ts']).reset_index(drop=True)
  for path in paths[1:]:
   p=pd.read_parquet(path).sort_values(['site_id','ts']).reset_index(drop=True)
   if not first[['site_id','ts']].equals(p[['site_id','ts']]): raise ValueError('keys differ')
   first['kwh']+=p.kwh
  first['kwh']/=len(paths); return first
 paths={'SM40':[base],'Seed Ensemble':[base]+[Path(f'outputs/val_sm41_baseseed{s}{suffix}_sites.parquet') for s in (21,42)],'Selected Feature Model':[feature],'Selected Feature + Seed Ensemble':[feature]+[Path(f'outputs/val_sm41_cloudseed{s}{suffix}_sites.parquet') for s in (21,42)]}
 details={}; metrics={}
 for name,ps in paths.items():
  pred=redistribute(ensemble(ps),gp,sites,comp,.2,times); d=hourly_penalties(pred,actual,comp,smp); w=float(d.pen.sum()); assert np.isclose(w,sc.score(pred,comp,actual,smp)['W'],atol=1e-5)
  details[name]=d; metrics[name]={'W':w,'W_1115':float(d.loc[d.ts.dt.hour.between(11,15),'pen'].sum()),'groups':{str(k):float(v) for k,v in d.groupby('group').pen.sum().items()},'inputs':{str(p):sha256(p) for p in ps}}
 base_d=details['SM40']; bm=base_d.groupby(base_d.ts.dt.strftime('%Y-%m')).pen.sum(); bh=base_d.groupby('ts').pen.sum().reindex(times,fill_value=0)
 for name,d in details.items():
  m=d.groupby(d.ts.dt.strftime('%Y-%m')).pen.sum(); delta=(d.groupby('ts').pen.sum().reindex(times,fill_value=0)-bh).to_numpy()
  monthly=pd.DataFrame({'baseline':bm,'candidate':m}); monthly['pct']=100*(monthly.candidate/monthly.baseline-1)
  monthly.to_csv(out/f'{year}_{name.replace(" ","_")}_monthly.csv')
  metrics[name]['worst_full_month_pct']=float(monthly.iloc[:12].pct.max()); metrics[name]['delta_pct']=100*(metrics[name]['W']/metrics['SM40']['W']-1)
  if year==2024 and name!='SM40' and metrics[name]['W']<metrics['SM40']['W']: metrics[name]['bootstrap']=block_bootstrap(delta)
 report[str(year)]=metrics; print(year,json.dumps(metrics,indent=2),flush=True)
(out/'four_way_comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
