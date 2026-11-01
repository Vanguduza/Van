"""Synthetic verification-instrument evidence; never application/native execution."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from tools.rebuild import backend_public_source as gate
from tools.rebuild import public_source_shards as proof

HEAD = "a" * 40
CONTEXT = {"id": "synthetic-instrument-run", "attempt": "1"}


def isolated_media_pytest(tmp_path):
    """Tiny fixture runtime: only the original media pytest/plugin closure, no media app claim."""
    import importlib.metadata
    import sysconfig
    import venv
    folder=tmp_path/"media-instrument-venv"
    venv.EnvBuilder(with_pip=False).create(folder)
    site=folder/"lib"/("python"+sysconfig.get_python_version())/"site-packages"
    for name in ("pytest", "pytest-asyncio", "pluggy", "iniconfig", "packaging", "pygments", "typing-extensions"):
        distribution=importlib.metadata.distribution(name)
        for top in {Path(p).parts[0] for p in distribution.files if Path(p).parts[0] not in {"..", "__pycache__"}}:
            destination=site/top
            if not destination.exists():
                destination.symlink_to(distribution.locate_file(top),target_is_directory=distribution.locate_file(top).is_dir())
    return str(folder/"bin/python")


def write_json(path, value):
    path.write_text(json.dumps(value))


def seal(folder):
    receipt = json.loads((folder / "run.json").read_text())
    names = ["terminal.json", "phases.jsonl", "storage-audit.json", "generated-bytecode.json"]
    if receipt["mode"] == "execution":
        names.append("report.xml")
    receipt["artifact_sha256"] = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                                   for name in names if (folder / name).exists()}
    write_json(folder / "run.json", receipt)


def frame(folder, selection, runtime, nodeids, costs, index, count, *, control=False, root=None):
    folder.mkdir(parents=True)
    root = root or next(p/"synthetic-source" for p in folder.parents if (p/"synthetic-source").is_dir())
    cwd_identity = {"execution_cwd": "checkout", "invocation_cwd": str(root.resolve()),
        "protected_before": proof.protected_identity(root), "protected_after": proof.protected_identity(root)}
    bins = proof.assignment(nodeids, [r for r in selection["selected"] if gate.runtime(r["path"]) == runtime], costs, count)
    environment = {"python": "3.12.12", "implementation": "CPython", "system": "Linux", "machine": "x86_64",
        "image_os": "ubuntu24", "image_version": "synthetic-instrument-image", "packages": [["synthetic", "0"]],
        "node": "v24.19.0", "chromium_sha256": "c"*64,
        "pytest_entrypoints": sorted(proof.EXPLICIT_PLUGINS[runtime]),
        "pythonpath": list(proof.CANONICAL_PYTHONPATH),
        "postgres_version": 170011 if runtime == "gateway" else None,
        "isolated_pg_fixture": "1" if runtime == "gateway" else None}
    state = {**cwd_identity, "schema": proof.SCHEMA, "mode": "collection" if control else "execution", "runtime": runtime,
        "expected_commit": HEAD, "execution_id": "synthetic-"+folder.name, "workflow_run": CONTEXT, "source_before": {"commit": HEAD, "tree": "b"*40},
        "source_after": {"commit": HEAD, "tree": "b"*40}, "environment_before": environment,
        "pytest_inputs": {"config_sha256": hashlib.sha256(b"[pytest]\n").hexdigest(),
            "plugins": {p:"d"*64 for p in proof.EXPLICIT_PLUGINS[runtime]}, "autoload": False},
        "environment_after": copy.deepcopy(environment), "selection": selection,
        "selected": [r for r in selection["selected"] if gate.runtime(r["path"]) == runtime],
        "collection_errors": [], "internal_errors": [], "pytest_exit": 0, "generated_cache_candidates": [],
        "instrument_sha256": hashlib.sha256(Path(proof.__file__).read_bytes()).hexdigest(), "costs": costs,
        "full_collection": sorted(nodeids), "assignment": bins, "assigned": bins[index],
        "shard_index": index, "shard_count": count, "full_collection_sha256": proof.fingerprint(sorted(nodeids)),
        "assignment_sha256": proof.fingerprint(bins)}
    write_json(folder / "terminal.json", state)
    write_json(folder / "generated-bytecode.json", {"schema":"van.parent-verified-generated-bytecode/1",
        "expected_commit":HEAD,"input_bytecode_paths":[],"records":[]})
    write_json(folder / "storage-audit.json", {"root": str(root.resolve()), "invocation_cwd": str(root.resolve()), "schema": "van.source-storage-audit/1", "forbidden_events": [],
        "source_sha256": hashlib.sha256(Path(proof.__file__).with_name("source_storage_audit.py").read_bytes()).hexdigest()})
    events = []
    suite = ET.Element("testsuite")
    if not control:
        for node in bins[index]:
            for when in ("setup", "call", "teardown"):
                events.append({"nodeid": node, "when": when, "outcome": "passed", "skip_reason": None})
            case = ET.SubElement(suite, "testcase", classname=node.split("::")[0], name="synthetic_instrument_case")
            ET.SubElement(ET.SubElement(case, "properties"), "property", name="van_source_nodeid", value=node)
        (folder / "report.xml").write_bytes(ET.tostring(suite))
    (folder / "phases.jsonl").write_text("".join(json.dumps(e)+"\n" for e in events))
    write_json(folder / "run.json", {**cwd_identity, "expected_commit": HEAD, "workflow_run": CONTEXT,
        "terminal": True, "exit": 0, "mode": state["mode"], "execution_id": state["execution_id"], "generated_cache_outputs": [],
        "source_before": state["source_before"], "source_after": state["source_after"],
        "environment_before": copy.deepcopy(environment), "environment_after": copy.deepcopy(environment)})
    seal(folder)


@pytest.fixture
def instrument(tmp_path, monkeypatch):
    root = tmp_path / "synthetic-source"
    root.mkdir()
    (root/".git").mkdir()
    (root/"pytest.ini").write_text("[pytest]\n")
    paths = ["backend/tests/test_a.py", "backend/tests/test_b.py", "backend/tests/test_c.py",
        "backend/tests/test_jev_no_generic_executor.py", "services/source/test_media.py",
        *gate.PRIVATE, gate.FIREWALL]
    for rel in paths:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# synthetic verification-instrument source, not application acceptance\n")
    costs = {"schema": "synthetic-assignment-costs", "costs": {}}
    cost = root / "tools/rebuild/backend_public_source_costs.json"
    cost.parent.mkdir(parents=True)
    write_json(cost, costs)
    (cost.parent/"source_storage_audit.py").write_bytes(Path(proof.__file__).with_name("source_storage_audit.py").read_bytes())
    selection = gate.plan(root)
    gateway = [r["path"] + "::" + ("test_no_fabric_or_generic_operation_survives_the_b1_validator[fixture]"
        if r["path"].endswith("test_jev_no_generic_executor.py") else "test_case")
        for r in selection["selected"] if gate.runtime(r["path"]) == "gateway"]
    media = ["services/source/test_media.py::test_case"]
    out = tmp_path / "evidence"
    out.mkdir()
    write_json(out / "selection.json", selection)
    monkeypatch.setenv("GITHUB_RUN_ID", CONTEXT["id"])
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", CONTEXT["attempt"])
    monkeypatch.setattr(proof, "source_identity", lambda root, expected: {"commit": HEAD, "tree": "b"*40})
    frame(out / "gateway-control", selection, "gateway", gateway, costs, 0, 4, control=True)
    for i in range(4):
        frame(out / "shards" / f"van-backend-public-source-gateway-{i}", selection, "gateway", gateway, costs, i, 4)
    frame(out / "media-control", selection, "media", media, costs, 0, 1, control=True)
    frame(out / "media", selection, "media", media, costs, 0, 1)
    return root, out


def judge(instrument, result="success"):
    root, out = instrument
    return proof.verify_shards(out, HEAD, result, root=root)


def worker(out, index=0):
    return out / "shards" / f"van-backend-public-source-gateway-{index}"


def test_complete_synthetic_protocol_preserves_scope_and_issues_no_certificate(instrument):
    result = judge(instrument)
    assert result["tests"] == result["passed"] == 5
    assert len(result["gateway_shards"]) == 4 and result["certificates_issued"] == []
    assert len(result["separate_modules"]) == 3


@pytest.mark.parametrize("damage", ["missing-shard", "missing-artifact", "wrong-head", "wrong-tree",
    "wrong-run", "stale-execution", "parent-source-drift", "parent-environment-drift", "different-environment", "missing-environment", "selection-drop", "collection-omission",
    "collection-duplicate", "collection-foreign", "assignment-disagreement", "foreign-phase",
    "duplicate-phase", "setup-failure", "call-failure", "teardown-error", "aborted-call",
    "collection-only", "status-only", "nonterminal", "nonzero-exit", "collection-error",
    "unexpected-skip", "duplicate-junit", "foreign-junit", "junit-error", "source-storage",
    "artifact-hash", "missing-media", "control-executed", "null-audit", "wrong-auditor", "null-collection-errors", "boolean-exit",
    "missing-pytest-inputs", "plugin-code-drift", "noncanonical-config"])
def test_semantically_bad_receipts_fail_even_with_resealed_artifact_hashes(instrument, damage):
    _, out = instrument
    folder = worker(out)
    state = json.loads((folder / "terminal.json").read_text())
    events = [json.loads(x) for x in (folder / "phases.jsonl").read_text().splitlines()]
    receipt = json.loads((folder / "run.json").read_text())
    if damage == "missing-shard":
        (folder / "terminal.json").unlink()
    elif damage == "missing-artifact":
        (folder / "phases.jsonl").unlink()
    elif damage == "wrong-head": state["expected_commit"] = "d"*40
    elif damage == "wrong-tree": state["source_after"]["tree"] = "d"*40
    elif damage == "wrong-run": state["workflow_run"] = {"id": "old-run", "attempt": "1"}
    elif damage == "stale-execution": receipt["execution_id"] = "old-execution"
    elif damage == "parent-source-drift": receipt["source_after"]["tree"] = "wrong"
    elif damage == "parent-environment-drift": receipt["environment_after"]["packages"] = [["changed", "1"]]
    elif damage == "different-environment":
        state["environment_before"]["packages"] = state["environment_after"]["packages"] = [["different", "1"]]
        receipt["environment_before"]["packages"] = receipt["environment_after"]["packages"] = [["different", "1"]]
    elif damage == "missing-environment":
        del state["environment_before"]["packages"]
        del state["environment_after"]["packages"]
    elif damage == "selection-drop": state["selection"]["selected"].pop()
    elif damage == "collection-omission": state["full_collection"].pop()
    elif damage == "collection-duplicate": state["full_collection"].append(state["full_collection"][0])
    elif damage == "collection-foreign": state["full_collection"].append("outside/test_foreign.py::test_case")
    elif damage == "assignment-disagreement": state["assignment"][0], state["assignment"][1] = state["assignment"][1], state["assignment"][0]
    elif damage == "foreign-phase": events[0]["nodeid"] = "outside/test_foreign.py::test_case"
    elif damage == "duplicate-phase": events.append(copy.deepcopy(events[0]))
    elif damage in {"setup-failure", "call-failure", "teardown-error"}:
        when = {"setup-failure": "setup", "call-failure": "call", "teardown-error": "teardown"}[damage]
        next(x for x in events if x["when"] == when)["outcome"] = "failed"
    elif damage == "aborted-call": events = [x for x in events if x["when"] != "call"]
    elif damage == "collection-only": state["mode"] = "collection"
    elif damage == "status-only": events = []
    elif damage == "nonterminal": receipt["terminal"] = False
    elif damage == "nonzero-exit": receipt["exit"] = state["pytest_exit"] = 1
    elif damage == "collection-error": state["collection_errors"].append("failed import")
    elif damage == "unexpected-skip":
        event = next(x for x in events if x["when"] == "call")
        event.update(outcome="skipped", skip_reason="unapproved source skip")
    elif damage in {"duplicate-junit", "foreign-junit", "junit-error"}:
        xml = ET.parse(folder / "report.xml"); case = xml.getroot()[0]
        if damage == "duplicate-junit": xml.getroot().append(copy.deepcopy(case))
        elif damage == "foreign-junit": case.find("./properties/property").set("value", "outside/test_foreign.py::test_case")
        else: ET.SubElement(case, "error", message="late teardown failure")
        xml.write(folder / "report.xml")
    elif damage == "source-storage": write_json(folder / "storage-audit.json", {"forbidden_events": ["checkout-write"]})
    elif damage == "null-audit": write_json(folder / "storage-audit.json", {"forbidden_events": None})
    elif damage == "wrong-auditor":
        data=json.loads((folder/"storage-audit.json").read_text());data["source_sha256"]="wrong";write_json(folder/"storage-audit.json",data)
    elif damage == "null-collection-errors": state["collection_errors"]=None
    elif damage == "boolean-exit": receipt["exit"]=state["pytest_exit"]=False
    elif damage == "missing-pytest-inputs": state.pop("pytest_inputs")
    elif damage == "plugin-code-drift": state["pytest_inputs"]["plugins"]["pytest_asyncio.plugin"]="e"*64
    elif damage == "noncanonical-config": state["pytest_inputs"]["config_sha256"]="e"*64
    elif damage == "missing-media": (out / "media/report.xml").unlink()
    elif damage == "control-executed":
        (out / "gateway-control/phases.jsonl").write_text(json.dumps(events[0])+"\n")
        seal(out / "gateway-control")
    if damage not in {"missing-shard"}: write_json(folder / "terminal.json", state)
    if damage != "missing-artifact":
        (folder / "phases.jsonl").write_text("".join(json.dumps(x)+"\n" for x in events))
    write_json(folder / "run.json", receipt)
    seal(folder)
    if damage == "missing-media": seal(out / "media")
    if damage == "artifact-hash":
        (folder / "phases.jsonl").write_text("corrupted after receipt")
    with pytest.raises((ValueError, FileNotFoundError)):
        judge(instrument)


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_job_status_is_necessary_but_never_sufficient(instrument, result):
    with pytest.raises(ValueError): judge(instrument, result)


def test_exact_declared_skip_remains_disclosed_and_not_counted_as_pass(instrument):
    _, out = instrument
    node = "backend/tests/test_jev_no_generic_executor.py::test_no_fabric_or_generic_operation_survives_the_b1_validator[fixture]"
    folder = next(worker(out, i) for i in range(4) if node in json.loads((worker(out, i)/"terminal.json").read_text())["assigned"])
    events = [json.loads(x) for x in (folder/"phases.jsonl").read_text().splitlines()]
    next(x for x in events if x["when"] == "call").update(outcome="skipped", skip_reason="member of the B1 closed set by definition")
    (folder/"phases.jsonl").write_text("".join(json.dumps(x)+"\n" for x in events))
    xml = ET.parse(folder/"report.xml")
    ET.SubElement(xml.getroot()[0], "skipped", message="member of the B1 closed set by definition")
    xml.write(folder/"report.xml"); seal(folder)
    result = judge(instrument)
    assert result["tests"] == 5 and result["passed"] == 4
    assert result["declared_unexecuted"] == [{"id": node, "reason": "member of the B1 closed set by definition"}]


def test_historical_weights_cannot_remove_cases_and_require_matching_source_hash():
    selected = [{"path": f"test_{i}.py", "sha256": str(i)} for i in range(8)]
    nodes = [r["path"]+"::test_case" for r in selected]
    costs = {"costs": {"test_0.py": {"seconds": 1000, "test_source_sha256": "0"},
                       "test_1.py": {"seconds": 9999, "test_source_sha256": "wrong"}}}
    bins = proof.assignment(nodes, selected, costs, 4)
    assert sorted(n for b in bins for n in b) == sorted(nodes)
    assert bins[0] == ["test_0.py::test_case"]
    assert proof.assignment(list(reversed(nodes)), selected, costs, 4) == bins


def test_actual_pytest_plugin_records_full_collection_disjoint_execution_and_teardown_error(tmp_path):
    """Tiny real subprocesses test the instrument, not native four-worker qualification."""
    import os
    import shutil
    import subprocess
    import sys
    repo = tmp_path / "synthetic-instrument-project"
    repo.mkdir()
    source_root = Path(__file__).resolve().parents[2]
    for rel in ("tools/rebuild/backend_public_source.py", "tools/rebuild/public_source_shards.py",
                "tools/rebuild/source_storage_audit.py", "tools/rebuild/backend_public_source_costs.json"):
        p = repo/rel;p.parent.mkdir(parents=True, exist_ok=True);shutil.copyfile(source_root/rel,p)
    for rel in gate.PRIVATE | {gate.FIREWALL}:
        p=repo/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text("# separate synthetic fixture\n")
    for index in range(4):
        p=repo/f"backend/tests/test_fixture_{index}.py";p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text("import pytest\n@pytest.fixture\ndef resource():\n    yield\n"+
                     ("    raise AssertionError('synthetic teardown counterexample')\n" if index==0 else "")+
                     f"def test_fixture_{index}(resource, committed_marker):\n    assert committed_marker == 'tracked fixture'\n")
    (repo/"backend/tests/conftest.py").write_text("import pytest\n@pytest.fixture\ndef committed_marker():\n    return 'tracked fixture'\n")
    media_source=repo/"services/source/test_media.py"
    media_source.parent.mkdir(parents=True,exist_ok=True)
    media_source.write_text("def test_media_fixture():\n    assert True\n")
    (repo/"pytest.ini").write_text("[pytest]\n")
    subprocess.run(["git","init","-q"],cwd=repo,check=True)
    subprocess.run(["git","add","."],cwd=repo,check=True)
    subprocess.run(["git","-c","user.name=Source instrument fixture","-c","user.email=source@example.test",
                    "commit","-qm","Synthetic verification instrument inputs"],cwd=repo,check=True)
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
    env={**os.environ,"PYTHONPATH":os.pathsep.join(str(repo/p) for p in proof.CANONICAL_PYTHONPATH),"PYTHONDONTWRITEBYTECODE":"1",
         "GITHUB_RUN_ID":"synthetic-instrument-subprocess","GITHUB_RUN_ATTEMPT":"1"}
    env.pop("VATI_TEST_PG_DSN",None);env.pop("VATI_TEST_PG_ISOLATED_FIXTURE",None)
    media_python=isolated_media_pytest(tmp_path)
    evidence=tmp_path/"full-cli-evidence"
    subprocess.run([sys.executable,"tools/rebuild/backend_public_source.py","plan","--output",str(evidence)],
                   cwd=repo,env=env,check=True,capture_output=True,text=True)
    for runtime, count in (("gateway",4),("media",1)):
        control=evidence/(runtime+"-control")
        result=subprocess.run([media_python if runtime=="media" else sys.executable,"tools/rebuild/backend_public_source.py","collect","--output",str(control),
            "--runtime",runtime,"--shards",str(count),"--expected-commit",commit,
            "--basetemp",str(tmp_path/(runtime+"-control-temp"))],cwd=repo,env=env,capture_output=True,text=True,timeout=90)
        assert result.returncode==0, result.stdout+result.stderr
        state=json.loads((control/"terminal.json").read_text())
        assert state["mode"]=="collection" and not (control/"phases.jsonl").read_text()
        assert len(state["full_collection"])==(4 if runtime=="gateway" else 1)
    media=evidence/"media"
    result=subprocess.run([media_python,"tools/rebuild/backend_public_source.py","run-shard","--output",str(media),
        "--runtime","media","--shards","1","--expected-commit",commit,
        "--basetemp",str(tmp_path/"media-temp")],cwd=repo,env=env,capture_output=True,text=True,timeout=90)
    assert result.returncode==0, result.stdout+result.stderr
    media_state=json.loads((media/"terminal.json").read_text())
    assert media_state["runtime"]=="media" and len(media_state["assigned"])==1
    all_assigned=[];outcomes=[]
    for index in range(4):
        out=evidence/"shards"/f"van-backend-public-source-gateway-{index}"
        cmd=[sys.executable,"tools/rebuild/backend_public_source.py","run-shard","--output",str(out),
             "--runtime","gateway","--shards","4","--shard-index",str(index),"--expected-commit",commit,
             "--basetemp",str(tmp_path/f"worker-temp-{index}")]
        result=subprocess.run(cmd,cwd=repo,env=env,capture_output=True,text=True,timeout=90)
        receipt=json.loads((out/"run.json").read_text());state=json.loads((out/"terminal.json").read_text())
        assert receipt["exit"]==result.returncode and receipt["terminal"] is True
        assert state["source_before"]==state["source_after"] and state["expected_commit"]==commit
        assert len(state["full_collection"])==4 and len(state["assigned"])==1
        assert "backend/tests/conftest.py" in state["pytest_inputs"]["plugins"]
        events=[json.loads(x) for x in (out/"phases.jsonl").read_text().splitlines()]
        assert {x["when"] for x in events}=={"setup","call","teardown"}
        cases=list(ET.parse(out/"report.xml").getroot().iter("testcase"));assert len(cases)==1
        assert cases[0].find("./properties/property[@name='van_source_nodeid']").get("value")==state["assigned"][0]
        all_assigned.extend(state["assigned"]);outcomes.append((result.returncode,events))
    result=subprocess.run([sys.executable,"tools/rebuild/backend_public_source.py","verify-shards","--output",str(evidence),
        "--expected-commit",commit,"--job-result","success"],cwd=repo,env=env,capture_output=True,text=True,timeout=90)
    assert result.returncode!=0  # A real failed teardown cannot become a status-only success.
    assert not (evidence/"summary.json").exists()
    for key,value in (("PYTEST_ADDOPTS","-k fixture_0"),("PYTEST_PLUGINS","unsupported_plugin")):
        rejected=tmp_path/("rejected-"+key)
        attempt=subprocess.run([sys.executable,"tools/rebuild/backend_public_source.py","collect","--output",str(rejected),
            "--runtime","gateway","--shards","4","--expected-commit",commit,"--basetemp",str(tmp_path/(key+"-temp"))],
            cwd=repo,env={**env,key:value},capture_output=True,text=True,timeout=90)
        assert attempt.returncode!=0 and not (rejected/"terminal.json").exists()
    original=evidence/"shards/van-backend-public-source-gateway-0/terminal.json"
    original_bytes=original.read_bytes()
    retry=subprocess.run([sys.executable,"tools/rebuild/backend_public_source.py","run-shard","--output",str(original.parent),
        "--runtime","gateway","--shards","4","--expected-commit",commit,"--basetemp",str(tmp_path/"reused-temp")],
        cwd=repo,env=env,capture_output=True,text=True,timeout=90)
    assert retry.returncode!=0 and original.read_bytes()==original_bytes
    cache_only=tmp_path/"retained-cache-evidence";cache_only.mkdir()
    saved=cache_only/"generated-bytecode.json";saved.write_text('{"original":"retained output"}\n')
    retry=subprocess.run([sys.executable,"tools/rebuild/backend_public_source.py","collect","--output",str(cache_only),
        "--runtime","gateway","--shards","4","--expected-commit",commit,"--basetemp",str(tmp_path/"cache-reuse-temp")],
        cwd=repo,env=env,capture_output=True,text=True,timeout=90)
    assert retry.returncode!=0 and "fresh evidence folder" in retry.stderr
    assert saved.read_text()=='{"original":"retained output"}\n' and not (cache_only/"terminal.json").exists()
    assert len(set(all_assigned))==4
    assert sum(code==0 for code,_ in outcomes)==3
    assert sum(any(e["when"]=="teardown" and e["outcome"]=="failed" for e in events) for _,events in outcomes)==1


def test_actual_collect_refuses_untracked_and_ignored_inputs_but_accepts_inert_outputs(tmp_path):
    """Regression for CI4-REVIEW-01: agreeing reduced inventories cannot bind HEAD."""
    import os
    import shutil
    import subprocess
    import sys
    repo = tmp_path/"source-provenance-fixture"
    repo.mkdir()
    source = Path(__file__).resolve().parents[2]
    for rel in ("tools/rebuild/backend_public_source.py", "tools/rebuild/public_source_shards.py",
                "tools/rebuild/source_storage_audit.py", "tools/rebuild/backend_public_source_costs.json"):
        path=repo/rel;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/rel,path)
    for rel in gate.PRIVATE | {gate.FIREWALL}:
        path=repo/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text("# separate fixture\n")
    for index in range(4):
        path=repo/f"backend/tests/test_fixture_{index}.py";path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text("import json\nfrom pathlib import Path\nimport pytest\n"
            "data=Path(__file__).resolve().parents[2]/'parameters.json'\n"
            "values=json.loads(data.read_text()) if data.exists() else [1,2]\n"
            "@pytest.mark.parametrize('value',values)\ndef test_case(value):\n    assert value > 0\n")
    (repo/"pytest.ini").write_text("[pytest]\n")
    (repo/".gitignore").write_text("backend/tests/conftest.py\n*.ini\n*.json\n__pycache__/\n.pytest_cache/\n*.pth\n*.pyc\n")
    subprocess.run(["git","init","-q"],cwd=repo,check=True)
    subprocess.run(["git","add","."],cwd=repo,check=True)
    subprocess.run(["git","add","-f","pytest.ini","tools/rebuild/backend_public_source_costs.json"],cwd=repo,check=True)
    subprocess.run(["git","-c","user.name=Source instrument fixture","-c","user.email=source@example.test",
                    "commit","-qm","Committed eight-case source provenance fixture"],cwd=repo,check=True)
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
    env={**os.environ,"PYTHONPATH":os.pathsep.join(str(repo/p) for p in proof.CANONICAL_PYTHONPATH),"PYTHONDONTWRITEBYTECODE":"1",
         "GITHUB_RUN_ID":"synthetic-provenance-subprocess","GITHUB_RUN_ATTEMPT":"1"}
    env.pop("VATI_TEST_PG_DSN",None);env.pop("VATI_TEST_PG_ISOLATED_FIXTURE",None)
    def collect(label, extra_env=None):
        output=tmp_path/("evidence-"+label)
        result=subprocess.run([sys.executable,"-B","-s","tools/rebuild/backend_public_source.py","collect",
            "--output",str(output),"--runtime","gateway","--shards","4","--expected-commit",commit,
            "--basetemp",str(tmp_path/("temp-"+label))],cwd=repo,env={**env,**(extra_env or {})},
            capture_output=True,text=True,timeout=90)
        return result,output
    # An ancestor collector must not run; committed root config/confcutdir owns scope.
    (tmp_path/"conftest.py").write_text("raise AssertionError('foreign ancestor collector loaded')\n")
    baseline,output=collect("clean")
    assert baseline.returncode==0, baseline.stdout+baseline.stderr
    assert len(json.loads((output/"terminal.json").read_text())["full_collection"])==8
    generated=(repo/"artifacts/backend-public-source/gateway-control/terminal.json")
    generated.parent.mkdir(parents=True);generated.write_text('{"synthetic_inert_output":true}\n')
    cache=repo/".pytest_cache/v/cache/nodeids";cache.parent.mkdir(parents=True,exist_ok=True);cache.write_text("[]\n")
    positive,output=collect("generated")
    assert positive.returncode==0,positive.stdout+positive.stderr
    assert len(json.loads((output/"terminal.json").read_text())["full_collection"])==8
    dropping="def pytest_collection_modifyitems(items):\n    items[:] = [i for i in items if not i.nodeid.endswith('[2]')]\n"
    for index,(rel,content) in enumerate((
        ("conftest.py",dropping),  # ordinary untracked collector: the original actual omission
        ("backend/tests/conftest.py",dropping),
        ("untracked_plugin.py",dropping),
        ("backend/pytest.ini","[pytest]\naddopts = -k test_first\n"),
        (".pytest_cache/conftest.py",dropping),
        ("__pycache__/unowned.pyc","synthetic bytecode input"),
        ("injected.pth","import untracked_plugin\n"),
        ("artifacts/backend-public-source/conftest.py",dropping),
        ("parameters.json","[1]"),  # ignored data would shrink every tracked parametrization
    )):
        path=repo/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
        rejected,folder=collect("injected-"+str(index))
        assert rejected.returncode!=0 and "uncommitted executable/config/fixture inputs" in rejected.stderr
        assert not (folder/"terminal.json").exists() and path.read_text()==content
        path.unlink()  # Only this explicitly owned synthetic injection is removed.
    rejected,folder=collect("foreign-pythonpath",{"PYTHONPATH":str(repo)+os.pathsep+str(tmp_path)})
    assert rejected.returncode!=0 and "foreign PYTHONPATH" in rejected.stderr and not (folder/"terminal.json").exists()
    # The extra-file policy refuses rather than modifying any original input/output.
    assert generated.read_text()=='{"synthetic_inert_output":true}\n' and cache.read_text()=="[]\n"


def test_reporter_preserves_all_phases_without_changing_application_json_patch(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(proof,"_STATE",{"output":str(tmp_path)})
    def report(when):
        return SimpleNamespace(nodeid="synthetic::original_json_refusal",when=when,
                               outcome="passed",duration=0.125,skipped=False)
    proof.pytest_runtest_logreport(report("setup"))
    def too_deep(*args,**kwargs):
        raise RecursionError("nested JSON")
    with monkeypatch.context() as patch:
        patch.setattr(json,"dumps",too_deep)
        with pytest.raises(RecursionError,match="nested JSON"):
            json.dumps({"application":"still patched"})
        proof.pytest_runtest_logreport(report("call"))
        assert json.dumps is too_deep
    proof.pytest_runtest_logreport(report("teardown"))
    events=[json.loads(line) for line in (tmp_path/"phases.jsonl").read_text().splitlines()]
    assert [(e["when"],e["outcome"]) for e in events]==[(p,"passed") for p in ("setup","call","teardown")]
    assert all(e["nodeid"]=="synthetic::original_json_refusal" for e in events)


@pytest.mark.parametrize("failure",["encode","write"])
def test_real_report_encoding_and_storage_errors_propagate_without_fake_events(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    path=tmp_path/"phases.jsonl";path.write_text('{"earlier":"actual event"}\n');before=path.read_bytes()
    monkeypatch.setattr(proof,"_STATE",{"output":str(tmp_path)})
    report=SimpleNamespace(nodeid="synthetic::recording_failure",when="call",outcome="passed",duration=0.1,skipped=False)
    with monkeypatch.context() as patch:
        if failure=="encode":
            def fail(*args,**kwargs):raise TypeError("real report encoding failure")
            patch.setattr(proof,"_JSON_DUMPS",fail)
            expected=TypeError
        else:
            class FailedWrite:
                def __enter__(self):return self
                def __exit__(self,*args):return False
                def write(self,value):raise OSError("real report storage failure")
            original=Path.open
            def open_path(self,*args,**kwargs):
                return FailedWrite() if self==path else original(self,*args,**kwargs)
            patch.setattr(Path,"open",open_path)
            expected=OSError
        with pytest.raises(expected,match="real report"):
            proof.pytest_runtest_logreport(report)
    assert path.read_bytes()==before


NATIVE_CACHE_SOURCES = (
    "backend/van_gateway/__init__.py", "backend/van_gateway/config.py",
    "backend/van_gateway/auth/__init__.py", "backend/van_gateway/auth/control_scopes.py",
    "backend/van_gateway/learning/__init__.py", "backend/van_gateway/learning/schema.py",
    "backend/van_gateway/private_core/__init__.py", "backend/van_gateway/private_core/app.py",
    "backend/van_gateway/storage/__init__.py", "backend/van_gateway/storage/chart_migration.py",
    "tools/runtime/preflight_owner_core.py",
)


@pytest.fixture
def real_cache_source(tmp_path):
    import shutil
    import subprocess
    repo=tmp_path/"exact-tracked-cache-source";repo.mkdir()
    root=Path(__file__).resolve().parents[2]
    for relative in NATIVE_CACHE_SOURCES:
        target=repo/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/relative,target)
    # This constant explicitly exercises legitimate frozenset marshal ordering across hash seeds.
    (repo/"seeded.py").write_text("def member(value):\n    return value in {"+','.join(repr('name-'+str(i)) for i in range(70))+"}\n")
    (repo/"pytest.ini").write_text("[pytest]\n")
    (repo/".gitignore").write_text("__pycache__/\n")
    subprocess.run(["git","init","-q"],cwd=repo,check=True);subprocess.run(["git","add","."],cwd=repo,check=True)
    subprocess.run(["git","-c","user.name=Generated cache source fixture","-c","user.email=source@example.test",
                    "commit","-qm","Exact native failure module bytes plus explicit hash-seed fixture"],cwd=repo,check=True)
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
    return repo,head


def compile_real_cache_sources(repo, seed="17", optimization=0, invalidation="TIMESTAMP"):
    import os,subprocess,sys
    paths=[str(repo/p) for p in (*NATIVE_CACHE_SOURCES,"seeded.py")]
    command=("import py_compile,sys;[py_compile.compile(p,doraise=True,optimize="+str(optimization)
             +",invalidation_mode=py_compile.PycInvalidationMode."+invalidation+") for p in sys.argv[1:]]")
    subprocess.run([sys.executable,"-c",command,*paths],
                   env={**os.environ,"PYTHONHASHSEED":seed},check=True,capture_output=True,text=True)


def test_parent_validates_actual_native_module_caches_and_retires_only_verified_outputs(real_cache_source,tmp_path):
    import base64
    repo,head=real_cache_source;before=proof.source_identity(repo,head)
    compile_real_cache_sources(repo)
    # Valid committed-source caches still cannot be admitted as pre-run inputs.
    with pytest.raises(ValueError,match="uncommitted executable"):
        proof.source_identity(repo,head)
    out=tmp_path/"inert-cache-archive";out.mkdir()
    outputs=proof.archive_generated_bytecode(repo,head,before,out)
    artifact=json.loads((out/"generated-bytecode.json").read_text())
    assert len(outputs)==len(NATIVE_CACHE_SOURCES)+1 and artifact["input_bytecode_paths"]==[]
    assert {r["source"] for r in artifact["records"]}==set(NATIVE_CACHE_SOURCES)|{"seeded.py"}
    assert proof.source_identity(repo,head)==before and not list(repo.rglob("*.pyc"))
    state={"root":str(repo),"generated_cache_candidates":outputs};receipt={"generated_cache_outputs":outputs}
    proof.verify_generated_bytecode(out,repo,head,state,receipt)
    first={r["source"]:r["code_identity_sha256"] for r in artifact["records"]}
    compile_real_cache_sources(repo,seed="93")
    second=tmp_path/"another-compiler-seed";second.mkdir()
    proof.archive_generated_bytecode(repo,head,before,second)
    assert {r["source"]:r["code_identity_sha256"] for r in json.loads((second/"generated-bytecode.json").read_text())["records"]}==first
    # A valid header cannot authorize changed code; verify archived bytes independently too.
    record=artifact["records"][-1];data=base64.b64decode(record["payload_base64"])
    import marshal
    forged=data[:16]+marshal.dumps(compile("raise RuntimeError('forged payload must never execute')",record["code_filename"],"exec"))
    record["payload_base64"]=base64.b64encode(forged).decode()
    write_json(out/"generated-bytecode.json",artifact)
    with pytest.raises(ValueError,match="payload differs"):
        proof.verify_generated_bytecode(out,repo,head,state,receipt)


@pytest.mark.parametrize("invalidation,optimization",[("CHECKED_HASH",1),("UNCHECKED_HASH",2)])
def test_exact_native_sources_hash_header_and_optimization_match(real_cache_source,tmp_path,invalidation,optimization):
    repo,head=real_cache_source;before=proof.source_identity(repo,head)
    compile_real_cache_sources(repo,optimization=optimization,invalidation=invalidation)
    output=tmp_path/"verified-other-header";output.mkdir()
    paths=proof.archive_generated_bytecode(repo,head,before,output)
    state={"root":str(repo),"generated_cache_candidates":paths};receipt={"generated_cache_outputs":paths}
    proof.verify_generated_bytecode(output,repo,head,state,receipt)
    artifact=json.loads((output/"generated-bytecode.json").read_text())
    assert all(r["optimization"]==optimization and r["flags"]==(3 if invalidation=="CHECKED_HASH" else 1) for r in artifact["records"])


@pytest.mark.parametrize("damage",["preexisting","untracked-source","wrong-magic","wrong-flags","wrong-timestamp",
                                  "forged-payload","wrong-interpreter","source-drift"])
def test_generated_cache_provenance_refuses_bad_input_without_deleting_it(real_cache_source,tmp_path,damage):
    import importlib.util,marshal,py_compile
    repo,head=real_cache_source;before=proof.source_identity(repo,head)
    compile_real_cache_sources(repo)
    path=Path(importlib.util.cache_from_source(str(repo/"seeded.py")))
    data=path.read_bytes()
    if damage=="preexisting":
        with pytest.raises(ValueError,match="uncommitted executable"):
            proof.source_identity(repo,head)
        assert path.read_bytes()==data
        return
    if damage=="untracked-source":
        foreign=repo/"foreign.py";foreign.write_text("payload='untracked'\n")
        py_compile.compile(str(foreign),doraise=True)
        foreign.unlink()  # The orphan cache still cannot claim any tracked source owner.
    elif damage=="wrong-magic":data=b"BAD!"+data[4:]
    elif damage=="wrong-flags":data=data[:4]+(7).to_bytes(4,"little")+data[8:]
    elif damage=="wrong-timestamp":data=data[:8]+((int.from_bytes(data[8:12],"little")+1)%2**32).to_bytes(4,"little")+data[12:]
    elif damage=="forged-payload":data=data[:16]+marshal.dumps(compile("value='different code'",str(repo/"seeded.py"),"exec"))
    elif damage=="wrong-interpreter":
        renamed=path.with_name(path.name.replace("cpython-312","cpython-999"));path.rename(renamed);path=renamed
    elif damage=="source-drift":(repo/"seeded.py").write_text("different='tracked source changed'\n")
    path.write_bytes(data)
    output=tmp_path/"refused-output";output.mkdir()
    with pytest.raises(ValueError):proof.archive_generated_bytecode(repo,head,before,output)
    assert path.read_bytes()==data and not (output/"generated-bytecode.json").exists()


def test_default_environment_verify_cli_creates_no_bytecode_and_refuses_foreign_input(tmp_path,monkeypatch):
    """Real CLI conformance with synthetic receipts, not application/native execution."""
    import os,shutil,subprocess,sys
    repo=tmp_path/"clean-default-verifier";repo.mkdir()
    source=Path(__file__).resolve().parents[2]
    for rel in ("tools/rebuild/backend_public_source.py","tools/rebuild/public_source_shards.py",
                "tools/rebuild/source_storage_audit.py"):
        path=repo/rel;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/rel,path)
    for rel in (*gate.PRIVATE,gate.FIREWALL,*(f"backend/tests/test_cli_{i}.py" for i in range(4)),"services/source/test_media.py"):
        path=repo/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text("def test_case():\n    assert True\n")
    (repo/"pytest.ini").write_text("[pytest]\n");(repo/".gitignore").write_text("__pycache__/\n")
    costs={"costs":{}};write_json(repo/"tools/rebuild/backend_public_source_costs.json",costs)
    subprocess.run(["git","init","-q"],cwd=repo,check=True);subprocess.run(["git","add","."],cwd=repo,check=True)
    subprocess.run(["git","-c","user.name=Default verifier fixture","-c","user.email=source@example.test",
                    "commit","-qm","Synthetic protocol and exact production verifier files"],cwd=repo,check=True)
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
    monkeypatch.setitem(globals(),"HEAD",head)
    original_source=proof.source_identity(repo,head)
    selection=gate.plan(repo);gateway=[r["path"]+"::test_case" for r in selection["selected"] if gate.runtime(r["path"])=="gateway"]
    media=["services/source/test_media.py::test_case"];out=tmp_path/"complete-synthetic-protocol";out.mkdir()
    write_json(out/"selection.json",selection)
    frames=[(out/"gateway-control","gateway",gateway,0,4,True),
            *((out/"shards"/f"van-backend-public-source-gateway-{i}","gateway",gateway,i,4,False) for i in range(4)),
            (out/"media-control","media",media,0,1,True),(out/"media","media",media,0,1,False)]
    for folder,runtime,nodes,index,count,control in frames:
        frame(folder,selection,runtime,nodes,costs,index,count,control=control,root=repo)
        state=json.loads((folder/"terminal.json").read_text());receipt=json.loads((folder/"run.json").read_text())
        state.update(source_before=original_source,source_after=original_source,root=str(repo))
        receipt.update(source_before=original_source,source_after=original_source)
        write_json(folder/"terminal.json",state);write_json(folder/"run.json",receipt);seal(folder)
    env={**os.environ,"PYTHONPATH":os.pathsep.join(str(repo/p) for p in proof.CANONICAL_PYTHONPATH),
         "GITHUB_RUN_ID":CONTEXT["id"],"GITHUB_RUN_ATTEMPT":CONTEXT["attempt"]}
    env.pop("PYTHONDONTWRITEBYTECODE",None)  # Match the production aggregate's default environment.
    command=[sys.executable,"tools/rebuild/backend_public_source.py","verify-shards","--output",str(out),
             "--expected-commit",head,"--job-result","success"]
    result=subprocess.run(command,cwd=repo,env=env,capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads((out/"summary.json").read_text())["tests"]==5
    assert not list(repo.rglob("*.pyc")) and proof.source_identity(repo,head)==original_source
    foreign=repo/"foreign/__pycache__/untrusted.cpython-312.pyc";foreign.parent.mkdir(parents=True);foreign.write_bytes(b"foreign bytecode input")
    refused=subprocess.run(command,cwd=repo,env=env,capture_output=True,text=True,timeout=90)
    assert refused.returncode!=0 and "uncommitted executable/config/fixture inputs" in refused.stderr
    assert foreign.read_bytes()==b"foreign bytecode input"
