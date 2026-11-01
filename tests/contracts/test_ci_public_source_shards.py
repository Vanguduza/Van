"""Public source sharding preserves the original required gate and other CI jobs."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = "fd33b0759b9ae170f8bdfdf27f9afe7082da7830"

# Explicit additive OBL004 audit jobs; every original job and global boundary remains below.
OBL004_JOBS = {'obl004-backend-gateway', 'obl004-browser-namespace', 'obl004-forecast-source', 'obl004-documentary', 'obl004-canonical-matrix', 'obl004-trading-pg', 'obl004-private-dds', 'obl004-backend-public-source', 'obl004-scenarios'}


def workflows():
    old = subprocess.check_output(["git", "show", BASE+":.github/workflows/van-ci.yml"], cwd=ROOT)
    return yaml.safe_load(old), yaml.safe_load((ROOT/".github/workflows/van-ci.yml").read_text())


def test_every_other_job_trigger_and_concurrency_boundary_is_unchanged():
    before, after = workflows()
    assert {k:v for k,v in before.items() if k != "jobs"} == {k:v for k,v in after.items() if k != "jobs"}
    assert set(after["jobs"]) == set(before["jobs"]) | {"backend-public-source-gateway"} | OBL004_JOBS
    for name, job in before["jobs"].items():
        if name != "backend-public-source": assert after["jobs"][name] == job, name


def test_original_required_gate_is_an_always_running_fail_closed_aggregate():
    _, after = workflows()
    gate = after["jobs"]["backend-public-source"]
    assert gate["name"] == "backend-public-source"
    assert gate["needs"] == ["backend-public-source-gateway"] and gate["if"] == "always()"
    verify = next(s for s in gate["steps"] if "verify-shards" in s.get("run", ""))
    assert verify["if"] == "always()"
    assert '--job-result "${{ needs.backend-public-source-gateway.result }}"' in verify["run"]
    assert '--expected-commit "${{ github.event.pull_request.head.sha || github.sha }}"' in verify["run"]
    assert not gate.get("continue-on-error", False)


def test_four_workers_are_fresh_native_fixtures_with_the_original_dependencies():
    before, after = workflows()
    old = before["jobs"]["backend-public-source"]
    worker = after["jobs"]["backend-public-source-gateway"]
    assert worker["strategy"] == {"fail-fast": False, "max-parallel": 4, "matrix": {"shard": [0,1,2,3]}}
    assert not worker.get("continue-on-error", False)
    for job in (worker, after["jobs"]["backend-public-source"]):
        for key in ("runs-on", "services", "env", "timeout-minutes"): assert job[key] == old[key], key
        assert job["steps"][:5] == old["steps"][:5]
    command = next(s["run"] for s in worker["steps"] if "run-shard" in s.get("run", ""))
    assert "--shards 4 --shard-index ${{ matrix.shard }}" in command
    assert '--expected-commit "${{ github.event.pull_request.head.sha || github.sha }}"' in command
    assert 'runner.temp }}/van-public-gateway-${{ matrix.shard }}' in command
    assert "pytest-xdist" not in command and " -n " not in command


def test_independent_full_collection_and_separate_hashed_media_runtime_remain():
    _, after = workflows()
    steps = after["jobs"]["backend-public-source"]["steps"]
    control = next(s for s in steps if "--runtime gateway --shards 4" in s.get("run", ""))
    assert control["if"] == "always()" and " collect " in " ".join(control["run"].split())
    media = next(s for s in steps if 'python -m venv "$RUNNER_TEMP/public-media-venv"' in s.get("run", ""))
    assert media["if"] == "always()"
    assert "--require-hashes -r deploy/van-browser-stream/requirements.lock" in media["run"]
    assert "--runtime media --shards 1" in media["run"]
    assert "media-control" in media["run"] and "run-shard" in media["run"]


def test_all_shard_evidence_and_original_named_aggregate_artifact_are_uploaded():
    _, after = workflows()
    worker = after["jobs"]["backend-public-source-gateway"]
    upload = next(s for s in worker["steps"] if s.get("uses") == "actions/upload-artifact@v4")
    assert upload["if"] == "always()" and upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["name"] == "van-backend-public-source-gateway-${{ matrix.shard }}"
    aggregate = after["jobs"]["backend-public-source"]
    download = next(s for s in aggregate["steps"] if s.get("uses") == "actions/download-artifact@v4")
    assert download["if"] == "always()" and download["with"]["merge-multiple"] is False
    final = next(s for s in aggregate["steps"] if s.get("uses") == "actions/upload-artifact@v4")
    assert final["if"] == "always()" and final["with"]["name"] == "van-backend-public-source"


def test_workflow_installer_mirror_and_frozen_mutation_source_remain_exact():
    assert (ROOT/".github/workflows/van-ci.yml").read_bytes() == (ROOT/"tools/ci/github-actions-ci.yml").read_bytes()
    previous = subprocess.check_output(["git", "show", BASE+":tools/audit/mutation_suite.py"], cwd=ROOT)
    # The independently reviewed LAC234 packet admitted exactly five retained edits.
    # Preserve the original frozen core, rather than rebasing the guard to arbitrary
    # current bytes or treating an authorized retarget as permission to alter a case.
    assert hashlib.sha256(previous).hexdigest() == "cbf114a3374538eeb1403d3f066ee4f22d2405b32e6a7f6b752fa9fe0d9a99df"
    current = (ROOT/"tools/audit/mutation_suite.py").read_bytes()
    assert hashlib.sha256(current).hexdigest() == "789f46dfefa7b022d869751e1548ca95a74177d6b51c4699f8d2692cdcc8c450"
    provenance = ROOT/"docs/rebuild/rev118/receipts/raw/queue-restoration-20261101/CATALOG_RECONCILIATION.json"
    assert hashlib.sha256(provenance.read_bytes()).hexdigest() == "290d5cd494d411ea03d7214f76d066fc08a9b542731016b1b9ed39dafcaf4d13"
    reviewed = json.loads(provenance.read_bytes())
    assert reviewed["identities_before_after"] == 374
    assert reviewed["edits_before_after"] == 383
    assert reviewed["case_order_ids_targets_test_selection_unchanged"] is True
    changes = {case["id"]: case for case in reviewed["exact_five_changes"]}
    assert len(changes) == 5
    restored = ast.parse(current)
    found = set()
    for node in ast.walk(restored):
        if not (isinstance(node, ast.Tuple) and len(node.elts) == 4
                and isinstance(node.elts[-1], ast.Constant) and node.elts[-1].value in changes):
            continue
        identity = node.elts[-1].value
        assert identity not in found
        found.add(identity)
        case = changes[identity]
        original, retarget = case["original"], case["retargeted"]
        assert original["id"] == retarget["id"] == identity
        assert original["tests"] == retarget["tests"]
        assert len(original["edits"]) == len(retarget["edits"]) == 1
        old, new = original["edits"][0], retarget["edits"][0]
        assert old[0] == new[0]
        assert ast.literal_eval(node.elts[1]) == new[1]
        assert ast.literal_eval(node.elts[2]) == new[2]
        node.elts[1], node.elts[2] = ast.Constant(old[1]), ast.Constant(old[2])
    assert found == set(changes)
    # Restoring only those ten string values must recover the entire original AST:
    # every case ID, order, target, selection, other edit and execution helper remains.
    assert ast.dump(restored) == ast.dump(ast.parse(previous))
    admitted = "629a986019a4eb298f58dd98c62e6bcbade36ab7"
    assert subprocess.check_output(["git", "show", admitted+":tools/audit/mutation_suite.py"], cwd=ROOT) == current
    rows = subprocess.check_output(["git", "show", admitted+":docs/project-state/LOCAL_CHANGE_LEDGER.jsonl"], cwd=ROOT)
    row = json.loads(rows.splitlines()[-1])
    assert "auth-20261022-owner-mutation-registry-reconciliation" in row["authorization_ids"]
    assert "tools/audit/mutation_suite.py" in row["changed_files"]


def _expanded_check_contexts(jobs):
    import itertools
    import re
    contexts=[]
    for job_id,job in jobs.items():
        matrix=job.get('strategy',{}).get('matrix',{})
        axes={k:v for k,v in matrix.items() if k not in {'include','exclude'}}
        rows=[dict(zip(axes,values)) for values in itertools.product(*axes.values())] if axes else matrix.get('include',[{}])
        assert not matrix.get('exclude'), 'unexpected matrix exclusion requires explicit coverage'
        for row in rows:
            name=job.get('name')
            if name is None:
                name=job_id+(' ('+', '.join(str(v) for v in row.values())+')' if row else '')
            else:
                name=re.sub(r'\$\{\{\s*matrix\.(\w+)\s*\}\}',lambda m:str(row[m[1]]),name)
            assert '${{' not in name
            contexts.append(name)
    return contexts


def _assert_obl004_hosted_transport_and_contexts(workflow):
    import fnmatch
    import re
    import shlex
    jobs=workflow['jobs'];contexts=_expanded_check_contexts(jobs)
    assert len(contexts)==len(set(contexts)), 'displayed check contexts collide'
    join=jobs['obl004-canonical-matrix']
    download=next(s for s in join['steps'] if s.get('uses','').startswith('actions/download-artifact') and 'pattern' in s['with'])
    assert download['with']=={'pattern':'van-obl004-profile-*','path':'${{ runner.temp }}/obl004-profiles','merge-multiple':False}
    join_command=next(s['run'] for s in join['steps'] if 'canonical_source_audit.py join' in s.get('run',''))
    assert '--reports "$RUNNER_TEMP/obl004-profiles"' in join_command
    normalize=next(s['run'] for s in join['steps'] if 'removeprefix' in s.get('run',''))
    assert "removeprefix('van-obl004-profile-')" in normalize
    profiles=[]
    for job_id,job in jobs.items():
        for step in job.get('steps',[]):
            if not step.get('uses','').startswith('actions/upload-artifact'):continue
            value=step['with']['path']
            # Action inputs evaluate expressions, never shell environment syntax.
            assert not re.search(r'\$(?:[A-Za-z_]\w*|\{[A-Za-z_]\w*\})',re.sub(r'\$\{\{.*?\}\}','',value)), (job_id,value)
            name=step['with']['name']
            if not name.startswith('van-obl004-profile-'):continue
            profiles.append(name)
            assert fnmatch.fnmatch(name,download['with']['pattern'])
            assert job['strategy']['matrix']=={'cwd':['checkout','backend']}
            profile=name.removeprefix('van-obl004-profile-').split('-${{')[0]
            assert value=='${{ runner.temp }}/obl004-audit/'+profile+'-${{ matrix.cwd }}/\n!${{ runner.temp }}/obl004-audit/'+profile+'-${{ matrix.cwd }}/**/basetemp/**'
            for cwd in ('checkout','backend'):
                resolve=lambda text:text.replace('${{ runner.temp }}','/owned-runner-temp').replace('$RUNNER_TEMP','/owned-runner-temp').replace('${{ matrix.cwd }}',cwd)
                included,excluded=resolve(value).splitlines()
                assert excluded=='!'+included+'**/basetemp/**'
                commands=[s['run'] for s in job['steps'] if '--profile '+profile+' ' in s.get('run','')]
                assert len(commands)==2
                outputs=[]
                for command in commands:
                    words=shlex.split(resolve(command));outputs.append(words[words.index('--output')+1])
                assert set(outputs)=={included+'collect',included+'execute'}
                assert resolve(name).removeprefix('van-obl004-profile-')==profile+'-'+cwd
    assert len(profiles)==9 and len(set(profiles))==9
    final=next(s for s in join['steps'] if s.get('uses','').startswith('actions/upload-artifact'))
    assert final['with']['path']=='${{ runner.temp }}/obl004-full-matrix.json'


def test_all_upload_paths_resolve_to_real_producers_and_expanded_checks_are_unique():
    _,current=workflows()
    _assert_obl004_hosted_transport_and_contexts(current)


def test_hosted_transport_and_context_controls_reject_the_reviewed_regressions():
    import copy
    import pytest
    _,current=workflows()
    for damage in ('literal-shell-path','lost-exclusion','worker-name','aggregate-name','matrix-name','final-upload'):
        candidate=copy.deepcopy(current);jobs=candidate['jobs']
        upload=next(s for s in jobs['obl004-documentary']['steps'] if s.get('uses','').startswith('actions/upload-artifact'))
        if damage=='literal-shell-path':upload['with']['path']=upload['with']['path'].replace('${{ runner.temp }}','$RUNNER_TEMP')
        elif damage=='lost-exclusion':upload['with']['path']=upload['with']['path'].splitlines()[0]
        elif damage=='worker-name':jobs['obl004-backend-gateway']['name']=jobs['backend-public-source-gateway']['name']
        elif damage=='aggregate-name':jobs['obl004-backend-public-source']['name']=jobs['backend-public-source']['name']
        elif damage=='matrix-name':jobs['obl004-documentary']['name']='same-context'
        else:next(s for s in jobs['obl004-canonical-matrix']['steps'] if s.get('uses','').startswith('actions/upload-artifact'))['with']['path']='$RUNNER_TEMP/obl004-full-matrix.json'
        with pytest.raises(AssertionError):_assert_obl004_hosted_transport_and_contexts(candidate)
