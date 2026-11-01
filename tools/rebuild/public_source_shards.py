"""Exact node/phase evidence for isolated public-source workers, not native admission."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import copy
import shutil
import importlib.metadata
import importlib.util
import json
import base64
import marshal
import io
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import types
import xml.etree.ElementTree as ET

import pytest

# CALL reports run before test monkeypatch teardown. Preserve the original
# primitive without altering application patches; real encode/write errors raise.
_JSON_DUMPS = json.dumps

SCHEMA = "van.public-source-node-ledger/1"
_STATE = None
EXPLICIT_PLUGINS = {"gateway": ("pytest_asyncio.plugin", "anyio.pytest_plugin"),
                    "media": ("pytest_asyncio.plugin",)}
CANONICAL_PYTHONPATH = ["backend", "backend/tests", "trading", "trading/tests", "."]


def import_path_identity(root):
    paths = [Path(p or ".").resolve() for p in os.environ.get("PYTHONPATH", "").split(os.pathsep)]
    require(all(p.is_relative_to(root) for p in paths), "foreign PYTHONPATH source is not committed checkout input")
    relative = [p.relative_to(root).as_posix() for p in paths]
    require(relative == CANONICAL_PYTHONPATH, "PYTHONPATH differs from original public source runtime")
    require(sys.flags.optimize == 0, "optimized Python assertions are not canonical source execution")
    return relative


def generated_evidence_path(path):
    """Only inert outputs, never a blanket exemption for ignored directories."""
    parts = Path(path).parts
    if parts and parts[0] == ".pytest_cache":
        tail = parts[1:]
        return tail in ((".gitignore",), ("CACHEDIR.TAG",), ("README.md",),
                        ("v", "cache", "nodeids"), ("v", "cache", "lastfailed"),
                        ("v", "cache", "stepwise"))
    names = {"selection.json", "tested-commit.txt", "collection.json", "terminal.json",
             "run.json", "phases.jsonl", "storage-audit.json", "report.xml", "summary.json",
             "gateway-report.xml", "media-report.xml", "gateway-storage-audit.json",
             "media-storage-audit.json", "generated-bytecode.json"}
    return (len(parts) >= 3 and parts[0] == "artifacts"
            and parts[1] in {"backend-public-source", *(f"backend-public-source-gateway-{i}" for i in range(4))}
            and parts[-1] in names)


def protected_identity(root):
    result = {}
    for relative in ('data', 'backend/data'):
        base = Path(root) / relative
        rows = []
        if base.is_symlink():
            rows.append({'path': '.', 'kind': 'link', 'value': os.readlink(base)})
        elif base.exists():
            for path in sorted(base.rglob('*')):
                rows.append({'path': path.relative_to(base).as_posix(),
                    'kind': 'link' if path.is_symlink() else 'file' if path.is_file() else 'directory',
                    'value': os.readlink(path) if path.is_symlink() else hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None})
        result[relative] = {'exists': base.exists(), 'entries': rows, 'sha256': fingerprint(rows)}
    return result


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return _JSON_DUMPS(value, sort_keys=True, separators=(",", ":")).encode()


def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def _source_observation(root, expected_commit, *, after_run=False):
    root = Path(root)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(head == expected_commit, "checkout differs from expected exact head")
    changed = subprocess.check_output(["git", "diff", "--no-ext-diff", "--name-only", "HEAD", "--"], cwd=root, text=True)
    require(not changed.strip(), "tracked source differs from tested commit")
    extra = set()
    for flags in (("--others", "--exclude-standard"), ("--others", "--ignored", "--exclude-standard")):
        extra.update(p for p in subprocess.check_output(["git", "ls-files", "-z", *flags], cwd=root).decode().split("\0") if p)
    candidates = sorted(p for p in extra if "__pycache__" in Path(p).parts and p.endswith(".pyc")) if after_run else []
    rejected = sorted(p for p in extra if (root/p).is_symlink()
                      or (p not in candidates and not generated_evidence_path(p)))
    require(not rejected, "uncommitted executable/config/fixture inputs outside explicit inert outputs: " + ", ".join(rejected[:10]))
    config = root / "pytest.ini"
    require(config.is_file() and subprocess.check_output(["git", "ls-files", "--", "pytest.ini"], cwd=root).strip(),
            "committed root pytest.ini required")
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
    return ({"commit": head, "tree": tree, "input_policy": "committed-inputs-parent-verified-cache-outputs/3",
             "pytest_ini_sha256": hashlib.sha256(config.read_bytes()).hexdigest()}, candidates)


def source_identity(root, expected_commit):
    # Every new collection/execution refuses repository bytecode, even valid caches.
    return _source_observation(root, expected_commit)[0]


def _code_identity(value, depth=0):
    """Typed code/constant graph; frozenset wire order and interning are not code semantics."""
    require(depth < 256, "generated code graph exceeds bounded depth")
    if type(value) is types.CodeType:
        fields = ("co_argcount", "co_posonlyargcount", "co_kwonlyargcount", "co_nlocals", "co_stacksize",
                  "co_flags", "co_code", "co_consts", "co_names", "co_varnames", "co_freevars", "co_cellvars",
                  "co_filename", "co_name", "co_qualname", "co_firstlineno", "co_linetable", "co_exceptiontable")
        return ["code", {name:_code_identity(getattr(value,name),depth+1) for name in fields}]
    if type(value) is tuple:
        return ["tuple", [_code_identity(v,depth+1) for v in value]]
    if type(value) is frozenset:
        return ["frozenset", sorted((_code_identity(v,depth+1) for v in value),key=encoded)]
    if type(value) is bytes:return ["bytes",value.hex()]
    if type(value) is float:return ["float",struct.pack("!d",value).hex()]
    if type(value) is complex:return ["complex",struct.pack("!dd",value.real,value.imag).hex()]
    if type(value) in (str,int,bool):return [type(value).__name__,value]
    if value is None:return ["None"]
    if value is Ellipsis:return ["Ellipsis"]
    raise ValueError("unsupported generated code constant")


def _cache_proof(root, expected_commit, relative, data, *, origin_root, source_mtime):
    """Decode only as verifier data; compare every code field to fresh committed compilation. Never execute/import it."""
    root = Path(root)
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts and path.parent.name == "__pycache__",
            "noncanonical generated cache path")
    match = re.fullmatch(r"(.+)\." + re.escape(sys.implementation.cache_tag) + r"(?:\.opt-([12]))?\.pyc", path.name)
    require(match is not None, "wrong interpreter/optimization cache name")
    source = path.parent.parent / (match[1] + ".py")
    mode = subprocess.check_output(["git", "ls-tree", expected_commit, "--", source.as_posix()], cwd=root)
    require(mode.startswith((b"100644 blob ", b"100755 blob ")), "cache source is not exact tracked regular source")
    original = subprocess.check_output(["git", "show", expected_commit + ":" + source.as_posix()], cwd=root)
    require(len(data) >= 16 and data[:4] == importlib.util.MAGIC_NUMBER, "wrong generated cache magic/header")
    flags = int.from_bytes(data[4:8], "little")
    require(flags in (0, 1, 3), "invalid generated cache flags")
    require(type(source_mtime) is int and 0 <= source_mtime < 2**32, "missing original source timestamp")
    if flags == 0:
        require(int.from_bytes(data[8:12], "little") == source_mtime
                and int.from_bytes(data[12:16], "little") == len(original) % 2**32,
                "generated cache timestamp/size differs from original source")
    else:
        require(data[8:16] == importlib.util.source_hash(original), "generated cache source hash differs")
    require(Path(origin_root).is_absolute(), "missing original compile root")
    filename = str(Path(origin_root) / source)
    optimization = int(match[2] or 0)
    expected = _code_identity(compile(original, filename, "exec", dont_inherit=True, optimize=optimization))
    stream = io.BytesIO(data[16:])
    decoded = marshal.load(stream)
    require(type(decoded) is types.CodeType and stream.tell() == len(data)-16, "invalid/trailing generated code payload")
    observed = _code_identity(decoded)
    require(observed == expected, "generated cache payload differs from exact committed compilation")
    return {"path": relative, "source": source.as_posix(), "source_sha256": hashlib.sha256(original).hexdigest(),
            "source_mtime": source_mtime, "source_size": len(original), "flags": flags,
            "optimization": optimization, "code_filename": filename,
            "code_identity_sha256":fingerprint(expected), "cache_sha256": hashlib.sha256(data).hexdigest()}


def archive_generated_bytecode(root, expected_commit, before, output):
    """Parent-only post-child validation; archive then retire only verified own outputs."""
    root = Path(root).resolve()
    after, candidates = _source_observation(root, expected_commit, after_run=True)
    require(after == before, "source drift before generated-cache validation")
    records = []
    for relative in candidates:
        path = root / relative
        require(path.stat().st_size <= 8 * 1024 * 1024, "generated cache exceeds bounded evidence size")
        data = path.read_bytes()
        # Derive only a candidate source path here; _cache_proof validates the full name/mode.
        name = path.name.split("." + sys.implementation.cache_tag, 1)[0]
        source = path.parent.parent / (name + ".py")
        require(source.is_file() and not source.is_symlink(), "cache source absent or symlinked")
        original = subprocess.check_output(["git", "show", expected_commit + ":" + str(source.relative_to(root))], cwd=root)
        require(source.read_bytes() == original, "cache source changed from committed bytes")
        proof = _cache_proof(root, expected_commit, relative, data, origin_root=str(root),
                             source_mtime=int(source.stat().st_mtime) % 2**32)
        records.append({**proof, "payload_base64": base64.b64encode(data).decode("ascii")})
    artifact = {"schema": "van.parent-verified-generated-bytecode/1", "expected_commit": expected_commit,
                "input_bytecode_paths": [], "records": records}
    destination = Path(output) / "generated-bytecode.json"
    destination.write_text(_JSON_DUMPS(artifact, indent=2) + "\n")
    require(read_json(destination) == artifact, "generated cache evidence readback failed")
    for record in records:
        path = root / record["path"]
        require(not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == record["cache_sha256"],
                "generated cache changed during archive")
        path.unlink()  # Absent at strict preflight; exact verified output retained non-importably above.
    require(source_identity(root, expected_commit) == before, "unexpected inputs after output retirement")
    return candidates


def verify_generated_bytecode(folder, root, expected_commit, state, receipt):
    artifact = read_json(Path(folder) / "generated-bytecode.json")
    require(artifact.get("schema") == "van.parent-verified-generated-bytecode/1"
            and artifact.get("expected_commit") == expected_commit and artifact.get("input_bytecode_paths") == [],
            "missing parent verified generated-cache provenance")
    records = artifact.get("records")
    require(isinstance(records, list), "missing generated-cache records")
    paths = [r["path"] for r in records]
    require(paths == sorted(set(paths)) == state.get("generated_cache_candidates")
            == receipt.get("generated_cache_outputs"), "generated-cache candidate/output disagreement")
    for record in records:
        require(len(record["payload_base64"]) <= 12*1024*1024, "generated cache artifact exceeds bounded size")
        data = base64.b64decode(record["payload_base64"], validate=True)
        expected = _cache_proof(root, expected_commit, record["path"], data,
                                origin_root=state["root"], source_mtime=record["source_mtime"])
        require({k:v for k,v in record.items() if k != "payload_base64"} == expected,
                "generated cache proof differs from committed source compilation")


def effective_pytest_inputs(config, root, runtime):
    """Bind effective configuration and actual plugin code, not just package names."""
    require(Path(config.inipath).resolve() == root / "pytest.ini" and Path(config.rootpath).resolve() == root,
            "noncanonical effective pytest configuration/root")
    require(os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") == "1", "ambient pytest plugin autoload is forbidden")
    require(sorted(e.value for e in importlib.metadata.entry_points(group="pytest11")) == sorted(EXPLICIT_PLUGINS[runtime]),
            "original locked runtime pytest plugin set differs from explicit loading")
    require(all(Path(p).resolve().is_relative_to(root) for p in config.getini("pythonpath")),
            "pytest config adds foreign import source")
    plugins = {}
    for name, plugin in config.pluginmanager.list_name_plugin():
        if plugin is None:
            continue
        filename = getattr(plugin, "__file__", None)
        if filename:
            file = Path(filename).resolve()
            if file.is_relative_to(root):
                relative = str(file.relative_to(root))
                require(subprocess.check_output(["git", "ls-files", "--", relative], cwd=root).strip(),
                        "uncommitted loaded pytest plugin: " + relative)
                identity = relative
            else:
                identity = getattr(plugin, "__name__", str(name))
            plugins[identity] = hashlib.sha256(file.read_bytes()).hexdigest()
    require(all(p in plugins for p in EXPLICIT_PLUGINS[runtime]), "original explicit runtime plugins missing")
    return {"config_sha256": hashlib.sha256((root/"pytest.ini").read_bytes()).hexdigest(),
            "plugins": plugins, "autoload": False}


def environment_identity(runtime):
    packages = sorted({(d.metadata.get("Name", "").lower(), d.version)
                       for d in importlib.metadata.distributions()})
    chromium = os.environ.get("VAN_TEST_CHROMIUM")
    pg_version = None
    if runtime == "gateway" and os.environ.get("VATI_TEST_PG_DSN"):
        import psycopg
        with psycopg.connect(os.environ["VATI_TEST_PG_DSN"]) as conn:
            pg_version = conn.info.server_version
    node = subprocess.run(["node", "--version"], capture_output=True, text=True)
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "system": platform.system(), "machine": platform.machine(),
            "image_os": os.environ.get("ImageOS"), "image_version": os.environ.get("ImageVersion"),
            "packages": packages, "node": node.stdout.strip() if node.returncode == 0 else None,
            "chromium_sha256": hashlib.sha256(Path(chromium).read_bytes()).hexdigest() if chromium else None,
            "postgres_version": pg_version,
            "pytest_entrypoints": sorted(e.value for e in importlib.metadata.entry_points(group="pytest11")),
            "pythonpath": import_path_identity(Path(__file__).resolve().parents[2]),
            "isolated_pg_fixture": os.environ.get("VATI_TEST_PG_ISOLATED_FIXTURE") if runtime == "gateway" else None}


def assignment(nodeids, selected, costs, shard_count):
    """Whole-file LPT; historical cost affects placement, never inclusion."""
    require(shard_count > 0, "invalid shard count")
    require(len(nodeids) == len(set(nodeids)) and nodeids, "empty or duplicate collection")
    files = {r["path"]: r["sha256"] for r in selected}
    grouped = defaultdict(list)
    for node in nodeids:
        path = node.split("::", 1)[0]
        require(path in files and "::" in node, "foreign collected node: " + node)
        grouped[path].append(node)
    require(set(grouped) == set(files), "selected module missing from full collection")
    loads = [0.0] * shard_count
    bins = [[] for _ in loads]
    work = []
    for path, nodes in grouped.items():
        previous = costs.get("costs", {}).get(path, {})
        weight = (float(previous["seconds"]) if previous.get("test_source_sha256") == files[path]
                  else float(len(nodes)))
        require(weight >= 0 and weight < float("inf"), "invalid historical weight")
        work.append((path, weight))
    for path, weight in sorted(work, key=lambda x: (-x[1], x[0])):
        index = min(range(shard_count), key=lambda i: (loads[i], i))
        bins[index].extend(grouped[path])
        loads[index] += weight
    require(all(bins), "empty execution shard; revise explicit worker count")
    return [sorted(nodes) for nodes in bins]


def pytest_addoption(parser):
    group = parser.getgroup("van-source-evidence")
    group.addoption("--van-source-output")
    group.addoption("--van-source-root")
    group.addoption("--van-source-expected-commit")
    group.addoption("--van-source-execution-id")
    group.addoption("--van-source-cwd", choices=("checkout", "backend"), default="checkout")
    group.addoption("--van-source-runtime", choices=("gateway", "media"))
    group.addoption("--van-source-shards", type=int, default=1)
    group.addoption("--van-source-index", type=int, default=0)
    group.addoption("--van-source-costs")


def pytest_configure(config):
    global _STATE
    output = config.getoption("--van-source-output")
    if not output:
        return
    require(not config.option.keyword and not config.option.markexpr and not config.option.deselect
            and not getattr(config.option, "lf", False)
            and getattr(config.option, "numprocesses", None) in (None, 0),
            "test selection overrides or shared-store parallelism are forbidden")
    from tools.rebuild import backend_public_source as gate
    root = Path(config.getoption("--van-source-root")).resolve()
    runtime = config.getoption("--van-source-runtime")
    expected = config.getoption("--van-source-expected-commit")
    require(expected and runtime and config.getoption("--van-source-execution-id"), "exact head, runtime and fresh execution identity required")
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=True)
    execution_cwd = config.getoption("--van-source-cwd")
    invocation_cwd = gate.execution_directory(root, execution_cwd)
    require(Path.cwd().resolve() == invocation_cwd, "actual pytest cwd differs from selected canonical cwd")
    selection = gate.plan(root)
    selected = [r for r in selection["selected"] if gate.runtime(r["path"]) == runtime]
    _STATE = {"invocation_cwd": str(invocation_cwd), "execution_cwd": execution_cwd, "schema": SCHEMA, "runtime": runtime, "expected_commit": expected,
              "workflow_run": {"id": os.environ.get("GITHUB_RUN_ID"), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT")},
              "mode": "collection" if config.option.collectonly else "execution",
              "execution_id": config.getoption("--van-source-execution-id"),
              "source_before": source_identity(root, expected),
              "protected_before": protected_identity(root),
              "pytest_inputs": effective_pytest_inputs(config, root, runtime),
              "environment_before": environment_identity(runtime),
              "selection": selection, "selected": selected,
              "shard_count": config.getoption("--van-source-shards"),
              "shard_index": config.getoption("--van-source-index"),
              "collection_errors": [], "internal_errors": [],
              "instrument_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "costs": read_json(config.getoption("--van-source-costs"))}
    _STATE["root"] = str(root)
    _STATE["output"] = str(folder)
    (folder / "phases.jsonl").write_text("")
    config._van_source_evidence = _STATE


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    state = getattr(config, "_van_source_evidence", None)
    if state is None:
        return
    full = [item.nodeid for item in items]
    bins = assignment(full, state["selected"], state["costs"], state["shard_count"])
    index = state["shard_index"]
    require(0 <= index < len(bins), "invalid execution shard")
    state.update(full_collection=sorted(full), assignment=bins, assigned=bins[index])
    state["full_collection_sha256"] = fingerprint(state["full_collection"])
    state["assignment_sha256"] = fingerprint(bins)
    if state["mode"] == "execution":
        own = set(bins[index])
        dropped = [item for item in items if item.nodeid not in own]
        items[:] = [item for item in items if item.nodeid in own]
        config.hook.pytest_deselected(items=dropped)
    for item in items:
        item.user_properties.append(("van_source_nodeid", item.nodeid))
    (Path(state["output"]) / "collection.json").write_text(_JSON_DUMPS(state, indent=2) + "\n")


def pytest_collectreport(report):
    if _STATE is not None and report.failed:
        _STATE["collection_errors"].append(str(report.nodeid))


def pytest_internalerror(excrepr, excinfo):
    if _STATE is not None:
        _STATE["internal_errors"].append(str(excrepr))


def pytest_runtest_logreport(report):
    if _STATE is None:
        return
    reason = None
    if report.skipped:
        value = report.longrepr
        reason = str(value[2] if isinstance(value, tuple) else value)
        if reason.startswith("Skipped: "):
            reason = reason[len("Skipped: "):]
    event = {"nodeid": report.nodeid, "when": report.when, "outcome": report.outcome,
             "duration": report.duration, "skip_reason": reason}
    with (Path(_STATE["output"]) / "phases.jsonl").open("a") as stream:
        stream.write(_JSON_DUMPS(event, sort_keys=True) + "\n")


def pytest_sessionfinish(session, exitstatus):
    state = getattr(session.config, "_van_source_evidence", None)
    if state is None:
        return
    source_after, candidates = _source_observation(state["root"], state["expected_commit"], after_run=True)
    state.update(protected_after=protected_identity(state["root"]), pytest_exit=int(exitstatus), generated_cache_candidates=candidates,
                 source_after=source_after,
                 environment_after=environment_identity(state["runtime"]))
    (Path(state["output"]) / "terminal.json").write_text(_JSON_DUMPS(state, indent=2) + "\n")


def approved_skip(nodeid, reason):
    from tools.rebuild import backend_public_source as gate
    path, _, name = nodeid.partition("::")
    name = name.rsplit("::", 1)[-1]
    return any(path == allowed_path and (name == test or name.startswith(test + "["))
               for allowed_path, test in gate.ALLOWED_SKIPS.get(reason, ()))


def verify_snapshot(folder, manifest, runtime, expected_commit, costs, root, *, collection, execution_cwd="checkout"):
    """Validate a terminal worker, including storage and subprocess evidence."""
    from tools.rebuild import backend_public_source as gate
    folder = Path(folder)
    state = read_json(folder / "terminal.json")
    receipt = read_json(folder / "run.json")
    require(state.get("schema") == SCHEMA, "unknown node evidence schema")
    invocation_cwd = gate.execution_directory(root, execution_cwd)
    require(state.get("execution_cwd") == receipt.get("execution_cwd") == execution_cwd
            and state.get("invocation_cwd") == receipt.get("invocation_cwd") == str(invocation_cwd),
            "wrong or missing actual execution cwd")
    require(state.get("execution_id") and state.get("execution_id") == receipt.get("execution_id"), "stale/different execution receipt")
    require(not receipt.get("parent_observation_error"), "parent source/runtime identity observation failed")
    require(state.get("mode") == ("collection" if collection else "execution"), "wrong evidence mode")
    require(state.get("workflow_run") == receipt.get("workflow_run") ==
            {"id": os.environ.get("GITHUB_RUN_ID"), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT")},
            "different workflow run/attempt")
    require(state.get("runtime") == runtime and state.get("expected_commit") == expected_commit,
            "wrong runtime or tested head")
    require(state.get("protected_before") == state.get("protected_after")
            == receipt.get("protected_before") == receipt.get("protected_after") == protected_identity(root),
            "protected-directory snapshot changed or missing")
    expected_source = source_identity(root, expected_commit)
    require(state.get("source_before") == expected_source == state.get("source_after")
            == receipt.get("source_before") == receipt.get("source_after"), "source identity drift")
    require(type(receipt.get("exit")) is int and type(state.get("pytest_exit")) is int, "invalid exit evidence type")
    require(receipt.get("expected_commit") == expected_commit and receipt.get("exit") == 0
            and receipt.get("terminal") is True and state.get("pytest_exit") == 0,
            "nonterminal or unsuccessful actual subprocess")
    require(state.get("collection_errors") == [] and state.get("internal_errors") == [], "missing or failed collection/internal evidence")
    require(state.get("selection") == manifest, "selection/source bytes differ")
    inputs = state.get("pytest_inputs", {})
    require(set(inputs) == {"config_sha256", "plugins", "autoload"}
            and inputs["autoload"] is False
            and inputs["config_sha256"] == hashlib.sha256((Path(root)/"pytest.ini").read_bytes()).hexdigest()
            and isinstance(inputs["plugins"], dict)
            and all(p in inputs["plugins"] for p in EXPLICIT_PLUGINS[runtime])
            and all(isinstance(v, str) and len(v) == 64 for v in inputs["plugins"].values()),
            "missing/noncanonical effective pytest inputs")
    require(state.get("environment_before") == state.get("environment_after")
            == receipt.get("environment_before") == receipt.get("environment_after"), "worker/parent environment drift")
    environment = state["environment_before"]
    require(set(environment) == {"python", "implementation", "system", "machine", "image_os", "image_version",
        "packages", "node", "chromium_sha256", "postgres_version", "isolated_pg_fixture", "pytest_entrypoints", "pythonpath"},
        "incomplete environment identity")
    require(environment["packages"] and environment["node"] == "v24.19.0"
            and environment["image_os"] == "ubuntu24" and environment["image_version"]
            and len(environment.get("chromium_sha256") or "") == 64, "missing pinned hosted runtime identity")
    require(environment.get("python", "").startswith("3.12.") and environment.get("system") == "Linux",
            "unsupported source worker runtime")
    require(environment.get("pytest_entrypoints") == sorted(EXPLICIT_PLUGINS[runtime]),
            "original locked runtime plugin set was not preserved")
    require(environment.get("pythonpath") == CANONICAL_PYTHONPATH, "original runtime import roots were not preserved")
    if runtime == "gateway":
        require(environment.get("postgres_version") == 170011
                and environment.get("isolated_pg_fixture") == "1", "missing pinned isolated PostgreSQL fixture")
    require(state.get("instrument_sha256") == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "different execution instrument")
    require(state.get("costs") == costs, "different assignment costs")
    selected = [r for r in manifest["selected"] if gate.runtime(r["path"]) == runtime]
    require(state.get("selected") == selected, "worker selected a different runtime scope")
    full = state.get("full_collection", [])
    bins = assignment(full, selected, costs, state["shard_count"])
    require(state.get("assignment") == bins and state.get("assigned") == bins[state["shard_index"]],
            "assignment differs from deterministic full collection")
    require(state.get("full_collection_sha256") == fingerprint(full)
            and state.get("assignment_sha256") == fingerprint(bins), "collection/assignment digest mismatch")
    for name, digest in receipt.get("artifact_sha256", {}).items():
        require(name in {"terminal.json", "phases.jsonl", "report.xml", "storage-audit.json", "generated-bytecode.json"}, "foreign receipt artifact")
        require(hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest, "worker artifact hash mismatch")
    mandatory = {"terminal.json", "phases.jsonl", "storage-audit.json", "generated-bytecode.json"} | (set() if collection else {"report.xml"})
    require(set(receipt.get("artifact_sha256", {})) == mandatory, "incomplete worker artifact receipt")
    verify_generated_bytecode(folder, root, expected_commit, state, receipt)
    audit = read_json(folder / "storage-audit.json")
    require(audit.get("schema") == "van.source-storage-audit/1" and audit.get("forbidden_events") == []
            and audit.get("source_sha256") == hashlib.sha256(Path(__file__).with_name("source_storage_audit.py").read_bytes()).hexdigest()
            and audit.get("root") == str(Path(root).resolve())
            and audit.get("invocation_cwd") == str(invocation_cwd),
            "missing/wrong source-storage instrument or violation")
    events = [json.loads(line) for line in (folder / "phases.jsonl").read_text().splitlines()]
    if collection:
        require(not events, "collect-only control executed test effects")
        return state, {}, []
    assigned = set(state["assigned"])
    phases = defaultdict(dict)
    for event in events:
        node, when = event.get("nodeid"), event.get("when")
        require(node in assigned and when in {"setup", "call", "teardown"}, "foreign execution phase")
        require(when not in phases[node], "duplicate execution phase or hidden rerun")
        require(event.get("outcome") in {"passed", "skipped"}, "failed/error execution phase")
        phases[node][when] = event
    require(set(phases) == assigned, "missing actual execution identities")
    outcomes, skipped = {}, []
    for node, reports in phases.items():
        require("setup" in reports and "teardown" in reports, "incomplete setup/teardown")
        require(reports["teardown"]["outcome"] == "passed", "teardown did not pass")
        setup_skip = reports["setup"]["outcome"] == "skipped"
        require(set(reports) == ({"setup", "teardown"} if setup_skip else {"setup", "call", "teardown"}),
                "missing/extra case phase")
        skip_events = [event for event in reports.values() if event["outcome"] == "skipped"]
        if skip_events:
            require(len(skip_events) == 1 and approved_skip(node, skip_events[0].get("skip_reason")),
                    "unapproved case/phase skip: " + node)
            outcomes[node] = "skipped"
            skipped.append({"id": node, "reason": skip_events[0]["skip_reason"]})
        else:
            outcomes[node] = "passed"
    junit = {}
    for case in ET.parse(folder / "report.xml").getroot().iter("testcase"):
        properties = case.findall("./properties/property[@name='van_source_nodeid']")
        require(len(properties) == 1, "JUnit lacks one exact node identity")
        node = properties[0].get("value")
        require(node in assigned and node not in junit, "foreign/duplicate JUnit identity")
        require(case.find("failure") is None and case.find("error") is None, "failed/error JUnit case")
        skip = case.find("skipped")
        junit[node] = "skipped" if skip is not None else "passed"
        if skip is not None:
            require(approved_skip(node, skip.get("message", "")), "unapproved JUnit skip")
    require(junit == outcomes, "JUnit/phase execution union differs")
    return state, outcomes, skipped


def verify_shards(output, expected_commit, job_result, *, root, shard_count=4, execution_cwd="checkout"):
    """The required gate has no status-only or legacy-module-count fallback."""
    from tools.rebuild import backend_public_source as gate
    output = Path(output)
    require(os.environ.get("GITHUB_RUN_ID") and os.environ.get("GITHUB_RUN_ATTEMPT"), "native workflow run identity required")
    require(shard_count == 4 and job_result == "success", "all four execution workers must finish successfully")
    manifest = read_json(output / "selection.json")
    require(manifest == gate.plan(root), "aggregate selection/source drift")
    costs = read_json(Path(root) / "tools/rebuild/backend_public_source_costs.json")
    control, _, _ = verify_snapshot(output / "gateway-control", manifest, "gateway", expected_commit,
                                    costs, root, collection=True, execution_cwd=execution_cwd)
    require(control["shard_count"] == shard_count, "wrong control assignment cardinality")
    all_outcomes, skips, receipts = {}, [], []
    for index in range(shard_count):
        folder = output / "shards" / ("van-backend-public-source-gateway-" + str(index))
        state, outcomes, declared = verify_snapshot(folder, manifest, "gateway", expected_commit,
                                                    costs, root, collection=False, execution_cwd=execution_cwd)
        require(state["shard_index"] == index and state["shard_count"] == shard_count, "wrong shard identity")
        require(state["full_collection"] == control["full_collection"]
                and state["assignment"] == control["assignment"], "full collection/assignment disagreement")
        require(state["environment_before"] == control["environment_before"], "gateway workers have different environments")
        require(state["pytest_inputs"] == control["pytest_inputs"], "gateway effective pytest inputs differ")
        require(not set(all_outcomes) & set(outcomes), "duplicate execution across shards")
        all_outcomes.update(outcomes)
        skips.extend(declared)
        receipts.append({"shard": index, "tests": len(outcomes), "terminal_sha256":
                         hashlib.sha256((folder / "terminal.json").read_bytes()).hexdigest()})
    require(Counter(all_outcomes.keys()) == Counter(control["full_collection"]), "gateway exact execution union is incomplete")
    media_control, _, _ = verify_snapshot(output / "media-control", manifest, "media", expected_commit,
                                          costs, root, collection=True, execution_cwd=execution_cwd)
    media, outcomes, declared = verify_snapshot(output / "media", manifest, "media", expected_commit,
                                                costs, root, collection=False, execution_cwd=execution_cwd)
    require(media["shard_count"] == 1 and media["shard_index"] == 0, "wrong isolated media worker")
    require(media["full_collection"] == media_control["full_collection"]
            and media["environment_before"] == media_control["environment_before"], "media collection/environment differs")
    require(media["pytest_inputs"] == media_control["pytest_inputs"], "media effective pytest inputs differ")
    require(Counter(outcomes.keys()) == Counter(media_control["full_collection"]), "media exact execution union incomplete")
    require(not set(all_outcomes) & set(outcomes), "cross-runtime duplicate execution")
    all_outcomes.update(outcomes)
    skips.extend(declared)
    # Compatibility artifacts are derived only AFTER exact phase/identity validation.
    # Originals remain under their shard folders; this is not a single-process run.
    combined = ET.Element("testsuites", name="derived-exact-gateway-shard-union")
    child_audits = []
    for index in range(shard_count):
        folder = output / "shards" / ("van-backend-public-source-gateway-" + str(index))
        xml = ET.parse(folder/"report.xml").getroot()
        for suite in (list(xml) if xml.tag == "testsuites" else [xml]):
            combined.append(copy.deepcopy(suite))
        child_audits.append({"shard": index, "sha256": hashlib.sha256((folder/"storage-audit.json").read_bytes()).hexdigest()})
    (output/"gateway-report.xml").write_bytes(ET.tostring(combined))
    (output/"gateway-storage-audit.json").write_text(_JSON_DUMPS({"forbidden_events": [],
        "scope": "Derived union of four independently verified child audits; original artifacts retained",
        "child_audits": child_audits}, indent=2)+"\n")
    shutil.copyfile(output/"media/report.xml", output/"media-report.xml")
    shutil.copyfile(output/"media/storage-audit.json", output/"media-storage-audit.json")
    runtimes = {name: {"junit_sha256": hashlib.sha256((output/(name+"-report.xml")).read_bytes()).hexdigest(),
        "storage_audit_sha256": hashlib.sha256((output/(name+"-storage-audit.json")).read_bytes()).hexdigest(),
        "tests": len(control["full_collection"] if name == "gateway" else media["full_collection"])}
        for name in ("gateway", "media")}
    return {"status": "PUBLIC_SOURCE_SUBSET_PASS", "tested_commit": expected_commit,
            "tests": len(all_outcomes), "passed": sum(v == "passed" for v in all_outcomes.values()),
            "declared_unexecuted": skips, "gateway_shards": receipts,
            "execution_mode": "FOUR_ISOLATED_GATEWAY_WORKERS_PLUS_SEPARATE_MEDIA",
            "isolated_runtimes": runtimes,
            "exact_collection_sha256": fingerprint(sorted(all_outcomes)),
            "separate_modules": manifest["separate"], "limits": manifest["qualification"],
            "certificates_issued": [], "proof": "Exact full collection, deterministic whole-file assignment, actual setup/call/teardown and JUnit union; all runtimes terminal"}
