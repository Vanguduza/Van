"""Actual production SQL history guard, with no files, keys or credential work."""
import sqlite3
import pytest
from commander.account_cleanup import UnlinkRecoveryBook
from commander.account_effects import AccountEffectUnknown


def owner(namespace):
    # This isolated SQL unit enters no lifecycle/key/authority path.
    book=object.__new__(UnlinkRecoveryBook)
    book.namespace=namespace;book.pg=False
    return book


@pytest.mark.parametrize('namespace',['owned',"owned' OR 1=1 --"])
def test_only_current_namespace_history_blocks_missing_key_initialization(namespace):
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE account_unlink_facts(namespace TEXT NOT NULL, operation_id TEXT NOT NULL, seq BIGINT NOT NULL, body_json TEXT NOT NULL, fact_ref TEXT NOT NULL, PRIMARY KEY(namespace,operation_id,seq), UNIQUE(namespace,fact_ref))')
        current=owner(namespace)
        assert current._require_empty_namespace(db) is None
        foreign=('other','retained_original',1,'nonsensitive-metadata','foreign-fact')
        db.execute('INSERT INTO account_unlink_facts VALUES(?,?,?,?,?)',foreign)
        before=db.execute('SELECT * FROM account_unlink_facts').fetchall()
        assert current._require_empty_namespace(db) is None
        assert db.execute('SELECT * FROM account_unlink_facts').fetchall()==before
        own=(namespace,'original_operation',1,'nonsensitive-metadata','owned-fact')
        db.execute('INSERT INTO account_unlink_facts VALUES(?,?,?,?,?)',own)
        before=db.execute('SELECT * FROM account_unlink_facts ORDER BY namespace').fetchall()
        with pytest.raises(AccountEffectUnknown):current._require_empty_namespace(db)
        assert db.execute('SELECT * FROM account_unlink_facts ORDER BY namespace').fetchall()==before
        # Both owners still see only their own original rows, never a grant to
        # read/rewrite another namespace or replace a key over their history.
        with pytest.raises(AccountEffectUnknown):owner('other')._require_empty_namespace(db)
