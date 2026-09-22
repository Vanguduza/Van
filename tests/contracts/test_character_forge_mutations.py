from copy import deepcopy
from tools.character_forge.gates import contract_surface_problems
BASE={"artboard":"Van","state_machine":"VanRuntime","inputs":[{"name":"state"},{"name":"speaking"},{"name":"listening"},{"name":"attention_x"},{"name":"attention_y"},{"name":"mouth_open"},{"name":"urgency"},{"name":"viseme"},{"name":"action_code"}],"triggers":["point","ack","celebrate","warning","wave","shrug","present","panel"],"durable_states":{f"S{i}":i for i in range(18)},"finite_actions":{f"A{i}":i for i in range(1,15)}}

def test_contract_guard_rejects_removed_state():
    x=deepcopy(BASE); x["durable_states"].pop("S17"); assert contract_surface_problems(x)
def test_contract_guard_rejects_renamed_input():
    x=deepcopy(BASE); x["inputs"][3]["name"]="attentionX"; assert contract_surface_problems(x)
def test_contract_guard_rejects_artboard_case_drift():
    x=deepcopy(BASE); x["artboard"]="VAN"; assert contract_surface_problems(x)
def test_contract_guard_rejects_removed_action():
    x=deepcopy(BASE); x["finite_actions"].pop("A14"); assert contract_surface_problems(x)
