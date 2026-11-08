-- READ ONLY metadata capture. Run with psql -X -qAt -v ON_ERROR_STOP=1.
-- The declared project ref is an ASSERTION, not observed connection identity.
-- One transaction and one result: no SQL statements, rows or secrets returned.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='10s';
SET LOCAL lock_timeout='2s';
SET LOCAL idle_in_transaction_session_timeout='15s';
SET LOCAL search_path=pg_catalog;
-- Hold a non-exclusive schema-stability lock while proving this is the
-- ordinary ledger table, not a view/foreign table or row-filtered relation.
LOCK TABLE ONLY supabase_migrations.schema_migrations IN ACCESS SHARE MODE;
DO $ledger_guard$ DECLARE target oid := 'supabase_migrations.schema_migrations'::regclass;
BEGIN
  IF NOT EXISTS (SELECT FROM pg_class WHERE oid=target AND relkind='r'
                 AND NOT relrowsecurity AND NOT relforcerowsecurity)
     OR (SELECT count(*) FROM pg_attribute WHERE attrelid=target AND NOT attisdropped
         AND ((attname IN ('version','name') AND atttypid='text'::regtype)
           OR (attname='statements' AND atttypid='text[]'::regtype)))<>3
  THEN RAISE EXCEPTION 'LEDGER_BASE_TABLE_WITHOUT_RLS_AND_TYPED_COLUMNS_REQUIRED'; END IF;
END $ledger_guard$;
WITH ledger AS MATERIALIZED (
  SELECT version,name,statements FROM supabase_migrations.schema_migrations
  ORDER BY version COLLATE "C" LIMIT 10001
), observed AS (
  SELECT version,name,
    CASE WHEN statements IS NULL THEN NULL ELSE cardinality(statements) END AS statement_count,
    CASE WHEN statements IS NULL THEN NULL ELSE encode(sha256(convert_to(to_jsonb(statements)::text,'UTF8')),'hex') END AS statements_sha256
  FROM ledger
)
SELECT jsonb_build_object(
  'schema_version',1,'kind','GTR_READ_ONLY_LEDGER_SNAPSHOT_V1',
  'capture_nonce','6e358ef794474241869e9fe4968c45c1','declared_project_ref','bicyjghgdnzlnjqxzoud',
  'captured_at',transaction_timestamp(),'server_version_num',current_setting('server_version_num')::integer,
  'database_name',current_database(),'sql_role',current_user,
  'read_only',current_setting('transaction_read_only')='on',
  'isolation',current_setting('transaction_isolation'),
  'fingerprint_format','POSTGRESQL_JSONB_STATEMENT_ARRAY_SHA256_V1',
  'row_count',(SELECT count(*) FROM observed),
  'truncated',(SELECT count(*)>10000 FROM observed),
  'rows',COALESCE((SELECT jsonb_agg(jsonb_build_object('version',version,'name',name,
     'statement_count',statement_count,'statements_sha256',statements_sha256) ORDER BY version COLLATE "C") FROM observed),'[]'::jsonb));
ROLLBACK;
