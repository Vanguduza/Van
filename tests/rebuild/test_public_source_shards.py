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
    names = ["terminal.json", "phases.jsonl", "storage-audit.json"]
    if receipt["mode"] == "execution":
        names.append("report.xml")
    receipt["artifact_sha256"] = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                                   for name in names if (folder / name).exists()}
    write_json(folder / "run.json", receipt)


def frame(folder, selection, runtime, nodeids, costs, index, count, *, control=False):
    folder.mkdir(parents=True)
    bins = proof.assignment(nodeids, [r for r in selection["selected"] if gate.runtime(r["path"]) == runtime], costs, count)
    environment = {"python": "3.12.12", "implementation": "CPython", "system": "Linux", "machine": "x86_64",
        "image_os": "ubuntu24", "image_version": "synthetic-instrument-image", "packages": [["synthetic", "0"]],
        "node": "v24.19.0", "chromium_sha256": "c"*64,
        "pytest_entrypoints": sorted(proof.EXPLICIT_PLUGINS[runtime]),
        "pythonpath": list(proof.CANONICAL_PYTHONPATH),
        "postgres_version": 170011 if runtime == "gateway" else None,
        "isolated_pg_fixture": "1" if runtime == "gateway" else None}
    state = {"schema": proof.SCHEMA, "mode": "collection" if control else "execution", "runtime": runtime,
        "expected_commit": HEAD, "execution_id": "synthetic-"+folder.name, "workflow_run": CONTEXT, "source_before": {"commit": HEAD, "tree": "b"*40},
        "source_after": {"commit": HEAD, "tree": "b"*40}, "environment_before": environment,
        "pytest_inputs": {"config_sha256": hashlib.sha256(b"[pytest]\n").hexdigest(),
            "plugins": {p:"d"*64 for p in proof.EXPLICIT_PLUGINS[runtime]}, "autoload": False},
        "environment_after": copy.deepcopy(environment), "selection": selection,
        "selected": [r for r in selection["selected"] if gate.runtime(r["path"]) == runtime],
        "collection_errors": [], "internal_errors": [], "pytest_exit": 0,
        "instrument_sha256": hashlib.sha256(Path(proof.__file__).read_bytes()).hexdigest(), "costs": costs,
        "full_collection": sorted(nodeids), "assignment": bins, "assigned": bins[index],
        "shard_index": index, "shard_count": count, "full_collection_sha256": proof.fingerprint(sorted(nodeids)),
        "assignment_sha256": proof.fingerprint(bins)}
    write_json(folder / "terminal.json", state)
    write_json(folder / "storage-audit.json", {"schema": "van.source-storage-audit/1", "forbidden_events": [],
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
    write_json(folder / "run.json", {"expected_commit": HEAD, "workflow_run": CONTEXT,
        "terminal": True, "exit": 0, "mode": state["mode"], "execution_id": state["execution_id"],
        "source_before": state["source_before"], "source_after": state["source_after"],
        "environment_before": copy.deepcopy(environment), "environment_after": copy.deepcopy(environment)})
    seal(folder)


@pytest.fixture
def instrument(tmp_path, monkeypatch):
    root = tmp_path / "synthetic-source"
    root.mkdir()
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
