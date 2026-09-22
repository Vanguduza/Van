import yaml
from tools.character_forge.gates import evaluate
from tools.character_forge.status import load_status, validate_status
from tools.character_forge.manifest import load_yaml

def test_status_vocabulary_and_implications():
    assert validate_status(load_status())==[]

def test_build_ready_never_precedes_m0():
    status=load_status()
    if status["build_ready"]: assert evaluate("m0").passed

def test_external_asset_state_is_honest_before_release():
    status=load_status()
    if status["qual_emb_01"]!="READY":
        assert status["qual_emb_01"]=="EXTERNAL_ARTEFACT"
