import json,time,os,importlib,importlib.metadata
from pathlib import Path
Path(os.environ['HOME']).mkdir(parents=True,exist_ok=True)
start=time.monotonic();result={'status':'IMPORT_PROBE_NOT_TRAIN_OR_QUALIFICATION','versions':{},'environment_names':sorted(os.environ),'cgroup':{}}
for name in ('cpu.max','memory.max','pids.max','memory.current'):
 p=Path('/sys/fs/cgroup')/name
 result['cgroup'][name]=p.read_text().strip() if p.exists() else None
for module,distribution in [('qlib','pyqlib'),('lightgbm','lightgbm'),('neuralforecast','neuralforecast'),('xgboost','xgboost-cpu'),('optuna','optuna'),('feast','feast'),('mlflow','mlflow'),('torch','torch')]:
 at=time.monotonic();importlib.import_module(module);result['versions'][distribution]={'version':importlib.metadata.version(distribution),'import_seconds':time.monotonic()-at}
import torch
torch.set_num_threads(1);result['cuda_available']=torch.cuda.is_available();result['elapsed_seconds']=time.monotonic()-start
print(json.dumps(result),flush=True)
