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
    assert "CREATE SCHEMA IF NOT EXISTS vati AUTHORIZATION vati" in sql

def test_reconcile_requires_canonical_role_statement():
    module = load_module()
    try:
        module.build_sql("SELECT 1;", "x" * 32)
    except RuntimeError as exc:
        assert "canonical VATI role statement missing" in str(exc)
    else:
        raise AssertionError("missing canonical role statement must fail closed")
