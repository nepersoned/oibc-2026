import sys,json,hashlib
from pathlib import Path
import pandas as pd
import numpy as np
sys.path.insert(0,'src')
from analysis.sm39_group_site_integration import redistribute,hourly_penalties,sha256
import scoring as sc
out=Path('outputs/sm41'); out.mkdir(parents=True,exist_ok=True)
sites=sc.load_sites(); comp=sc.reference_composition(sites); smp=sc.load_smp()
a,b=sc.window('2023-06-01','2024-06-01'); times=pd.date_range(a,b,freq='h')
gp=pd.read_parquet('outputs/sm39/group_pred_2023.parquet'); actual=sc.load_actual('2023-06-01','2024-06-01')
results={}
for name,path in [('baseline','outputs/val_sm37_noext_repro_2023_sites.parquet'),('F2','outputs/val_sm41_cloud_2023_sites.parquet')]:
 pred=redistribute(pd.read_parquet(path),gp,sites,comp,.2,times)
 detail=hourly_penalties(pred,actual,comp,smp)
 results[name]={'W':float(detail.pen.sum()),'W_1115':float(detail.loc[detail.ts.dt.hour.between(11,15),'pen'].sum()),'group':detail.groupby('group').pen.sum().to_dict(),'input_sha256':sha256(Path(path))}
 print(name,results[name],flush=True)
(out/'screen_2023.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
