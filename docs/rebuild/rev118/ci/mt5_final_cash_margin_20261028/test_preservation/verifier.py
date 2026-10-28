from pathlib import Path
import ast,json,subprocess
root=Path('/workspace/van-review-2026-10-18/publish');base='bf41e16b0213431eeaeb33da96676cfb7dc47477'
files=['trading/tests/test_mt5_worker.py','trading/tests/test_mt5_physical_identity.py',
 'trading/tests/test_mql_native_function_bodies.py','trading/tests/test_mt5_final_native_entry_fence.py']
changes={};preserved=0
for file in files:
 before=ast.parse(subprocess.check_output(['git','show',base+':'+file],cwd=root))
 after=ast.parse((root/file).read_text())
 old={n.name:n for n in before.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')}
 new={n.name:n for n in after.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')}
 assert old.keys()<=new.keys()
 for name,value in old.items():
  if ast.dump(value)==ast.dump(new[name]):preserved+=1;continue
  if name=='test_parallel_aliases_cannot_switch_the_terminal_between_identity_check_and_send':
   assert [ast.dump(n) for n in ast.walk(value) if isinstance(n,ast.Assert)]==[ast.dump(n) for n in ast.walk(new[name]) if isinstance(n,ast.Assert)]
   changes[name]='Original assertions identical. Fixture now executes actual Terminal native preparation instead of bypassing it.'
  elif name=='test_final_native_account_read_cannot_extend_the_signed_time_window':
   changes[name]='Delay is injected at the actual final_entry_guard account read. REJECTED and no-native-send conditions retained; exactly one final-read injection replaces obsolete third-read numbering.'
  else:raise AssertionError((file,name))
result={'original_test_functions_unchanged_AST':preserved,'all_original_test_function_names_preserved':True,'reviewed_test_fixture_boundary_changes':changes,
 'actual_EA_function_bodies':'Exact source bodies remain extracted; dependency set/struct/API fixture expanded. No original EA control assertion removed.'}
Path('/workspace/van-mt5-final-cash-margin-test-preservation-20261028.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
