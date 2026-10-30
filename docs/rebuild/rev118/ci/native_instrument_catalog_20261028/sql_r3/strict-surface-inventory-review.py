from pathlib import Path
import ast,json,hashlib,subprocess
root=Path('/workspace/van-review-2026-10-18/publish')
file='backend/tests/test_trading_api.py'
r=json.loads(Path('/workspace/van-native-instrument-catalog-sql-r2-20261028/receipt.json').read_text())
old=subprocess.check_output(['git','show',r['base_head']+':'+file],cwd=root)
new=(root/file).read_bytes()
assert hashlib.sha256(old).hexdigest()==r['source_sha256'][file]
a=ast.parse(old);b=ast.parse(new)
f=next(x for x in b.body if isinstance(x,ast.FunctionDef) and x.name=='test_service_never_exposes_an_order_path')
assertion=next(x for x in f.body if isinstance(x,ast.Assert))
s=assertion.test.comparators[0];assert isinstance(s,ast.Set)
added={'instrument_catalog','native_catalog_ledger_path'}
assert sum(isinstance(x,ast.Constant) and x.value in added for x in s.elts)==2
s.elts=[x for x in s.elts if not isinstance(x,ast.Constant) or x.value not in added]
assert ast.dump(a)==ast.dump(b)
print('Independent AST check: only the two explicit readonly expected members changed; all other test assertions and capability bans intact')
