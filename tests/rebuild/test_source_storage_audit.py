"""Keep the actual filesystem misuse probes in the documentary CI suite."""
import json
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize("cwd", [".", "backend"])
def test_actual_cli_binds_both_protected_trees_from_either_directory(tmp_path, cwd):
    import shutil
    tool = Path(__file__).resolve().parents[2]/"tools/rebuild/source_storage_audit.py"
    root = tmp_path/"checkout"
    (root/".git").mkdir(parents=True)
    (root/"backend/tests").mkdir(parents=True)
    (root/"tools/rebuild").mkdir(parents=True)
    (root/"pytest.ini").write_text("[pytest]\n")
    shutil.copyfile(tool, root/"tools/rebuild/source_storage_audit.py")
    (root/"data").mkdir()
    (root/"backend/data").mkdir()
    sentinels = [root/"data/seed", root/"backend/data/seed"]
    for p in sentinels:
        p.write_bytes(b"owned snapshot sentinel")
    case = tmp_path/"test_protected.py"
    case.write_text("import pytest\nfrom pathlib import Path\ndef test_protected():\n"
                    + "".join(f" with pytest.raises(AssertionError, match='checkout runtime storage'):\n  Path({str(p)!r}).write_bytes(b'bad')\n" for p in sentinels))
    report = tmp_path/"audit.json"
    result = subprocess.run([sys.executable, "-B", str(tool), "--checkout-root", str(root),
                             "--report", str(report), str(case), "-q", "-p", "no:cacheprovider",
                             "--basetemp="+str(tmp_path/"pytest")], cwd=root/cwd,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
    observed = json.loads(report.read_text())
    assert observed["root"] == str(root)
    assert observed["invocation_cwd"] == str((root/cwd).resolve())
    assert {v["path"] for v in observed["forbidden_events"]} == {"data/seed", "backend/data/seed"}
    assert all(p.read_bytes() == b"owned snapshot sentinel" for p in sentinels)


@pytest.mark.parametrize("choice", ["outside", "backend", "outside-cwd", "nested"])
def test_actual_cli_refuses_an_override_or_ambiguous_root_before_pytest(tmp_path, choice):
    import shutil
    tool = Path(__file__).resolve().parents[2]/"tools/rebuild/source_storage_audit.py"
    root = tmp_path/"checkout"
    def markers(p):
        (p/".git").mkdir(parents=True)
        (p/"backend/tests").mkdir(parents=True)
        (p/"tools/rebuild").mkdir(parents=True)
        (p/"pytest.ini").write_text("[pytest]\n")
        shutil.copyfile(tool, p/"tools/rebuild/source_storage_audit.py")
    markers(root)
    outside = tmp_path/"outside"
    outside.mkdir()
    requested, cwd = outside, root
    if choice == "backend":
        requested = root/"backend"
    elif choice == "outside-cwd":
        requested, cwd = root, outside
    elif choice == "nested":
        requested = root/"nested"
        markers(requested)
        cwd = requested
    report = tmp_path/"never-report.json"
    case = tmp_path/"test_never.py"
    case.write_text("raise AssertionError('collection must never start')\n")
    result = subprocess.run([sys.executable, "-B", str(tool), "--checkout-root", str(requested),
                             "--report", str(report), str(case)], cwd=cwd,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 2, result.stdout+result.stderr
    assert not report.exists()
    assert "collection must never start" not in result.stdout+result.stderr


def test_storage_audit_rejects_planted_writes_and_preserves_valid_access():
    tool=Path(__file__).resolve().parents[2]/'tools/rebuild/source_storage_audit.py'
    result=subprocess.run([sys.executable,str(tool),'--selftest'],capture_output=True,text=True,check=True)
    observed=json.loads(result.stdout)
    assert observed['rejected']>=14
    assert observed['allowed_read_and_external_write'] is True


@pytest.mark.parametrize('operation', ['mkdir','unlink','rmdir','rename-to','rename-from','link-to','symlink-to'])
def test_real_directory_fd_mutations_cannot_bypass_the_storage_boundary(operation):
    code = r'''
import os,sys,tempfile
from pathlib import Path
from tools.rebuild.source_storage_audit import StorageAudit
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp)/'checkout';protected=root/'data';protected.mkdir(parents=True)
 outside=Path(temp)/'external';outside.mkdir()
 (protected/'seed').write_text('original fixture');(protected/'empty').mkdir()
 (outside/'outside-seed').write_text('external fixture')
 current=Path.cwd();target=os.open(protected,os.O_RDONLY|os.O_DIRECTORY);external=os.open(outside,os.O_RDONLY|os.O_DIRECTORY)
 audit=StorageAudit(root);sys.addaudithook(audit)
 actions={
  'mkdir':lambda:os.mkdir('new',dir_fd=target),
  'unlink':lambda:os.unlink('seed',dir_fd=target),
  'rmdir':lambda:os.rmdir('empty',dir_fd=target),
  'rename-to':lambda:os.rename('outside-seed','moved',src_dir_fd=external,dst_dir_fd=target),
  'rename-from':lambda:os.rename('seed','moved',src_dir_fd=target,dst_dir_fd=external),
  'link-to':lambda:os.link('outside-seed','linked',src_dir_fd=external,dst_dir_fd=target),
  'symlink-to':lambda:os.symlink('outside-seed','alias',dir_fd=target),
 }
 try:
  os.chdir(outside)
  try:actions[sys.argv[1]]()
  except AssertionError as exc:assert str(exc).startswith('source test attempted checkout runtime storage:')
  else:raise AssertionError('real directory-fd mutation bypassed the storage guard')
  assert (protected/'seed').read_text()=='original fixture'
 finally:
  audit.enabled=False;os.chdir(current);os.close(target);os.close(external)
'''
    result=subprocess.run([sys.executable,'-c',code,operation],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


def test_external_fd_cleanup_of_a_directory_named_data_is_not_a_checkout_write():
    code = r'''
import os,sys,tempfile
from pathlib import Path
from tools.rebuild.source_storage_audit import StorageAudit
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp)/'checkout';(root/'data').mkdir(parents=True)
 outside=Path(temp)/'external';(outside/'data').mkdir(parents=True)
 current=Path.cwd();fd=os.open(outside,os.O_RDONLY|os.O_DIRECTORY)
 audit=StorageAudit(root);sys.addaudithook(audit)
 try:
  os.chdir(root);os.rmdir('data',dir_fd=fd)
  assert (root/'data').is_dir() and not (outside/'data').exists()
  assert audit.violations==[]
 finally:audit.enabled=False;os.chdir(current);os.close(fd)
'''
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


def test_report_pins_the_original_tool_hash_before_pytest_can_clear_main_file(tmp_path):
    tool=Path(__file__).resolve().parents[2]/'tools/rebuild/source_storage_audit.py'
    case=tmp_path/'test_main_file.py'
    case.write_text("def test_clear_main_file():\n import __main__\n del __main__.__file__\n")
    report=tmp_path/'audit.json'
    result=subprocess.run([sys.executable,str(tool),'--report',str(report),str(case),'-q',
        '--basetemp='+str(tmp_path/'own-pytest')],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    import hashlib
    assert json.loads(report.read_text())['source_sha256']==hashlib.sha256(tool.read_bytes()).hexdigest()
