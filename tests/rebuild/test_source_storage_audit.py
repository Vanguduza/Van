"""Keep the actual filesystem misuse probes in the documentary CI suite."""
import json
from pathlib import Path
import subprocess
import sys
import pytest


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
