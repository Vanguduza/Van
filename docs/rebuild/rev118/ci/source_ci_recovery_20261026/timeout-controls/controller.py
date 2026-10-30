from pathlib import Path
import subprocess,os,json,tempfile,hashlib
out=Path('/workspace/van-ci-timeout-controls-20261026');out.mkdir()
with tempfile.TemporaryDirectory(prefix='van-timeout-control-') as directory:
 root=Path(directory);script=root/'owned_fixture.py';marker=root/'cleanup.json'
 script.write_text("""import subprocess,time,json,os
from pathlib import Path
child=subprocess.Popen(['python3','-c','import signal,time;signal.signal(signal.SIGINT,signal.SIG_IGN);time.sleep(60)'])
try:time.sleep(60)
finally:
 child.terminate();child.wait(timeout=5)
 try:os.waitpid(child.pid,os.WNOHANG)
 except ChildProcessError:reaped=True
 else:reaped=False
 Path('cleanup.json').write_text(json.dumps({'owned_child_reaped':reaped,'exit':child.returncode}))
""")
 def pipeline(command,label):
  with (out/(label+'.log')).open('wb') as log:
   p=subprocess.run(['bash','-c','set -o pipefail\n'+command+' 2>&1 | tee pipeline.log'],cwd=root,stdout=log,stderr=subprocess.STDOUT,timeout=15)
  return p.returncode
 positive=pipeline("python3 -c 'raise SystemExit(0)'",'positive')
 failure=pipeline("python3 -c 'raise SystemExit(1)'",'failure')
 timeout=pipeline('timeout --signal=INT --kill-after=1s 1s python3 owned_fixture.py','timeout')
 cleanup=json.loads(marker.read_text())
 assert positive==0 and failure==1 and timeout==124 and cleanup['owned_child_reaped'] is True
 receipt={'actual_positive_exit':positive,'actual_failure_preserved':failure,'actual_timeout_exit':timeout,'actual_owned_child_cleanup':cleanup,'scope':'Synthetic shell/timeout cleanup control, not product-test acceptance'}
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt)

