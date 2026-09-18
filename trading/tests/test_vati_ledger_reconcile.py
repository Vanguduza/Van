import importlib.util
import pathlib

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "deploy/van-trading-core/supabase/reconcile_vati_ledger.py"

def load_module():
    spec = importlib.util.spec_from_file_location("reconcile_vati_ledger", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

def test_reconcile_sql_is_idempotent_and_escapes_password():
    module = load_module()
    template = module.ROLE_STMT + "\nCREATE SCHEMA IF NOT EXISTS vati AUTHORIZATION vati;\n"
    sql = module.build_sql(template, "safe'password-value")
    assert module.ROLE_STMT not in sql
    assert "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vati')" in sql
    assert "ALTER ROLE vati WITH LOGIN PASSWORD 'safe''password-value'" in sql
    assert "NOSUPERUSER" not in sql.replace(module.ROLE_STMT, "")
    assert "CREATE SCHEMA IF NOT EXISTS vati AUTHORIZATION vati" in sql

def test_reconcile_requires_canonical_role_statement():
    module = load_module()
    try:
        module.build_sql("SELECT 1;", "x" * 32)
    except RuntimeError as exc:
        assert "canonical VATI role statement missing" in str(exc)
    else:
        raise AssertionError("missing canonical role statement must fail closed")

def test_update_core_env_preserves_mode_and_encodes_password(tmp_path):
    module = load_module()
    target = tmp_path / "core.env"
    target.write_text("OTHER=1\nVAN_COMMANDER_LEDGER=old\n")
    target.chmod(0o640)
    module.update_core_env(target, "a/b:c@d")
    text = target.read_text()
    assert "OTHER=1" in text
    assert "VAN_COMMANDER_LEDGER=postgres://vati:a%2Fb%3Ac%40d@127.0.0.1:5432/postgres" in text
    assert (target.stat().st_mode & 0o777) == 0o640

def test_reconcile_uses_supabase_admin_boundary():
    module = load_module()
    assert module.ADMIN_ROLE == "supabase_admin"

def test_runtime_ledger_never_requires_database_create_privilege():
    from vati.core import ledger_pg
    assert "CREATE SCHEMA" not in ledger_pg.SCHEMA.upper()
