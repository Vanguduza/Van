"""Cold fixed-fixture inference. No training, owner data or execution authority."""


def run_fixture_inference():
    from pathlib import Path
    import json,os
    from vati_forecast_worker.policy import require_worker_boundary,require_locked_environment
    from vati_forecast_worker.artifacts import verified_fixture_bundle
    boundary=require_worker_boundary();environment=require_locked_environment()
    if boundary['role']!='INFERENCE_FIXTURE_SMOKE':raise ValueError('INFERENCE_ROLE_REQUIRED')
    os.umask(0o077)
    import torch
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    import numpy as np
    import pandas as pd
    import lightgbm as lgb
    import xgboost as xgb
    from neuralforecast import NeuralForecast
    dates=pd.date_range('2020-01-01',periods=48,freq='D')
    x=np.column_stack([np.linspace(-1,1,48),np.sin(np.arange(48)/4)]).astype('float64')
    series=pd.DataFrame({'unique_id':'FIXTURE_SERIES','ds':dates,
        'y':np.sin(np.arange(48)/4)+np.arange(48)*.05})
    results={}
    with verified_fixture_bundle('/artifacts') as (root,manifest):
        light=lgb.Booster(model_file=str(root/'qlib-lightgbm.txt'))
        results['qlib_lightgbm']=light.predict(x[38:])
        booster=xgb.Booster();booster.load_model(root/'xgboost.json')
        results['xgboost']=booster.predict(xgb.DMatrix(x[38:]))
        nf=NeuralForecast.load(str(root/'neuralforecast'),allow_pickle=False,trust_remote=False)
        results['neuralforecast']=nf.predict(df=series)['NHITS'].to_numpy()
        errors={}
        for name,values in results.items():
            expected=np.asarray(manifest['expected_predictions'][name]);actual=np.asarray(values)
            if actual.shape!=expected.shape or not np.isfinite(actual).all():raise ValueError('INFERENCE_SHAPE_OR_FINITE_MISMATCH')
            errors[name]=float(np.max(np.abs(actual-expected)))
            if errors[name]>1e-6:raise ValueError('INFERENCE_EXPORT_LOAD_PARITY_FAILURE')
    report={'schema':'van.ml004.fixed-fixture-inference/1','status':'SOURCE_FIXTURE_INFERENCE_PASS',
        'data_environment':'FIXTURE','economic_evidence':False,'execution_authority':False,
        'worker_boundary':boundary,'locked_environment':environment,'model_rows':{k:len(v) for k,v in results.items()},
        'max_abs_reload_errors':errors,'training_executed':False,'allow_pickle':False,'trust_remote':False}
    Path('/work/inference-receipt.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report,allow_nan=False),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(run_fixture_inference())
