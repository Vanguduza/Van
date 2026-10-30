"""Real PostgreSQL durable TCA readback and independently connected consumers."""
from test_postgres_ledger_isolation import pg_dsn
from test_tca_exact_consumers import lifecycle_cost_path
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.learning import Environment
from vati.learning.hooks import LearningHooks
from vati.learning.replay import restore_learning_runtime


def test_original_postgres_cost_survives_independent_reconnect_and_cold_replay(pg_dsn):
    owner=PostgresLedger(pg_dsn,ledger_name='exact-tca')
    try:cost,_=lifecycle_cost_path(owner);count=owner.count()
    finally:owner.close()
    reader=PostgresLedger(pg_dsn,ledger_name='exact-tca')
    other=PostgresLedger(pg_dsn,ledger_name='other-account')
    try:
        assert list(reader.iter(EventKind.TCA_RECORD))[0].hash==cost.hash
        hooks=LearningHooks(Environment.DEMO)
        assert restore_learning_runtime(reader,hooks,{}).tca_observations==1
        assert restore_learning_runtime(reader,hooks,{}).tca_observations==1
        assert len(hooks.brokers.profiles[('paper','EURUSD','LONDON')].samples)==1
        assert reader.count()==count and reader.verify_chain()[0]
        assert restore_learning_runtime(other,LearningHooks(Environment.DEMO),{}).tca_observations==0
        assert other.count()==0
    finally:other.close();reader.close()
