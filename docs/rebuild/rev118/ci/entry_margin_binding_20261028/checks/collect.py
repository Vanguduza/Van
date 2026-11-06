import os,subprocess,json,pathlib
root=pathlib.Path("/workspace/van-review-2026-10-18/publish")
env=dict(os.environ,PYTHONPATH=":".join(str(root/p) for p in ["backend","backend/tests","trading","trading/tests","."]),DIAL_REPO="/workspace/van-review-2026-10-18/dial-development-system")
files=json.loads(pathlib.Path("/workspace/van-entry-margin-binding-full-targets-20261028.json").read_text())
raise SystemExit(subprocess.run(["/workspace/van-backend-venv-20261025/bin/python","-m","pytest",*files,"--collect-only","-q"],cwd=root,env=env).returncode)
