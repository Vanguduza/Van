"""Opaque native account configuration version; never reads secret values."""
from dataclasses import asdict
from pathlib import Path

from vati.accounts.registry import AccountRegistry, AccountRegistryError
from vati.core.canonical import canonical_hash


def resource_snapshot(registry: AccountRegistry, alias: str) -> dict:
    with registry.operation_lock(alias), registry._mutation_lock():
        current = AccountRegistry(registry.path)
        account = current.accounts.get(alias)
        credential_generation = None
        if account and account.credential_ref.secrets_file:
            path = Path(account.credential_ref.secrets_file)
            if path.is_symlink():
                raise AccountRegistryError("credential reference must not be a symbolic link")
            try:
                stat = path.stat()
                credential_generation = [stat.st_dev, stat.st_ino, stat.st_size,
                                         stat.st_mtime_ns, stat.st_ctime_ns]
            except FileNotFoundError:
                credential_generation = "ABSENT"
        revision = current._resource_revisions.get(alias, 0)
        body = {"schema": "vati.account-resource/1", "alias": alias,
                "revision": revision, "account": asdict(account) if account else None,
                "credential_file_generation": credential_generation}
        return {"schema": "vati.account-resource/1", "alias": alias,
                "state": "REGISTERED" if account else "ABSENT",
                "revision": revision, "resource_version": canonical_hash(body)}
