import pathlib,os,subprocess
root=pathlib.Path("/workspace/van-review-2026-10-18/publish")
env=dict(os.environ,PYTHONPATH=":".join(str(root/p) for p in ["backend","backend/tests","trading","trading/tests","."]),DIAL_REPO="/workspace/van-review-2026-10-18/dial-development-system")
files=pathlib.Path("/workspace/van-native-close-movement-consumers-sql-r1-20261028/targets.txt").read_text().splitlines()
raise SystemExit(subprocess.run(["/workspace/van-backend-venv-20261025/bin/python","-m","pytest",*files,"--collect-only","-q"],cwd=root,env=env).returncode)
