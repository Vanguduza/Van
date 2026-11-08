"""Migration IDs are historical evidence, never instructions to repair a ledger."""
import copy
from datetime import datetime,timezone,timedelta
import hashlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import gtr_history_reconcile as g

NOW=datetime(2026,11,8,22,tzinfo=timezone.utc)
N='a'*32
V='20261102080000'
H='20260904114922'

def catalog():
    def row(version,family,name):return {'version':version,'name':name,'family':family,'path':family+'/'+version+'_'+name+'.sql','source_file_sha256':'1'*64,'bytes':100}
    return {'kind':'GTR_PINNED_SOURCE_HISTORY_CATALOG_NOT_HOSTED_OBSERVATION','commit':g.GTR_COMMIT,'manifest_sha256':g.MANIFEST_SHA,
        'baseline_version':V,'histories':{'legacy':[row(H,'legacy','foundation')],
        'hosted_archive':[row(H,'hosted_archive','foundation')],
        'active':[row(V,'active','baseline'),row('20261102085000','active','forward')]}}

def snapshot(rows=None):
    rows=rows if rows is not None else [{'version':H,'name':'foundation','statement_count':1,'statements_sha256':'2'*64}]
    return {'schema_version':1,'kind':'GTR_READ_ONLY_LEDGER_SNAPSHOT_V1','capture_nonce':N,
        'declared_project_ref':g.ACTIVE_PROJECT,'captured_at':(NOW-timedelta(minutes=1)).isoformat(),
        'server_version_num':170006,'database_name':'postgres','sql_role':'readonly_observer',
        'read_only':True,'isolation':'repeatable read','fingerprint_format':g.FORMAT,
        'row_count':len(rows),'truncated':False,'rows':rows}

class HistoryTests(unittest.TestCase):
    def review(self,s=None,previous=None):return g.compare(catalog(),s or snapshot(),nonce=N,now=NOW,previous=previous)
    def test_archive_versions_are_known_not_missing_active_sql(self):
        r=self.review();self.assertEqual(r['unknown_versions'],[])
        self.assertEqual(r['classified_versions'][0]['source_families'],['hosted_archive','legacy'])
        self.assertEqual(r['ledger_mode'],'HISTORICAL_OR_OTHER_LEDGER_DO_NOT_REPLAY_BASELINE')
        self.assertFalse(r['may_apply_baseline']);self.assertFalse(r['may_repair_history'])
    def test_baseline_marker_does_not_prove_schema(self):
        s=snapshot([{'version':V,'name':'baseline','statement_count':1,'statements_sha256':'3'*64}])
        r=self.review(s);self.assertEqual(r['ledger_mode'],'BASELINE_MARKER_RECORDED_NOT_SCHEMA_PROOF')
        self.assertIn('LEDGER_MATCH_IS_NOT_SCHEMA_OR_DATA_EQUIVALENCE',r['blockers'])
    def test_unknown_version_not_automatically_applied(self):
        s=snapshot();s['rows'][0]['version']='20261101000000'
        r=self.review(s);self.assertEqual(r['unknown_versions'],['20261101000000']);self.assertFalse(r['may_cutover'])
    def test_empty_ledger_is_not_fresh_database_proof(self):
        r=self.review(snapshot([]));self.assertEqual(r['ledger_mode'],'EMPTY_LEDGER_REQUIRES_INVENTORY');self.assertFalse(r['may_apply_baseline'])
    def test_name_drift_reported_without_emitting_source_sql(self):
        s=snapshot();s['rows'][0]['name']='different'
        r=self.review(s);self.assertEqual(r['source_name_drift'],[H]);self.assertNotIn('different',json.dumps(r))
    def test_null_name_remains_unknown_without_false_mismatch(self):
        s=snapshot();s['rows'][0]['name']=None
        self.assertEqual(self.review(s)['source_name_drift'],[])
    def test_null_statements_not_equivalent_to_empty_array(self):
        s=snapshot();s['rows'][0].update(statement_count=None,statements_sha256=None)
        r=self.review(s);self.assertIn('MISSING_STATEMENT_FINGERPRINTS',r['blockers'])
        s['rows'][0].update(statement_count=0,statements_sha256='3'*64)
        self.assertNotIn('MISSING_STATEMENT_FINGERPRINTS',self.review(s)['blockers'])
    def test_old_and_future_captures_blocked(self):
        for delta,block in [(timedelta(hours=-2),'CAPTURE_OLDER_THAN_ONE_HOUR'),(timedelta(seconds=1),'CAPTURE_TIME_IS_IN_THE_FUTURE')]:
            s=snapshot();s['captured_at']=(NOW+delta).isoformat()
            self.assertIn(block,self.review(s)['blockers'])
    def test_naive_datetime_refused(self):
        s=snapshot();s['captured_at']='2026-11-08T22:00:00'
        with self.assertRaises(ValueError):self.review(s)
        with self.assertRaises(ValueError):g.compare(catalog(),snapshot(),nonce=N,now=datetime(2026,11,8))
    def test_opaque_version_not_calendar_validation(self):
        s=snapshot();s['rows'][0]['version']='20260725270000'
        self.assertEqual(self.review(s)['unknown_versions'],['20260725270000'])
    def test_duplicate_versions_refused(self):
        s=snapshot();s['rows']*=2;s['row_count']=2
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):self.review(s)
    def test_retired_project_refused(self):
        s=snapshot();s['declared_project_ref']=g.RETIRED_PROJECT
        with self.assertRaisesRegex(ValueError,'ACTIVE_PROJECT'):self.review(s)
    def test_other_project_refused(self):
        s=snapshot();s['declared_project_ref']='abcdefghijklmnopqrst'
        with self.assertRaises(ValueError):self.review(s)
    def test_unknown_fields_refused(self):
        s=snapshot();s['rows'][0]['statements']=['RAW SQL SHOULD NOT ENTER']
        with self.assertRaisesRegex(ValueError,'EXACT_FIELDS'):self.review(s)
        s=snapshot();s['authority']='root'
        with self.assertRaises(ValueError):self.review(s)
    def test_truncated_or_count_mismatch_refused(self):
        for field,value in [('truncated',True),('row_count',2),('row_count',True),('truncated',0)]:
            s=snapshot();s[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.review(s)
    def test_non_readonly_or_wrong_isolation_refused(self):
        for field,value in [('read_only',False),('read_only',1),('isolation','read committed')]:
            s=snapshot();s[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.review(s)
    def test_mixed_hash_formats_refused(self):
        s=snapshot();s['fingerprint_format']='RAW_SQL_FILE_SHA256'
        with self.assertRaisesRegex(ValueError,'INCOMPARABLE'):self.review(s)
    def test_hash_missing_but_count_present_refused(self):
        s=snapshot();s['rows'][0]['statements_sha256']=None
        with self.assertRaises(ValueError):self.review(s)
    def test_noncanonical_statement_hash_refused(self):
        for value in ('A'*64,'bad','1'*63):
            s=snapshot();s['rows'][0]['statements_sha256']=value
            with self.assertRaises(ValueError):self.review(s)
    def test_bool_schema_version_and_statement_count_refused(self):
        s=snapshot();s['schema_version']=True
        with self.assertRaises(ValueError):self.review(s)
        s=snapshot();s['rows'][0]['statement_count']=True
        with self.assertRaises(ValueError):self.review(s)
    def test_capture_correlation_refused(self):
        s=snapshot();s['capture_nonce']='b'*32
        with self.assertRaisesRegex(ValueError,'CORRELATION'):self.review(s)
    def test_capture_nonce_sql_injection_refused(self):
        for nonce in ('x; DROP SCHEMA public','a'*31,'A'*32,"a'*32",None):
            with self.subTest(nonce=nonce),self.assertRaises(ValueError):g.capture_sql(nonce)
    def test_capture_is_read_only_bounded_one_result(self):
        sql=g.capture_sql(N)
        self.assertIn('REPEATABLE READ READ ONLY',sql);self.assertIn("lock_timeout='2s'",sql)
        self.assertIn('LIMIT 10001',sql);self.assertIn('ROLLBACK;',sql)
        self.assertNotIn('CREATE ',sql);self.assertNotIn('UPDATE ',sql);self.assertNotIn('DELETE ',sql)
        self.assertNotIn('INSERT ',sql);self.assertNotIn('pg_authid',sql)
    def test_stable_canonical_encoding(self):
        self.assertEqual(g.canonical({'b':1,'a':2}),g.canonical({'a':2,'b':1}))
        with self.assertRaises(ValueError):g.canonical({'x':float('nan')})
    def test_removed_history_detected(self):
        old=snapshot();old['captured_at']=(NOW-timedelta(minutes=2)).isoformat()
        r=self.review(snapshot([]),previous=old)
        self.assertEqual(r['previous_capture_diff']['removed'],[H]);self.assertIn('PREVIOUS_LEDGER_REMOVED_OR_CHANGED',r['blockers'])
    def test_same_version_changed_statements_detected(self):
        old=snapshot();old['captured_at']=(NOW-timedelta(minutes=2)).isoformat()
        s=snapshot();s['rows'][0]['statements_sha256']='5'*64
        r=self.review(s,previous=old)
        self.assertEqual(r['previous_capture_diff']['changed'],[H])
    def test_identical_statements_never_become_schema_proof(self):
        old=snapshot();old['captured_at']=(NOW-timedelta(minutes=2)).isoformat()
        r=self.review(previous=old)
        self.assertEqual(r['previous_capture_diff']['same'],[H]);self.assertFalse(r['current_hosted_state_independently_verified'])
    def test_missing_previous_fingerprint_is_incomparable(self):
        old=snapshot();old['captured_at']=(NOW-timedelta(minutes=2)).isoformat()
        old['rows'][0].update(statement_count=None,statements_sha256=None)
        self.assertEqual(self.review(previous=old)['previous_capture_diff']['incomparable'],[H])
    def test_previous_db_or_version_change_refused(self):
        for field,value in [('database_name','elsewhere'),('server_version_num',180001)]:
            old=snapshot();old['captured_at']=(NOW-timedelta(minutes=2)).isoformat();old[field]=value
            with self.assertRaises(ValueError):self.review(previous=old)
    def test_previous_capture_must_precede_current(self):
        with self.assertRaises(ValueError):self.review(previous=snapshot())
    def test_source_pin_changed_refused(self):
        c=catalog();c['commit']='0'*40
        with self.assertRaises(ValueError):g.compare(c,snapshot(),nonce=N,now=NOW)
    def test_source_read_no_symlinks_or_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);(root/'file.sql').write_text('SELECT 1;')
            expected=g.digest(b'SELECT 1;')
            self.assertEqual(g.public_source(root,'file.sql',expected),b'SELECT 1;')
            (root/'link.sql').symlink_to(root/'file.sql')
            with self.assertRaises(OSError):g.public_source(root,'link.sql',expected)
            for path in ('../file.sql','/file.sql','./file.sql','x//file.sql'):
                with self.assertRaises(ValueError):g.public_source(root,path,expected)
    def test_source_hash_and_size_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);(root/'file.sql').write_text('SELECT 1;')
            with self.assertRaises(ValueError):g.public_source(root,'file.sql','0'*64)
            with self.assertRaises(ValueError):g.public_source(root,'file.sql',g.digest(b'SELECT 1;'),max_bytes=2)
    def test_source_parent_symlink_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);d=root/'actual';d.mkdir();(d/'file.sql').write_text('x')
            (root/'shortcut').symlink_to(d,target_is_directory=True)
            with self.assertRaises(OSError):g.public_source(root,'shortcut/file.sql',g.digest(b'x'))
    def test_cli_missing_source_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as td:
            out=pathlib.Path(td)/'out'
            with redirect_stdout(io.StringIO()):rc=g.main(['--source-root',td,'--capture-nonce',N,'--out',str(out)])
            self.assertEqual(rc,2);self.assertFalse(out.exists())
    def test_cli_previous_without_current_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with redirect_stdout(io.StringIO()):rc=g.main(['--source-root',td,'--capture-nonce',N,'--previous',td+'/none','--out',td+'/out'])
            self.assertEqual(rc,2)
    def test_snapshot_metadata_injection_refused(self):
        for field,value in [('database_name','postgres\nsecret'),('sql_role','postgres;select'),('server_version_num',True)]:
            s=snapshot();s[field]=value
            with self.assertRaises(ValueError):self.review(s)
    def test_ordering_is_deterministic(self):
        s=snapshot([{'version':H,'name':'foundation','statement_count':1,'statements_sha256':'2'*64},
                    {'version':V,'name':'baseline','statement_count':1,'statements_sha256':'3'*64}])
        result=self.review(s);s['rows'].reverse();other=self.review(s)
        self.assertEqual(result['classified_versions'],other['classified_versions'])
        self.assertNotEqual(result['snapshot_sha256'],other['snapshot_sha256'])

    def test_private_input_reads_large_complete_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/'snapshot.json';d={'synthetic':'x'*70000};p.write_text(json.dumps(d));p.chmod(0o600)
            self.assertEqual(g.load_snapshot_file(p),d)
    def test_private_input_refuses_public_mode_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/'snapshot.json';p.write_text('{}');p.chmod(0o644)
            with self.assertRaises(ValueError):g.load_snapshot_file(p)
            p.chmod(0o600);p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):g.load_snapshot_file(p)
    def test_private_input_refuses_symlink_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);p=root/'snapshot.json';p.write_text('{}');p.chmod(0o600)
            link=root/'link.json';link.symlink_to(p)
            with self.assertRaises(OSError):g.load_snapshot_file(link)
            p.write_text('{"n":NaN}')
            with self.assertRaises(ValueError):g.load_snapshot_file(p)
    def test_private_input_refuses_oversize_before_parse(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/'snapshot.json';p.write_text(' '*1025);p.chmod(0o600)
            with patch.object(g,'MAX_INPUT',1024),self.assertRaises(ValueError):g.load_snapshot_file(p)

    def test_same_version_distinct_source_bytes_not_collapsed(self):
        c=catalog();c['histories']['legacy'][0]['source_file_sha256']='8'*64
        r=g.compare(c,snapshot(),nonce=N,now=NOW)
        self.assertEqual(r['source_content_ambiguous_versions'],[H])
        self.assertIn('SAME_VERSION_HAS_DISTINCT_SOURCE_BYTES_SEMANTICS_UNPROVEN',r['blockers'])
        self.assertFalse(r['may_repair_history'])
    def test_source_file_hash_not_compared_as_ledger_array_hash(self):
        s=snapshot();s['rows'][0]['statements_sha256']='1'*64
        r=self.review(s)
        self.assertEqual(r['classified_versions'][0]['classification'],'KNOWN_VERSION_CONTENT_UNVERIFIED')
        self.assertIn('SOURCE_SQL_FILE_HASH_IS_NOT_LEDGER_STATEMENT_ARRAY_HASH',r['blockers'])

    def test_capture_refuses_views_rls_and_column_shape_drift(self):
        sql=g.capture_sql(N)
        self.assertIn('IN ACCESS SHARE MODE',sql)
        self.assertIn("relkind='r'",sql)
        self.assertIn('NOT relrowsecurity AND NOT relforcerowsecurity',sql)
        self.assertIn("atttypid='text[]'::regtype",sql)
        self.assertLess(sql.index('LOCK TABLE ONLY'),sql.index('DO $ledger_guard$'))
        self.assertLess(sql.index('DO $ledger_guard$'),sql.index('WITH ledger AS MATERIALIZED'))

if __name__=='__main__':unittest.main()
