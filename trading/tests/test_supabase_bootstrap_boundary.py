import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
RECOVERY = ROOT / "deploy/van-trading-core/supabase/recover_donor_migrations.py"
OVERRIDE = ROOT / "deploy/van-trading-core/supabase/docker-compose.override.yml"
BOOTSTRAP = ROOT / "deploy/van-trading-core/bootstrap.sh"

def load_recovery():
    spec = importlib.util.spec_from_file_location("recover_donor_migrations", RECOVERY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

def test_vati_sql_is_not_in_supabase_donor_init_chain():
    text = OVERRIDE.read_text()
    assert "99-vati-ledger.sql" not in text
    assert "01_vati_ledger.sql:" not in text

def test_bootstrap_recovers_donor_before_vati_reconcile():
    text = BOOTSTRAP.read_text()
    recover = text.index("recover_donor_migrations.py")
    reconcile = text.index("reconcile_vati_ledger.py", recover)
    assert recover < reconcile

def test_recovery_classification_is_fail_closed():
    m = load_recovery()
    base = {
        "supabase_db": False,
        "graphql_public": False,
        "auth_uid_owner": "postgres",
        "auth_role_owner": "postgres",
        "supabase_admin_super": True,
    }
    assert m.classify(base) == "interrupted_before_donor_migrations"
    complete = dict(base, supabase_db=True, graphql_public=True,
                    auth_uid_owner="supabase_auth_admin",
                    auth_role_owner="supabase_auth_admin")
    assert m.classify(complete) == "complete"
    ambiguous = dict(base, graphql_public=True)
    assert m.classify(ambiguous) == "ambiguous_partial"
