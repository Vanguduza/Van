import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET

BASE = Path('/workspace/.onboarding/browser-parser')
ROOT = BASE / 'postgres-root'
REPO = Path('/workspace/Van')
EVIDENCE = REPO / 'docs/audit/validation'
PREFIX = 'postgres-ledger-real-fixture-2026-10-07'
EVIDENCE.mkdir(parents=True, exist_ok=True)
assert os.geteuid() != 0
work = Path(tempfile.mkdtemp(prefix='postgres-ledger-', dir=BASE))
data, sockets = work / 'data', work / 'socket'
sockets.mkdir(mode=0o700)
bin_dir = ROOT / 'usr/lib/postgresql/17/bin'
env = dict(os.environ)
env['LD_LIBRARY_PATH'] = str(ROOT / 'usr/lib/x86_64-linux-gnu') + (os.pathsep + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
env['PYTHONPATH'] = os.pathsep.join(str(p) for p in (ROOT / 'usr/lib/python3/dist-packages', REPO / 'trading', REPO / 'backend', REPO))
env['PGOPTIONS'] = '-c statement_timeout=15000'
python = '/workspace/.onboarding/van-venv/bin/python'
commands = []
started = False
results = {'schema_version': 1, 'scope': 'ISOLATED_REAL_POSTGRES_LEDGER_FIXTURE', 'recorded_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'fixture_user_uid': os.geteuid(), 'shared_or_production_database_used': False, 'production_source_changed': False, 'registry_or_receipt_hashes_changed': False, 'host_executed': False, 'device_executed': False, 'live_qualified': False}

def run(args, timeout=60, check=True):
    start = time.monotonic()
    result = subprocess.run(args, cwd=REPO, env=env, capture_output=True, text=True, timeout=timeout)
    item = {'args': args, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr, 'elapsed_seconds': time.monotonic()-start}
    commands.append(item)
    if check and result.returncode:
        raise RuntimeError('fixture_command_failed: ' + json.dumps(item))
    return result

try:
    run([str(bin_dir / 'postgres'), '--version'])
    run([str(bin_dir / 'initdb'), '-D', str(data), '-L', str(ROOT / 'usr/share/postgresql/17'), '-A', 'trust', '-U', 'van_fixture', '--encoding=UTF8', '--locale=C', '--no-instructions'])
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    results['measured_free_loopback_port'] = port
    options = f'-h 127.0.0.1 -p {port} -k {sockets} -c shared_buffers=16MB -c max_connections=10'
    run([str(bin_dir / 'pg_ctl'), '-D', str(data), '-l', str(work / 'postgres.log'), '-w', '-t', '15', '-o', options, 'start'], timeout=25)
    started = True
    dsn = f'postgresql://van_fixture@127.0.0.1:{port}/postgres'
    env['VATI_TEST_PG_DSN'] = dsn
    # The deployment reconciler owns the vati schema; the local fixture supplies
    # it explicitly before exercising the current runtime ledger implementation.
    run([python, '-c', 'import os,psycopg; c=psycopg.connect(os.environ["VATI_TEST_PG_DSN"]); c.autocommit=True; c.execute("CREATE SCHEMA vati"); print("psycopg",psycopg.__version__); print("server",c.execute("SELECT version()").fetchone()[0]); print("fixture schemas",c.execute("SELECT nspname FROM pg_namespace WHERE nspname = \'vati\'").fetchall()); c.close()'])
    xml = EVIDENCE / (PREFIX + '.xml')
    test = run([python, '-m', 'pytest', '-q', 'trading/tests/test_infra_live.py::test_postgres_ledger_matches_sqlite_chain_and_detects_tampering', '--junitxml=' + str(xml)], timeout=90, check=False)
    (EVIDENCE / (PREFIX + '.log')).write_text(test.stdout + test.stderr)
    suites = ET.parse(xml).getroot()
    results['junit_counts'] = {key: sum(int(suite.get(key, 0)) for suite in suites.findall('.//testsuite')) for key in ('tests', 'errors', 'failures', 'skipped')}
    results['test_returncode'] = test.returncode
except Exception:
    results['setup_or_execution_error'] = traceback.format_exc()
finally:
    if started:
        stop = run([str(bin_dir / 'pg_ctl'), '-D', str(data), '-m', 'fast', '-w', '-t', '15', 'stop'], timeout=25, check=False)
        results['fixture_stopped'] = stop.returncode == 0
        status = run([str(bin_dir / 'pg_ctl'), '-D', str(data), 'status'], timeout=5, check=False)
        results['post_stop_status_returncode'] = status.returncode
        results['no_fixture_server_running'] = status.returncode == 3
    else:
        results['fixture_stopped'] = True
        results['no_fixture_server_running'] = True
    if (work / 'postgres.log').exists():
        (EVIDENCE / (PREFIX + '-server.log')).write_text((work / 'postgres.log').read_text())
    results['commands'] = commands
    packages = [item for item in json.loads((BASE / 'downloads/postgres-packages.json').read_text()) if item['Package'] != 'postgresql-common']
    packages += [item for item in json.loads((BASE / 'downloads/postgres-optional-packages.json').read_text()) if item['Package'] == 'python3-psycopg']
    results['package_trust'] = {'origin': 'https://deb.debian.org/debian/', 'trusted_archive_keyring': '/usr/share/keyrings/debian-archive-keyring.gpg', 'release_signature_verified': True, 'index_size_and_sha256_match_signed_release': True, 'release_sha256': hashlib.sha256((BASE / 'downloads/InRelease').read_bytes()).hexdigest(), 'index_sha256': hashlib.sha256((BASE / 'downloads/Packages.xz').read_bytes()).hexdigest(), 'packages': packages, 'extraction': 'dpkg-deb -x workspace-only; no package scripts or global installation'}
    results['binary_sha256'] = {name: hashlib.sha256((bin_dir / name).read_bytes()).hexdigest() for name in ('postgres', 'pg_ctl', 'initdb', 'psql')}
    results['test_inputs_sha256'] = {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (REPO / 'trading/tests/test_infra_live.py', REPO / 'trading/vati/core/ledger_pg.py', REPO / 'trading/vati/core/ledger.py', REPO / 'trading/vati/core/events.py', REPO / 'trading/vati/core/canonical.py')}
    results['limits'] = ['Database initialized and used only by current nonroot user in a private workspace fixture.', 'Loopback-only trust authentication is fixture-specific; production authentication, network isolation, runtime grant policy and deployment readiness are not qualified.', 'VATI_TEST_PG_DSN and PGOPTIONS supplied only to fixture subprocess environment; existing deployment settings unused.']
    if results['no_fixture_server_running']:
        shutil.rmtree(work)
        results['temporary_database_removed'] = True
    (EVIDENCE / (PREFIX + '.json')).write_text(json.dumps(results, indent=2) + '\n')
    (EVIDENCE / (PREFIX + '-debian-signatures.txt')).write_text((BASE / 'release-signature-verification.txt').read_text())
print(json.dumps({key: results.get(key) for key in ('test_returncode', 'junit_counts', 'fixture_stopped', 'no_fixture_server_running', 'temporary_database_removed', 'setup_or_execution_error')}, indent=2))
raise SystemExit(0 if results.get('test_returncode') == 0 and results.get('junit_counts', {}).get('skipped') == 0 and results.get('no_fixture_server_running') else 1)
