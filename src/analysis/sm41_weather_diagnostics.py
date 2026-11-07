"""Descriptive 2024 conditional residual diagnostics, never used for prediction."""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd
from scipy import stats
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scoring as sc
from analysis.sm39_group_site_integration import redistribute,hourly_penalties
sites=sc.load_sites(); comp=sc.reference_composition(sites); smp=sc.load_smp()
a,b=sc.window('2024-06-01','2025-06-01'); ts=pd.date_range(a,b,freq='h')
actual=sc.load_actual('2024-06-01','2025-06-01')
sp=pd.read_parquet('outputs/val_sm37_noext_repro_sites.parquet'); gp=pd.read_parquet('outputs/sm39/group_pred_2024.parquet')
details={}
for name,alpha in [('site',0.),('group',1.),('blend',.2)]:
 pred=redistribute(sp,gp,sites,comp,alpha,ts)
 d=hourly_penalties(pred,actual,comp,smp); d['err']=d.pred-d.act
 details[name]=d[['group','ts','err','pen']].rename(columns={'err':'err_'+name,'pen':'pen_'+name})
d=details['site'].merge(details['group'],on=['group','ts']).merge(details['blend'],on=['group','ts'])
f=pd.read_parquet(Path(sc.DATA)/'train'/'forecast_wa.parquet',columns=['wa_station','round','ts','wa_cloud']); f['ts']=sc.to_ts(f.ts)
f=f[(f.ts>=a)&(f.ts<=b)]; f.wa_cloud=f.wa_cloud.clip(0,100)
r=f.groupby(['ts','round']).wa_cloud.mean().unstack('round'); r['cloud']=r[17].fillna(r[10]); r['revision']=(r[17]-r[10]).abs()
r['regime']=np.select([r.revision>=20,r.cloud<30,r.cloud>=70],['unstable','clear','cloudy'],default='mixed')
d=d.merge(r[['cloud','revision','regime']],on='ts',how='left'); d=d[d.ts.dt.hour.between(9,16)]
rows=[]
for (group,regime),x in d.groupby(['group','regime']):
 e=x.err_blend.to_numpy(); s=x.err_site.to_numpy(); g=x.err_group.to_numpy()
 if len(e)<10: continue
 rows.append({'group':group,'regime':regime,'n':len(e),'mean':float(e.mean()),'std':float(e.std(ddof=1)),'median':float(np.median(e)),'q05':float(np.quantile(e,.05)),'q95':float(np.quantile(e,.95)),'skew':float(stats.skew(e)),'excess_kurtosis':float(stats.kurtosis(e)),'normaltest_p':float(stats.normaltest(e).pvalue),'site_group_corr':float(np.corrcoef(s,g)[0,1]),'site_group_cov':float(np.cov(s,g)[0,1]),'W':float(x.pen_blend.sum())})
out=Path('outputs/sm41'); out.mkdir(exist_ok=True,parents=True); (out/'weather_diagnostics.json').write_text(json.dumps(rows,indent=2),encoding='utf-8'); print(json.dumps(rows,indent=2))
