"""Real secret files and processes; values below are isolated source-test fixtures."""
import multiprocessing
import os
from pathlib import Path

import pytest

from commander.accounts import _write_secrets
from vati.accounts.registry import load_secret_file


def update_worker(path, key, ready, result):
    original_open = os.open
    def rendezvous_before_legacy_truncation(target, flags, *args, **kwargs):
        if Path(target) == Path(path) and flags & os.O_TRUNC:
            ready.wait(timeout=10)
        return original_open(target, flags, *args, **kwargs)
    os.open = rendezvous_before_legacy_truncation
    ready.wait(timeout=10)
    try:
        _write_secrets(Path(path), {key: 'fixture-'+key})
        result.put('saved')
    except Exception as error:
        result.put(type(error).__name__)
    finally:
        os.open = original_open


def test_interrupted_credential_replacement_retains_the_complete_previous_file(tmp_path, monkeypatch):
    path = tmp_path/'credentials.env'; _write_secrets(path, {'OLD': 'fixture-old'})
    before = path.read_bytes()
    def fail(*args):
        raise OSError('induced atomic swap failure')
    monkeypatch.setattr('commander.accounts.os.replace', fail)
    with pytest.raises(OSError, match='swap failure'):
        _write_secrets(path, {'NEW': 'fixture-new'})
    assert path.read_bytes() == before
    assert load_secret_file(str(path)) == {'OLD': 'fixture-old'}
    assert not list(tmp_path.glob('.credentials.env.*.tmp'))


def test_two_processes_merge_credentials_without_dropping_existing_keys(tmp_path):
    path = tmp_path/'credentials.env'; _write_secrets(path, {'OLD': 'fixture-old'})
    context = multiprocessing.get_context('spawn')
    ready = context.Barrier(2); result = context.Queue()
    workers = [context.Process(target=update_worker, args=(str(path), key, ready, result)) for key in ('ONE', 'TWO')]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
            assert worker.exitcode == 0
        assert [result.get(timeout=3) for _ in workers] == ['saved', 'saved']
        assert load_secret_file(str(path)) == {'OLD': 'fixture-old', 'ONE': 'fixture-ONE', 'TWO': 'fixture-TWO'}
        assert path.stat().st_mode & 0o777 == 0o600
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.kill(); worker.join(timeout=3)
        result.close(); result.join_thread()


@pytest.mark.parametrize('value', ['fixture\rINJECT=bad', 'fixture\nINJECT=bad'])
def test_multiline_credentials_are_refused_before_any_write(value, tmp_path):
    path = tmp_path/'credentials.env'; _write_secrets(path, {'OLD': 'fixture-old'})
    before = path.read_bytes()
    with pytest.raises(ValueError, match='single-line'):
        _write_secrets(path, {'NEW': value})
    assert path.read_bytes() == before


def test_non_private_existing_credentials_are_not_read_or_replaced(tmp_path):
    from vati.accounts import AccountRegistryError
    path = tmp_path/'credentials.env'; _write_secrets(path, {'OLD': 'fixture-old'})
    path.chmod(0o644); before = path.read_bytes()
    with pytest.raises(AccountRegistryError, match='0600'):
        _write_secrets(path, {'NEW': 'fixture-new'})
    assert path.read_bytes() == before


def test_a_secret_destination_symlink_cannot_redirect_a_rotation(tmp_path):
    target = tmp_path/'target.env'; _write_secrets(target, {'OLD': 'fixture-old'})
    alias = tmp_path/'alias.env'; alias.symlink_to(target)
    before = target.read_bytes()
    with pytest.raises(ValueError, match='symbolic link'):
        _write_secrets(alias, {'NEW': 'fixture-new'})
    assert target.read_bytes() == before and alias.is_symlink()


def test_real_handlers_serialize_rotation_with_unlink_without_orphaning_secret_files(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from commander.accounts import AccountControlSettings, build_account_handlers
    from vati.accounts import AccountRegistry
    import commander.accounts as module
    registry = tmp_path/'accounts.json'; path = tmp_path/'secrets'/'deriv_demo.env'
    handlers = build_account_handlers(AccountControlSettings(str(registry), str(path.parent)))
    handlers['account_upsert']({'alias': 'deriv_demo', 'broker': 'DERIV'})
    handlers['account_credentials']({'alias': 'deriv_demo', 'secrets': {'DERIV_API_TOKEN': 'fixture-old'}})
    started, release, removed = Event(), Event(), Event()
    original_write = module._write_secrets
    def paused_write(destination, values, **kwargs):
        if values.get('DERIV_API_TOKEN') == 'fixture-new':
            started.set()
            assert release.wait(timeout=5)
        return original_write(destination, values, **kwargs)
    monkeypatch.setattr(module, '_write_secrets', paused_write)
    def unlink():
        try:
            return handlers['account_remove']({'alias': 'deriv_demo'})
        finally:
            removed.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        rotation = pool.submit(handlers['account_credentials'],
            {'alias': 'deriv_demo', 'secrets': {'DERIV_API_TOKEN': 'fixture-new'}})
        assert started.wait(timeout=3)
        removal = pool.submit(unlink)
        try:
            assert not removed.wait(timeout=0.25), 'unlink ran through an in-flight credential mutation'
        finally:
            release.set()
        assert rotation.result(timeout=5)['stored_keys'] == ['DERIV_API_TOKEN']
        assert removal.result(timeout=5)['removed']
    assert not path.exists() and 'deriv_demo' not in AccountRegistry(registry).accounts
