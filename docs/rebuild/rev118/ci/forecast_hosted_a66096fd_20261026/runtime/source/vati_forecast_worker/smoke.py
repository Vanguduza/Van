"""Fixed synthetic upstream-stack smoke; no market or economic qualification.

The worker runs only behind the actual kernel/environment boundary. General
research jobs and all production use remain subject to their canonical grants,
immutable datasets, independent evidence and VATI authority.
"""


def run_fixture_smoke():
    from pathlib import Path
    from datetime import datetime,timedelta,timezone
    import hashlib,json,os,time,traceback

    from vati_forecast_worker.policy import require_worker_boundary,require_locked_environment
    worker_boundary=require_worker_boundary()
    if worker_boundary['role']!='RESEARCH_FIXTURE_SMOKE':raise ValueError('RESEARCH_ROLE_REQUIRED')
    locked_environment=require_locked_environment()
    ROOT=Path('/work')
    if not ROOT.is_dir():raise ValueError('WORKER_OUTPUT_DIRECTORY_UNAVAILABLE')
    Path(os.environ['HOME']).mkdir(parents=True,exist_ok=True)
    os.umask(0o077)
    report={'schema':'van.ml004.synthetic-stack-probe/1','status':'RUNNING',
            'data_environment':'FIXTURE','economic_evidence':False,'execution_authority':False,
            'worker_boundary':worker_boundary,'locked_environment':locked_environment,'cases':[],'unexecuted':['qlib_lightgbm','xgboost','neuralforecast','optuna','feast','mlflow']}


    def checkpoint():
        target=ROOT/'train-probe-receipt.json';tmp=target.with_suffix('.tmp')
        tmp.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');tmp.replace(target)


    def case(name,fn):
        at=time.monotonic()
        try:
            detail=fn();result={'case':name,'status':'PASS','detail':detail}
        except Exception as exc:
            traceback.print_exc();result={'case':name,'status':'FAIL','error_type':type(exc).__name__,'error':str(exc)}
        result['elapsed_seconds']=time.monotonic()-at
        report['cases'].append(result);report['unexecuted'].remove(name);checkpoint()
        print(json.dumps(result,allow_nan=False),flush=True)


    def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


    import torch
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    import numpy as np
    import pandas as pd
    import lightgbm as lgb

    native_omp=list((Path(torch.__file__).parent/'lib').glob('*gomp*'))
    report['bundled_openmp']={p.name:digest(p) for p in native_omp if p.is_file()}
    report['observed_cgroup']={name:(Path('/sys/fs/cgroup')/name).read_text().strip()
                              for name in ('cpu.max','memory.max','pids.max')}
    quota,period=report['observed_cgroup']['cpu.max'].split()
    assert int(quota)==2*int(period) and int(report['observed_cgroup']['memory.max'])==6*1024**3
    assert int(report['observed_cgroup']['pids.max'])==256 and not torch.cuda.is_available()
    dates=pd.date_range('2020-01-01',periods=48,freq='D')
    x=np.column_stack([np.linspace(-1,1,48),np.sin(np.arange(48)/4)]).astype('float64')
    y=2*x[:,0]+x[:,1]*.25


    def qlib_lightgbm():
        from qlib.contrib.model.gbdt import LGBModel
        from qlib.data.dataset import DatasetH
        from qlib.data.dataset.handler import DataHandlerLP
        from qlib.data.dataset.loader import StaticDataLoader
        from qlib.workflow import R,QlibRecorder
        from qlib.workflow.expm import MLflowExpManager
        index=pd.MultiIndex.from_product([dates,['FIXTURE_SERIES']],names=['datetime','instrument'])
        columns=pd.MultiIndex.from_tuples([('feature','x0'),('feature','x1'),('label','synthetic_y')])
        frame=pd.DataFrame(np.column_stack([x,y]),index=index,columns=columns)
        handler=DataHandlerLP(data_loader=StaticDataLoader(frame),infer_processors=[],learn_processors=[])
        dataset=DatasetH(handler=handler,segments={'train':(dates[0],dates[29]),
                        'valid':(dates[30],dates[37]),'test':(dates[38],dates[47])})
        R.register(QlibRecorder(MLflowExpManager(uri='sqlite:////work/qlib.sqlite',default_exp_name='van_stack_fixture')))
        model=LGBModel(num_boost_round=4,early_stopping_rounds=2,num_leaves=4,min_data_in_leaf=1,num_threads=1)
        with R.start(experiment_name='van_stack_fixture',recorder_name='fixed_source_smoke'):
            model.fit(dataset,verbose_eval=0)
            expected=model.predict(dataset).to_numpy()
            path=ROOT/'qlib-lightgbm.txt';model.model.save_model(str(path))
        restored=lgb.Booster(model_file=str(path));actual=restored.predict(x[38:])
        assert len(actual)==10 and np.isfinite(actual).all()
        error=float(np.max(np.abs(expected-actual)));assert error<1e-12
        return {'rows':10,'native_format':'LIGHTGBM_TEXT','max_abs_reload_error':error,
                'artifact_sha256':digest(path),'expected_predictions':[float(v) for v in expected],'actual_qlib_model_fit':True,'data_provider_used':False}


    def xgboost():
        import xgboost as xgb
        train=xgb.DMatrix(x[:30],label=y[:30]);test=xgb.DMatrix(x[38:])
        model=xgb.train({'objective':'reg:squarederror','tree_method':'hist','device':'cpu',
                         'nthread':1,'max_depth':2,'eta':.2},train,num_boost_round=4)
        expected=model.predict(test);path=ROOT/'xgboost.json';model.save_model(path)
        restored=xgb.Booster();restored.load_model(path);actual=restored.predict(test)
        error=float(np.max(np.abs(expected-actual)));assert error<1e-12 and np.isfinite(actual).all()
        return {'rows':len(actual),'native_format':'XGBOOST_JSON','max_abs_reload_error':error,'artifact_sha256':digest(path),'expected_predictions':[float(v) for v in expected]}


    def neuralforecast():
        from neuralforecast import NeuralForecast
        from neuralforecast.models import NHITS
        frame=pd.DataFrame({'unique_id':'FIXTURE_SERIES','ds':dates,'y':np.sin(np.arange(48)/4)+np.arange(48)*.05})
        model=NHITS(h=2,input_size=8,max_steps=2,mlp_units=[[8,8],[8,8],[8,8]],
            batch_size=1,windows_batch_size=16,inference_windows_batch_size=16,val_check_steps=1,
            random_seed=17,accelerator='cpu',devices=1,logger=False,enable_checkpointing=False,
            enable_progress_bar=False,enable_model_summary=False)
        nf=NeuralForecast(models=[model],freq='D');nf.fit(df=frame,val_size=0,verbose=False)
        expected=nf.predict(df=frame)['NHITS'].to_numpy()
        path=ROOT/'neuralforecast';nf.save(str(path),save_dataset=False)
        files=list(path.iterdir());assert files and all(p.suffix in {'.json','.safetensors'} for p in files)
        config=json.loads((path/'configuration.json').read_text());assert config['nf_format']=='2'
        restored=NeuralForecast.load(str(path),allow_pickle=False,trust_remote=False)
        actual=restored.predict(df=frame)['NHITS'].to_numpy()
        error=float(np.max(np.abs(expected-actual)));assert len(actual)==2 and np.isfinite(actual).all() and error<1e-6
        return {'rows':2,'native_format':'NEURALFORECAST_V2_JSON_SAFETENSORS','max_abs_reload_error':error,
                'allow_pickle':False,'trust_remote':False,'expected_predictions':[float(v) for v in expected],'artifacts':{p.name:digest(p) for p in files}}


    def optuna():
        import optuna as native
        uri='sqlite:////work/optuna.sqlite'
        study=native.create_study(study_name='van_fixed_stack_fixture',storage=uri,
                                  sampler=native.samplers.TPESampler(seed=17),direction='minimize')
        study.optimize(lambda trial:(trial.suggest_float('fixture_x',-1,1)-.25)**2,n_trials=2,n_jobs=1,timeout=20)
        restored=native.load_study(study_name=study.study_name,storage=uri)
        assert len(restored.trials)==2 and all(t.state is native.trial.TrialState.COMPLETE for t in restored.trials)
        return {'trial_count':2,'states':[t.state.name for t in restored.trials],'objective_is_fixture_math':True}


    def feast():
        from feast import FeatureStore,Entity,FeatureView,Field,FileSource,ValueType
        from feast.types import Float64
        import yaml
        path=ROOT/'feast';path.mkdir()
        now=datetime.now(timezone.utc)
        frame=pd.DataFrame({'fixture_id':[7,7],'value':[1.25,2.5],
            'event_timestamp':[now-timedelta(minutes=10),now-timedelta(minutes=1)]})
        frame.to_parquet(path/'input.parquet',index=False)
        (path/'feature_store.yaml').write_text(yaml.safe_dump({'project':'van_stack_fixture','provider':'local',
            'registry':str(path/'registry.db'),'online_store':{'type':'sqlite','path':str(path/'online.db')},
            'offline_store':{'type':'file'},'entity_key_serialization_version':3}))
        store=FeatureStore(repo_path=str(path))
        entity=Entity(name='fixture_entity',join_keys=['fixture_id'],value_type=ValueType.INT64)
        source=FileSource(path=str(path/'input.parquet'),timestamp_field='event_timestamp')
        view=FeatureView(name='fixture_view',entities=[entity],ttl=timedelta(days=1),
            schema=[Field(name='value',dtype=Float64)],online=True,source=source)
        store.apply([entity,view]);store.materialize(now-timedelta(hours=1),now)
        result=store.get_online_features(features=['fixture_view:value'],entity_rows=[{'fixture_id':7}]).to_dict()
        assert result['value']==[2.5],result
        return {'registry_exists':(path/'registry.db').is_file(),'sqlite_online_value':result['value'],
                'offline_source':'LOCAL_FIXTURE_PARQUET','network_provider_used':False}


    def mlflow():
        import mlflow as native
        uri='sqlite:////work/mlflow.sqlite';native.set_tracking_uri(uri)
        native.set_experiment('van_fixed_stack_fixture')
        artifact=ROOT/'fixture-artifact.json';artifact.write_text(json.dumps({'data_environment':'FIXTURE','economic_evidence':False}))
        with native.start_run(run_name='source_stack_smoke',log_system_metrics=False) as active:
            native.set_tags({'data_environment':'FIXTURE','economic_evidence':'false'})
            native.log_metric('fixture_value',1.0);native.log_artifact(str(artifact));run_id=active.info.run_id
        client=native.tracking.MlflowClient(tracking_uri=uri);original=client.get_run(run_id)
        assert original.info.status=='FINISHED' and original.data.metrics['fixture_value']==1.0
        listed=client.list_artifacts(run_id);assert any(p.path==artifact.name for p in listed)
        return {'run_id':run_id,'readback_status':original.info.status,'local_sqlite_metrics':True,'artifact_sha256':digest(artifact)}


    for name in tuple(report['unexecuted']):case(name,locals()[name])
    if all(r['status']=='PASS' for r in report['cases']):
        from vati_forecast_worker.artifacts import write_fixture_bundle
        report['model_bundle']=write_fixture_bundle(ROOT,report['cases'])
    report['status']='SOURCE_FIXTURE_SMOKE_PASS_NOT_UNIT_QUALIFICATION' if all(r['status']=='PASS' for r in report['cases']) else 'FAILED_SOURCE_FIXTURE_SMOKE'
    report['observed_memory_current']=(Path('/sys/fs/cgroup')/'memory.current').read_text().strip()
    checkpoint();print(json.dumps({'status':report['status'],'cases':len(report['cases'])}),flush=True)
    return 0 if all(r['status']=='PASS' for r in report['cases']) else 1

if __name__=='__main__':
    raise SystemExit(run_fixture_smoke())
