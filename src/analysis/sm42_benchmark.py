"""Official baseline and SM40/41/42 paired observed-site settlement benchmark."""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scoring as sc
from analysis.sm39_group_site_integration import redistribute,hourly_penalties,block_bootstrap,sha256
out=Path('outputs/sm42'); out.mkdir(parents=True,exist_ok=True)
sites=sc.load_sites(); comp=sc.reference_composition(sites);smp=sc.load_smp(); selection=json.loads((out/'screen_2023.json').read_text())['selected_2023_only']; records=[];monthly=[];diagnostics={}
for year in (2023,2024):
 start,end=sc.window(f'{year}-06-01',f'{year+1}-06-01'); times=pd.date_range(start,end,freq='h'); actual=sc.load_actual(f'{year}-06-01',f'{year+1}-06-01'); gp_path=Path(f'outputs/sm39/group_pred_{year}.parquet');gp=pd.read_parquet(gp_path);suffix='_2023' if year==2023 else ''
 base=Path(f'outputs/val_sm37_noext_repro{suffix}_sites.parquet')
 known={'2023':'c346a74ba7ecd8ac8495c3700256bfcc3288621b829e9cacd61d32d9f7fd8da6','2024':'1bee1c8c58083c4cd25bfdb77ce414e1d573a62130ebada75df964ea73257241'}
 if sha256(base)!=known[str(year)]: raise ValueError('SM40 site hash mismatch')
 old=json.loads(Path('outputs/sm41/four_way_comparison.json').read_text())[str(year)]
 prior=json.loads(Path('outputs/sm41/comparison.json').read_text())[str(year)]
 if sha256(gp_path)!=prior['group_input_sha256']:raise ValueError('SM39 group hash mismatch')
 original=json.loads((out/f'baseline_{year}_manifest.json').read_text())
 if sha256(out/f'baseline_{year}_sites.parquet')!=original['prediction_sha256']:raise ValueError('official prediction hash mismatch')
 seed_paths=[base]+[Path(f'outputs/val_sm41_baseseed{s}{suffix}_sites.parquet') for s in (21,42)]
 for path in seed_paths:
  if sha256(path)!=old['Seed Ensemble']['inputs'][str(path)]:raise ValueError('SM41 seed hash mismatch')
 def avg(paths):
  p=pd.read_parquet(paths[0]).sort_values(['site_id','ts']).reset_index(drop=True)
  if p.duplicated(['site_id','ts']).any():raise ValueError('duplicate')
  for path in paths[1:]:
   x=pd.read_parquet(path).sort_values(['site_id','ts']).reset_index(drop=True)
   if not p[['site_id','ts']].equals(x[['site_id','ts']]):raise ValueError('seed grid mismatch')
   p['kwh']+=x.kwh
  p['kwh']/=len(paths);return p
 candidates={'Official baseline':([out/f'baseline_{year}_sites.parquet'],False),'JH1-style SM4':([Path(f'outputs/val_sm_baseline{suffix}_sites.parquet')],False),'SM40':([base],True),'SM41':(seed_paths,True)}
 for fam in ('f4','f3'):
  path=Path(f'outputs/val_sm42_{fam}_seed7{suffix}_sites.parquet')
  if path.exists(): candidates[f'SM42 {fam.upper()} seed7']=([path],True)
 if selection:
  paths=[Path(f'outputs/val_sm42_{selection}_seed{s}{suffix}_sites.parquet') for s in (7,21,42)]
  if all(x.exists() for x in paths):candidates['SM42 selected ensemble']=(paths,True)
 weather=pd.read_parquet(Path(sc.DATA)/'train'/'forecast_wa.parquet',columns=['wa_station','round','ts','wa_cloud']); weather['ts']=sc.to_ts(weather.ts); weather=weather[(weather.ts>=start)&(weather.ts<=end)]
 weather=weather.groupby(['ts','round']).wa_cloud.mean().unstack('round');weather['cloud']=weather[17].fillna(weather[10]);weather['rev']=(weather[17]-weather[10]).abs();weather['regime']=np.select([weather.rev>=20,weather.cloud<30,weather.cloud>=70],['unstable','clear','cloudy'],default='mixed')
 details={}; year_info={}
 for name,(paths,blend) in candidates.items():
  p=avg(paths)
  if blend:p=redistribute(p,gp,sites,comp,.2,times)
  else:
   expected=pd.MultiIndex.from_product([sites.site_id,times],names=['site_id','ts']);got=pd.MultiIndex.from_frame(p[['site_id','ts']]);
   if not got.is_unique or len(got)!=len(expected) or len(expected.difference(got)):raise ValueError('baseline grid mismatch')
  d=hourly_penalties(p,actual,comp,smp); official=sc.score(p,comp,actual,smp);w=float(d.pen.sum())
  if not np.isclose(w,official['W'],atol=1e-5):raise ValueError('official score mismatch')
  m=actual.merge(p,on=['site_id','ts'],validate='one_to_one');err=m.kwh-m.energy;gerr=d.pred-d.act
  row={'year':year,'model':name,'W':w,'W_1115':float(d.loc[d.ts.dt.hour.between(11,15),'pen'].sum()),'site_MAE_kwh':float(err.abs().mean()),'site_bias_kwh':float(err.mean()),'group_MAE_kwh':float(gerr.abs().mean()),'group_bias_kwh':float(gerr.mean()),'observed_site_hours':len(m),'group_time_rows':len(d),'G1_W':float(d.loc[d.group=='G1','pen'].sum()),'G2_W':float(d.loc[d.group=='G2','pen'].sum())};records.append(row)
  mm=d.groupby(d.ts.dt.strftime('%Y-%m')).pen.sum()
  for mon,val in mm.items(): monthly.append({'year':year,'model':name,'month':mon,'W':float(val)})
  dd=d.merge(weather[['regime']],left_on='ts',right_index=True,how='left');dd['err']=dd.pred-dd.act;reg=dd.groupby(['group','regime']).agg(n=('err','size'),mean_error=('err','mean'),mae=('err',lambda x:x.abs().mean()),W=('pen','sum')).reset_index()
  year_info[name]={'prediction_sha256':{str(p):sha256(p) for p in paths},'weather':json.loads(reg.to_json(orient='records'))};details[name]=d
  print(year,name,round(w),flush=True)
 base_detail=details['SM41'];base_h=base_detail.groupby('ts').pen.sum().reindex(times,fill_value=0)
 for name,d in details.items():
  if year==2024 and name.startswith('SM42'):
   diff=d.groupby('ts').pen.sum().reindex(times,fill_value=0)-base_h
   if diff.sum()<0:year_info[name]['bootstrap_vs_SM41']=block_bootstrap(diff.to_numpy())
  bm=base_detail.groupby(base_detail.ts.dt.strftime('%Y-%m')).pen.sum();cm=d.groupby(d.ts.dt.strftime('%Y-%m')).pen.sum();rel=100*(cm/bm-1);year_info[name]['max_full_month_deterioration_pct']=float(rel.iloc[:12].max())
 diagnostics[str(year)]={'models':year_info,'group_input_sha256':sha256(gp_path)}
records=pd.DataFrame(records);records['delta_vs_official_pct']=records.apply(lambda r:100*(r.W/records.loc[(records.year==r.year)&(records.model=='Official baseline'),'W'].iloc[0]-1),axis=1);records['delta_vs_sm41_pct']=records.apply(lambda r:100*(r.W/records.loc[(records.year==r.year)&(records.model=='SM41'),'W'].iloc[0]-1),axis=1)
records['status']='Run'
missing=[]
for y in (2023,2024):
 for name in ('SM42 F4 seed7','SM42 F3 seed7','SM42 selected ensemble','SM42 F4 3-seed'):
  if not ((records.year==y)&(records.model==name)).any(): missing.append({'year':y,'model':name,'status':'Not Run'})
records=pd.concat([records,pd.DataFrame(missing)],ignore_index=True)
records.to_csv(out/'baseline_comparison.csv',index=False);pd.DataFrame(monthly).to_csv(out/'monthly_comparison.csv',index=False)
(out/'benchmark_diagnostics.json').write_text(json.dumps(diagnostics,indent=2),encoding='utf-8')
(out/'baseline_reproduction.json').write_text(json.dumps({'official_2023':json.loads((out/'baseline_2023_manifest.json').read_text()),'official_2024':json.loads((out/'baseline_2024_manifest.json').read_text()),'selection':selection,'comparison_sha256':sha256(out/'baseline_comparison.csv')},indent=2),encoding='utf-8')
