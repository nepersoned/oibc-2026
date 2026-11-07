"""Choose F3 or F4 using 2023 seed7 W alone; write frozen decision."""
import json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scoring as sc
from analysis.sm39_group_site_integration import redistribute,hourly_penalties,sha256
out=Path('outputs/sm42');site=sc.load_sites();comp=sc.reference_composition(site);smp=sc.load_smp();start,end=sc.window('2023-06-01','2024-06-01');times=pd.date_range(start,end,freq='h'); actual=sc.load_actual('2023-06-01','2024-06-01');gp=pd.read_parquet('outputs/sm39/group_pred_2023.parquet')
files={'baseline':Path('outputs/val_sm37_noext_repro_2023_sites.parquet'),'f4':Path('outputs/val_sm42_f4_seed7_2023_sites.parquet'),'f3':Path('outputs/val_sm42_f3_seed7_2023_sites.parquet')}; result={}
for name,path in files.items():
 p=redistribute(pd.read_parquet(path),gp,site,comp,.2,times); det=hourly_penalties(p,actual,comp,smp); w=float(det.pen.sum()); assert abs(w-sc.score(p,comp,actual,smp)['W'])<.0001
 result[name]={'W':w,'sha256':sha256(path)}; print(name,w,flush=True)
selected=min(('f3','f4'),key=lambda name:(result[name]['W'],3 if name=='f3' else 4))
if result[selected]['W']>=result['baseline']['W']:selected=None
result['selected_2023_only']=selected
(out/'screen_2023.json').write_text(json.dumps(result,indent=2));print('selected',selected,flush=True)
