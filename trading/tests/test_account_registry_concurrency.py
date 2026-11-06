"""Independent registry writers must merge disjoint edits and refuse stale replacements."""
from dataclasses import replace
import multiprocessing

import pytest

from vati.accounts import Account, AccountRegistry, AccountRegistryError


def paper(alias='paper_demo', label='Original'):
    return Account(alias=alias, broker='PAPER', mode='DEMO_TRADER', currency='USD', label=label)


def add_stale_worker(path, alias, ready, results):
    registry = AccountRegistry(path)
    ready.wait(timeout=10)
    try:
        registry.add(paper(alias))
        results.put((alias, 'saved'))
    except Exception as error:
        results.put((alias, type(error).__name__))


def test_two_real_processes_do_not_drop_disjoint_account_additions(tmp_path):
    path = str(tmp_path/'accounts.json')
    context = multiprocessing.get_context('spawn')
    ready = context.Barrier(2); results = context.Queue()
    workers = [context.Process(target=add_stale_worker, args=(path, alias, ready, results))
               for alias in ('paper_one', 'paper_two')]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
            assert worker.exitcode == 0
        assert sorted(results.get(timeout=3) for _ in workers) == [('paper_one', 'saved'), ('paper_two', 'saved')]
        assert set(AccountRegistry(path).accounts) == {'paper_one', 'paper_two'}
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.kill(); worker.join(timeout=3)
        results.close(); results.join_thread()


def test_stale_instance_merges_a_disjoint_replace_and_add(tmp_path):
    path = tmp_path/'accounts.json'
    one = AccountRegistry(path); one.add(paper())
    stale = AccountRegistry(path)
    one.replace(paper(label='New label'))
    stale.add(paper('paper_other'))
    fresh = AccountRegistry(path)
    assert fresh.get('paper_demo').label == 'New label'
    assert set(fresh.accounts) == {'paper_demo', 'paper_other'}


@pytest.mark.parametrize('operation', ['replace', 'remove'])
def test_same_account_changed_since_read_refuses_instead_of_overwriting(operation, tmp_path):
    path = tmp_path/'accounts.json'
    one = AccountRegistry(path); one.add(paper())
    stale = AccountRegistry(path)
    one.replace(paper(label='New label'))
    with pytest.raises(AccountRegistryError, match='changed|conflict|reload'):
        stale.replace(paper(label='Stale label')) if operation == 'replace' else stale.remove('paper_demo')
    assert AccountRegistry(path).get('paper_demo').label == 'New label'


def test_an_unrelated_account_cannot_be_lost_by_a_stale_removal(tmp_path):
    path = tmp_path/'accounts.json'
    one = AccountRegistry(path); one.add(paper())
    stale = AccountRegistry(path)
    one.add(paper('paper_other'))
    stale.remove('paper_demo')
    assert set(AccountRegistry(path).accounts) == {'paper_other'}


def test_an_account_created_after_read_is_not_silently_replaced_by_add(tmp_path):
    path = tmp_path/'accounts.json'
    one, stale = AccountRegistry(path), AccountRegistry(path)
    one.add(paper(label='Persisted'))
    with pytest.raises(AccountRegistryError, match='already registered'):
        stale.add(paper(label='Stale add'))
    assert AccountRegistry(path).get('paper_demo').label == 'Persisted'


def test_direct_save_cannot_bypass_the_stale_registry_check(tmp_path):
    path = tmp_path/'accounts.json'
    one = AccountRegistry(path); one.add(paper())
    stale = AccountRegistry(path)
    one.add(paper('paper_other'))
    with pytest.raises(AccountRegistryError, match='changed'):
        stale.save()
    assert set(AccountRegistry(path).accounts) == {'paper_demo', 'paper_other'}


def test_corrupt_persisted_state_is_not_replaced_by_a_stale_writers_cache(tmp_path):
    path = tmp_path/'accounts.json'; registry = AccountRegistry(path); registry.add(paper())
    path.write_text('{induced incomplete write')
    with pytest.raises(AccountRegistryError, match='safely'):
        registry.add(paper('paper_other'))
    assert path.read_text() == '{induced incomplete write'
    assert set(registry.accounts) == {'paper_demo'}


@pytest.mark.parametrize('field', ['demo', 'enabled'])
@pytest.mark.parametrize('value', ['false', 'true', 0, 1, None])
def test_ambiguous_identity_flags_cannot_be_persisted(field, value, tmp_path):
    registry = AccountRegistry(tmp_path/'accounts.json')
    with pytest.raises(AccountRegistryError, match='booleans'):
        registry.add(replace(paper(), **{field: value}))
    assert not registry.path.exists()
