import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("owner_registry_refresh", ROOT/"tools/rebuild/refresh_owner_source_contracts.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    originals = {(ref,p): (ref+":"+p).encode() for ref in (module.INPUT,module.LEGACY_GENERATION) for p in module.REGISTRIES}
    originals.update({("HEAD",p): ("generated:"+p).encode() for p in module.REGISTRIES})
    originals["HEAD",module.RECEIPT] = b"source receipt"
    record = {"schema":"van.rebuild.owner-registry-generation/1",
        "source_receipt_sha256":module.sha(b"source receipt"),
        "outputs":{p:module.sha(originals["HEAD",p]) for p in module.REGISTRIES}}
    originals["HEAD",module.GENERATION] = json.dumps(record).encode()
    def read(ref,path):
        try:return originals[ref,path]
        except KeyError:raise subprocess.CalledProcessError(128,["git","show",ref+":"+path])
    return originals,record,read


def test_original_and_previous_generated_registry_are_safe_preimages():
    originals,_,read=fixture()
    for ref in (module.INPUT,module.LEGACY_GENERATION,"HEAD"):
        for path in module.REGISTRIES:
            assert module.approved_preimage(path,originals[ref,path],read)


def test_local_owner_edits_are_never_replaced_even_when_head_generation_is_valid():
    originals,_,read=fixture()
    for path in module.REGISTRIES:
        assert not module.approved_preimage(path,originals["HEAD",path]+b"owner edit",read)


@pytest.mark.parametrize("corruption", ["source_receipt","one_registry","missing_output","unknown_schema"])
def test_a_broken_generation_cannot_authorize_refreshing_even_its_untouched_files(corruption):
    originals,record,read=fixture()
    target="registries/owner_features.json"
    if corruption=="source_receipt": originals["HEAD",module.RECEIPT]=b"different receipt"
    elif corruption=="one_registry": originals["HEAD","registries/owner_screens.json"]=b"committed owner edit"
    elif corruption=="missing_output": record["outputs"].pop("registries/owner_screens.json")
    else: record["schema"]="unknown-generation"
    originals["HEAD",module.GENERATION]=json.dumps(record).encode()
    assert not module.approved_preimage(target,originals["HEAD",target],read)


def test_an_arbitrary_committed_registry_is_not_automatically_a_generated_preimage():
    originals,_,read=fixture()
    originals.pop(("HEAD",module.GENERATION))
    path="registries/owner_features.json"
    assert not module.approved_preimage(path,originals["HEAD",path],read)
    assert not module.approved_preimage("registries/other.json",b"anything",read)


@pytest.mark.parametrize("corruption", ["none", "owner_edit", "source_receipt"])
def test_main_uses_supplied_object_reader_and_keeps_all_preimage_checks(tmp_path, monkeypatch, corruption):
    originals, _, read = fixture()
    for path in module.REGISTRIES:
        target = tmp_path/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(originals["HEAD", path])
    if corruption == "owner_edit":
        target = tmp_path/"registries/owner_screens.json"
        target.write_bytes(target.read_bytes()+b"owner edit")
    elif corruption == "source_receipt":
        originals["HEAD", module.RECEIPT] = b"changed committed receipt"
    outputs = {path: b"new derived bytes:"+path.encode() for path in module.REGISTRIES}
    def build(*, read):
        assert read is supplied
        return outputs
    supplied = read
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "build", build)
    monkeypatch.setattr(module.sys, "argv", ["refresh_owner_source_contracts.py", "--apply"])
    before = {p: (tmp_path/p).read_bytes() for p in module.REGISTRIES}
    if corruption == "none":
        assert module.main(read=supplied) == 0
        assert all((tmp_path/p).read_bytes() == data for p, data in outputs.items())
    else:
        with pytest.raises(ValueError, match="Unexpected registry edits"):
            module.main(read=supplied)
        assert all((tmp_path/p).read_bytes() == data for p, data in before.items())
