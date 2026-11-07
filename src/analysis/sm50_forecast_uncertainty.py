"""SM#50 diagnostic: forecast-derived uncertainty regimes vs frozen Site/Group W.

No fitting or submission-file generation occurs. Output contains aggregate diagnostics only.
"""
from __future__ import annotations
import hashlib, json, os, platform, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
os.environ.update({"OIBC_CAL_MODE":"weekday","OIBC_EXT_SOURCES":"no_openmeteo","OIBC_GFS":"0","OIBC_GEFS":"0","OIBC_UM":"0","OIBC_SRC":"prov","OIBC_SPATIAL":"none","OIBC_PHYSICS":"none"})
import scoring as sc
import features as ft
from analysis.sm39_group_site_integration import hourly_penalties, redistribute, sha256
from analysis.sm43_group_bagging import average_site_frames
OUT=ROOT/'outputs'/'sm50'
INDICATORS=['provider_cloud_disagreement','round_revision_magnitude','within_day_cloud_change','wa_temporal_sd','wb_temporal_sd','provider_temporal_sd_mean']


def _norm_ts(s):
    t=pd.to_datetime(s)
    if t.dt.tz is None: t=t.dt.tz_localize(sc.TZ)
    else: t=t.dt.tz_convert(sc.TZ)
    return t.astype(f'datetime64[ns, {sc.TZ}]')


def provider_hourly(path: Path, provider: str, station_col: str, cloud_col: str, start: pd.Timestamp, end: pd.Timestamp):
    f=pd.read_parquet(path,columns=[station_col,'round','ts',cloud_col])
    f['ts']=_norm_ts(f.ts)
    f=f[(f.ts>=start)&(f.ts<=end)].copy()
    f[cloud_col]=pd.to_numeric(f[cloud_col],errors='coerce')
    bad=(f[cloud_col]<0)|(f[cloud_col]>100)
    invalid=int(bad.sum()); f.loc[bad,cloud_col]=np.nan
    if f.duplicated([station_col,'round','ts']).any(): raise ValueError(f'{provider}: duplicate station-round-time keys')
    # Match the model's per-station policy: prefer round 17, then fill each missing
    # station-hour from round 10; only then compute the provider regional mean.
    station_round=f.pivot(index=[station_col,'ts'],columns='round',values=cloud_col)
    ix=station_round.index
    c10=station_round[10] if 10 in station_round else pd.Series(index=ix,dtype=float)
    c17=station_round[17] if 17 in station_round else pd.Series(index=ix,dtype=float)
    preferred=c17.combine_first(c10)
    long=pd.DataFrame({'preferred':preferred,'r10':c10,'r17':c17}).reset_index()
    reg=long.groupby('ts').agg(cloud=('preferred','mean'),r10=('r10','mean'),r17=('r17','mean'),
        n10=('r10','count'),n17=('r17','count'),npreferred=('preferred','count'))
    out=reg.rename(columns={'cloud':f'{provider}_cloud','r10':f'{provider}_r10',
        'r17':f'{provider}_r17','n10':f'{provider}_n10','n17':f'{provider}_n17'})
    out=out.reset_index()
    return out, {'rows_in_window':int(len(f)),'invalid_cloud_rows_outside_0_100':invalid,
                 'timestamps_with_cloud':int(out[f'{provider}_cloud'].notna().sum()),'station_round_timestamp_rows':int(len(f)),
                 'preferred_station_timestamp_rows':int(long.preferred.notna().sum())}


def uncertainty_days(wa_path:Path,wb_path:Path,start:pd.Timestamp,end:pd.Timestamp,sites:pd.DataFrame):
    wa,wa_audit=provider_hourly(wa_path,'wa','wa_station','wa_cloud',start,end)
    wb,wb_audit=provider_hourly(wb_path,'wb','wb_station','wb_cloud',start,end)
    h=wa.merge(wb,on='ts',how='outer',validate='one_to_one').sort_values('ts').reset_index(drop=True)
    h['target_day']=ft.target_day(h.ts)
    lat=float(sites.lat.median()); lon=float(sites.lon.median())
    elev,_,_=ft.solar(pd.DatetimeIndex(h.ts),np.full(len(h),lat),np.full(len(h),lon))
    h['daylight']=elev>0
    both=h.wa_cloud.notna()&h.wb_cloud.notna()
    h['disagree']=np.where(both,(h.wa_cloud-h.wb_cloud).abs(),np.nan)
    h['wa_revision']=(h.wa_r17-h.wa_r10).abs()
    h['wb_revision']=(h.wb_r17-h.wb_r10).abs()
    rev=pd.concat([h.wa_revision,h.wb_revision],axis=1)
    h['revision']=rev.mean(axis=1,skipna=True)
    h['cloud_ensemble']=h[['wa_cloud','wb_cloud']].mean(axis=1,skipna=True)
    # Consecutive valid adjacent hours within a target day only.
    h['previous_day']=h.target_day.shift(1)
    h['previous_ts']=h.ts.shift(1)
    h['previous_cloud']=h.cloud_ensemble.shift(1)
    adjacent=(h.target_day==h.previous_day)&((h.ts-h.previous_ts)==pd.Timedelta(hours=1))
    h['cloud_change']=np.where(adjacent,(h.cloud_ensemble-h.previous_cloud).abs(),np.nan)
    rows=[]
    for day,g in h[h.daylight].groupby('target_day',sort=True):
        wa_sd=float(g.wa_cloud.std(ddof=0)) if g.wa_cloud.notna().sum()>=2 else np.nan
        wb_sd=float(g.wb_cloud.std(ddof=0)) if g.wb_cloud.notna().sum()>=2 else np.nan
        rows.append({'target_day':day,
          'provider_cloud_disagreement':float(g.disagree.mean()) if g.disagree.notna().any() else np.nan,
          'round_revision_magnitude':float(g.revision.mean()) if g.revision.notna().any() else np.nan,
          'within_day_cloud_change':float(g.cloud_change.mean()) if g.cloud_change.notna().any() else np.nan,
          'wa_temporal_sd':wa_sd,'wb_temporal_sd':wb_sd,
          'provider_temporal_sd_mean':float(np.mean([wa_sd,wb_sd])) if np.isfinite([wa_sd,wb_sd]).all() else np.nan,
          'daylight_forecast_hours':int(len(g)),
          'paired_provider_hours':int(g.disagree.notna().sum()),
          'round_revision_provider_hours':int(g.revision.notna().sum())})
    result=pd.DataFrame(rows)
    if result.empty: raise ValueError('no daylight daily uncertainty rows in selected window')
    return result,{'WA':wa_audit,'WB':wb_audit,'hour_rows':int(len(h)),
        'daylight_hour_rows':int(h.daylight.sum()),'daily_indicator_rows':int(len(result)),
        'coordinate_basis':'median of supplied sites.csv lat/lon; only solar daylight mask, no external join'}


def locked_tertiles(train:pd.DataFrame,valid:pd.DataFrame):
    cut={}; bins=valid[['target_day']].copy()
    for col in INDICATORS:
        vals=train[col].replace([np.inf,-np.inf],np.nan).dropna()
        q=np.quantile(vals.to_numpy(),[1/3,2/3]) if len(vals)>=30 else np.array([np.nan,np.nan])
        if not np.isfinite(q).all() or q[0]>=q[1]:
            cut[col]={'q33':None,'q67':None,'training_days_finite':int(len(vals)),'available':False}
            bins[col+'_bin']=pd.NA
        else:
            cut[col]={'q33':float(q[0]),'q67':float(q[1]),'training_days_finite':int(len(vals)),'available':True}
            bins[col+'_bin']=pd.cut(valid[col],[-np.inf,q[0],q[1],np.inf],labels=['low','middle','high'],include_lowest=True)
    return bins,cut


def evaluation_predictions(year,sites,comp):
    start=f'{year}-06-01'; end=f'{year+1}-06-01'
    a,b=sc.window(start,end); times=pd.date_range(a,b,freq='h').astype(f'datetime64[ns, {sc.TZ}]')
    site_path=OUT.parent/'sm45'/f'{year}_A1_B0_site_only_sites.parquet'
    group_path=OUT.parent/'sm45'/f'group_a1_{year}.parquet'
    site=pd.read_parquet(site_path); group=pd.read_parquet(group_path)
    site['ts']=sc.to_ts(site.ts); group['ts']=sc.to_ts(group.ts)
    expected_site=len(sites)*len(times); expected_group=2*len(times)
    if len(site)!=expected_site or site.duplicated(['site_id','ts']).any(): raise ValueError(f'{year}: Site prediction grid invalid')
    if len(group)!=expected_group or group.duplicated(['group','ts']).any(): raise ValueError(f'{year}: Group prediction grid invalid')
    preds={alpha:redistribute(site,group,sites,comp,alpha,times) for alpha in (0.0,1.0,0.2)}
    actual=sc.load_actual(start,end); smp=sc.load_smp()
    detail={}
    for alpha,pred in preds.items():
        hourly=hourly_penalties(pred,actual,comp,smp)
        w=float(hourly.pen.sum()); api=float(sc.score(pred,comp,actual,smp)['W'])
        if not np.isclose(w,api,atol=1e-5,rtol=0): raise AssertionError(f'{year} alpha {alpha}: hourly/scorer mismatch {w} {api}')
        detail[alpha]=hourly
    input_paths=[site_path,group_path]
    meta={'site_path':str(site_path.relative_to(ROOT)),'site_sha256':sha256(site_path),
          'group_path':str(group_path.relative_to(ROOT)),'group_sha256':sha256(group_path),
          'site_rows':int(len(site)),'group_rows':int(len(group)),
          'observed_site_hours':int(len(actual)),'expected_site_rows':expected_site,
          'expected_group_rows':expected_group,'scorer_crosscheck':'independent hourly sum equals scoring.score within 1e-5 KRW',
          'overall_W':{str(k):float(v.pen.sum()) for k,v in detail.items()},
          'g2_2023_training_labels':0 if year==2023 else None}
    obs_site_counts=actual.groupby('ts').size()
    return times,preds,detail,meta,obs_site_counts


def summarize_regime(year,times,preds,details,uncertainty,obs_site_counts):
    # Map every settlement timestamp to its right-closed target day.
    score_days=pd.DataFrame({'ts':times}); score_days['target_day']=ft.target_day(score_days.ts)
    rows=[]; permonth=[]; corr_rows=[]; bin_maps={}
    for col in INDICATORS:
        bins=uncertainty[['target_day',col+'_bin']].dropna(subset=[col+'_bin']).copy()
        for level in ['low','middle','high']:
            days=set(bins.loc[bins[col+'_bin'].astype(str)==level,'target_day'])
            if not days: continue
            ts_bin=score_days[score_days.target_day.isin(days)].ts
            for alpha,detail in details.items():
                d=detail[detail.ts.isin(ts_bin)].copy()
                if d.empty: continue
                grp=d.groupby('group').pen.sum().to_dict()
                peak=d[d.ts.dt.hour.between(11,15)].pen.sum(); nonpeak=d[~d.ts.dt.hour.between(11,15)].pen.sum()
                rows.append({'year':year,'indicator':col,'bin':level,'model':{0.0:'Site-only',1.0:'Group-only',0.2:'fixed alpha=0.2'}[alpha],
                    'days':len(days),'scored_group_hours':int(len(d)),
                    'observed_site_hours':int(obs_site_counts.reindex(d.ts.drop_duplicates()).sum()),
                    'W':float(d.pen.sum()),'W_per_scored_day':float(d.pen.sum()/len(days)),
                    'G1_W':float(grp.get('G1',0)),'G2_W':float(grp.get('G2',0)),
                    'peak_11_15_W':float(peak),'nonpeak_W':float(nonpeak),
                    'peak_group_hours':int(d.ts.dt.hour.between(11,15).sum()),
                    'nonpeak_group_hours':int((~d.ts.dt.hour.between(11,15)).sum()),
                    'W_per_observed_site_hour':float(d.pen.sum()/obs_site_counts.reindex(d.ts.drop_duplicates()).sum()),
                    'W_per_group_hour':float(d.pen.sum()/len(d)),
                    'peak_W_per_group_hour':float(peak/max(1,d.ts.dt.hour.between(11,15).sum())),
                    'nonpeak_W_per_group_hour':float(nonpeak/max(1,(~d.ts.dt.hour.between(11,15)).sum())),
                    'signed_error_kwh':float((d.pred-d.act).sum()),
                    'months':int(d.ts.dt.strftime('%Y-%m').nunique())})
                dm=d.assign(month=d.ts.dt.strftime('%Y-%m'),peak=d.ts.dt.hour.between(11,15)).groupby('month')
                for month,md in dm:
                    permonth.append({'year':year,'indicator':col,'bin':level,'model':rows[-1]['model'],'month':month,
                        'days':int((md.ts-pd.Timedelta(hours=1)).dt.floor('D').nunique()),'scored_group_hours':int(len(md)),
                        'peak_group_hours':int(md.peak.sum()),'nonpeak_group_hours':int((~md.peak).sum()),
                        'W':float(md.pen.sum()),'peak_W':float(md.loc[md.peak,'pen'].sum()),
                        'nonpeak_W':float(md.loc[~md.peak,'pen'].sum()),
                        'W_per_group_hour':float(md.pen.sum()/len(md))})
            # signed residual correlation, Site vs Group on matched group-hour observed rows.
            s=details[0.0].query('ts in @ts_bin')[['group','ts','pred','act']].rename(columns={'pred':'site_pred'})
            g=details[1.0].query('ts in @ts_bin')[['group','ts','pred','act']].rename(columns={'pred':'group_pred'})
            m=s.merge(g,on=['group','ts','act'],validate='one_to_one')
            if len(m)>=3 and m.site_pred.std()>0 and m.group_pred.std()>0:
                corr_rows.append({'year':year,'indicator':col,'bin':level,'group':'pooled G1+G2 group-hours',
                    'paired_group_hours':int(len(m)),'residual_correlation':float((m.site_pred-m.act).corr(m.group_pred-m.act))})
            for group in ['G1','G2']:
                mg=m[m.group==group]
                if len(mg)>=3 and mg.site_pred.std()>0 and mg.group_pred.std()>0:
                    corr_rows.append({'year':year,'indicator':col,'bin':level,'group':group,
                        'paired_group_hours':int(len(mg)),'residual_correlation':float((mg.site_pred-mg.act).corr(mg.group_pred-mg.act))})
    return pd.DataFrame(rows),pd.DataFrame(permonth),pd.DataFrame(corr_rows)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    sites=sc.load_sites(); comp=sc.reference_composition(sites); smp=sc.load_smp()
    data=Path(sc.DATA); train_wa=data/'train'/'forecast_wa.parquet'; train_wb=data/'train'/'forecast_wb.parquet'
    all_results={'experiment':'SM#50 forecast uncertainty regime diagnostic','training_performed':False,
      'submission_created':False,'calendar_mode':os.environ.get('OIBC_CAL_MODE'),'years':{},
      'indicator_definitions':INDICATORS,'forecast_inputs':{},'outputs':{},
      'data_lineage':{'analysis_script_sha256':sha256(Path(__file__).resolve()),
        'preregistration_sha256':sha256(ROOT/'SM50_PREREGISTRATION.md'),
        'git_revision':__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'evaluation_actuals_used_only_for_scoring':True,'evaluation_actuals_used_for_regimes_or_cutpoints':False,
        'external_weather_loaded':False,'external_holiday_data_loaded':False,'coordinates_used_only_for_daylight_mask':True,
        'sm45_manifest_sha256':sha256(ROOT/'outputs'/'sm45'/'manifest.json'),
        'features_py_sha256':sha256(ROOT/'src'/'features.py'),
        'sites_csv_sha256':sha256(data/'sites.csv'),
        'train_generation_sha256':sha256(data/'train'/'generation.parquet'),
        'train_smp_sha256':sha256(data/'train'/'smp.csv')}}
    summaries=[]; months=[]; correlations=[]; daily_frames=[]
    for year in (2023,2024):
        eval_start=pd.Timestamp(f'{year}-06-01 00:00',tz=sc.TZ); eval_end=pd.Timestamp(f'{year+1}-06-01 00:00',tz=sc.TZ)
        train_start=eval_start-pd.DateOffset(years=2)
        train_first=train_start+pd.Timedelta(hours=1)
        valid_first=eval_start+pd.Timedelta(hours=1)
        train_u,audit_tr=uncertainty_days(train_wa,train_wb,train_first,eval_start,sites)
        valid_u,audit_va=uncertainty_days(train_wa,train_wb,valid_first,eval_end,sites)
        bins,cuts=locked_tertiles(train_u,valid_u)
        valid=valid_u.merge(bins,on='target_day',validate='one_to_one')
        times,preds,details,pred_meta,obs_site_counts=evaluation_predictions(year,sites,comp)
        summ,month,corr=summarize_regime(year,times,preds,details,valid,obs_site_counts)
        summaries.append(summ); months.append(month); correlations.append(corr)
        daily_frames.append(valid.assign(year=year))
        all_results['years'][str(year)]={'train_forecast_window':{'first_valid_ts':str(train_first),'last_valid_ts':str(eval_start)},
          'validation_window_right_closed':{'first_valid_ts':str(valid_first),'last_valid_ts':str(eval_end)},
          'training_forecast_audit':audit_tr,'validation_forecast_audit':audit_va,
          'train_only_tertile_cutpoints':cuts,'prediction_and_score_audit':pred_meta,
          'indicator_validation_missing_days':{c:int(valid[c].isna().sum()) for c in INDICATORS},
          'bin_day_counts':{c:{str(k):int(v) for k,v in valid[c+'_bin'].value_counts(dropna=False).items()} for c in INDICATORS}}
        # A compact overall diagnostic and best fixed model per uncertainty bin.
        all_results['years'][str(year)]['overall_best_fixed_model']={k:min(v,key=v.get) for k,v in pred_meta['overall_W'].items()} if False else None
    if summaries:
        s=pd.concat([x for x in summaries if not x.empty],ignore_index=True); m=pd.concat([x for x in months if not x.empty],ignore_index=True); c=pd.concat([x for x in correlations if not x.empty],ignore_index=True)
    else: raise ValueError('no valid results')
    s.to_csv(OUT/'regime_scores.csv',index=False); m.to_csv(OUT/'regime_monthly_w.csv',index=False); c.to_csv(OUT/'residual_correlations.csv',index=False)
    pd.concat(daily_frames,ignore_index=True).to_csv(OUT/'daily_uncertainty_bins.csv',index=False)
    for key,fn in [('regime_scores','regime_scores.csv'),('regime_monthly','regime_monthly_w.csv'),('residual_correlations','residual_correlations.csv'),('daily_uncertainty_bins','daily_uncertainty_bins.csv')]:
        all_results['outputs'][fn]={'sha256':sha256(OUT/fn),'bytes':(OUT/fn).stat().st_size}
    all_results['forecast_inputs']['train_forecast_wa']={'path':str(train_wa.relative_to(ROOT)),'sha256':sha256(train_wa)}
    all_results['forecast_inputs']['train_forecast_wb']={'path':str(train_wb.relative_to(ROOT)),'sha256':sha256(train_wb)}
    all_results['forecast_inputs']['scoring_smp']={'path':str((data/'train'/'smp.csv').relative_to(ROOT)),'sha256':sha256(data/'train'/'smp.csv')}
    all_results['runtime']={'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__}
    all_results['readme_cloud_units']='forecast_wa.wa_cloud and forecast_wb.wb_cloud are percent (0-100); out-of-range treated missing'
    all_results['interpretation_limits']=['Observed-site mask is shared; Group CF training denominator and fixed-capacity inference are not the same as observed-sum scoring.',
       '2023 Group G2 has zero eligible min_cov=0.3 labels; G2 comparisons are extrapolative.',
       '2024 validation and these splits have been reused; associations are not causal and do not form an independent test.',
       'Group-only was allocated with frozen Site forecast shape to common observed rows; it is an evaluation construction, not an observed-subset-trained forecast.']
    (OUT/'diagnostics.json').write_text(json.dumps(all_results,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    print(json.dumps({'training_performed':False,'score_rows':len(s),'monthly_rows':len(m),'correlation_rows':len(c),
      'period_overall_W':{y:v['prediction_and_score_audit']['overall_W'] for y,v in all_results['years'].items()},
      'cutpoints':{y:v['train_only_tertile_cutpoints'] for y,v in all_results['years'].items()}},indent=2,ensure_ascii=False))

if __name__=='__main__': main()

