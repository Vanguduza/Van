"""Process import boundary for the dedicated T0 trading-session command.

Model workers are separate processes. This guard is a Python import boundary,
not an operating-system sandbox or authority for credentials, risk or orders.
"""
import importlib.abc
import sys
import threading


MODEL_FRAMEWORK_ROOTS=frozenset({
    'qlib','lightgbm','neuralforecast','xgboost','optuna','feast','mlflow',
    'torch','torchvision','torchaudio','pytorch_lightning','lightning',
    'tensorflow','keras','sklearn','ray','safetensors',
})
_lock=threading.RLock()


class T0ModelImportError(ImportError):
    pass


class _T0ModelFinder(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.partition('.')[0] in MODEL_FRAMEWORK_ROOTS:
            raise T0ModelImportError('FORECAST_MODEL_IMPORT_IN_T0:'+fullname)
        return None


def install_t0_model_guard():
    """Install before session construction; an already loaded model refuses startup.

    No caller profile, environment switch or model metadata can relax this guard.
    Existing execution-worker credential handling remains outside model authority.
    """
    with _lock:
        loaded=sorted({name.partition('.')[0] for name in sys.modules
                       if name.partition('.')[0] in MODEL_FRAMEWORK_ROOTS})
        if loaded:
            raise T0ModelImportError('T0_MODEL_ALREADY_LOADED:'+','.join(loaded))
        if not any(isinstance(finder,_T0ModelFinder) for finder in sys.meta_path):
            sys.meta_path.insert(0,_T0ModelFinder())
