#!/usr/bin/env python3
"""Prepare an exact-source tenant-scoped Broadcast replication-slot amendment.

Upstream v2.152.0 chooses one global messages slot suffix. In one PostgreSQL
cluster with many DBs that collides. This adds the immutable native tenant ID
to BOTH runtime call sites, hashing to a bounded PostgreSQL identifier. It
leaves the upstream two-argument helper for compatibility, but runtime paths
use only the new three-argument function. No authority, RLS or JWT is relaxed.
This script writes one new candidate source, never modifies a running release.
"""
import argparse
import hashlib
import os
import pathlib

UPSTREAM_SHA256='8bf4a4a66683e6ae3348234d24551a6d06fef0059364335017fcb043b6236c5a'


def patched_source(source: str) -> str:
    if hashlib.sha256(source.encode()).hexdigest()!=UPSTREAM_SHA256:
        raise ValueError('EXACT_REALTIME_REPLICATION_SOURCE_REQUIRED')
    pairs=[
        ('    slot_name = replication_slot_name(@schema, @table)',
         '    slot_name = replication_slot_name(@schema, @table, tenant_id)'),
        ('    replication_slot_name = replication_slot_name(@schema, @table)',
         '    replication_slot_name = replication_slot_name(@schema, @table, state.tenant_id)')]
    for old,new in pairs:
        if source.count(old)!=1:raise ValueError('REALTIME_SLOT_CALLSITE_DRIFT')
        source=source.replace(old,new,1)
    anchor='  defp slot_suffix, do: Application.get_env(:realtime, :slot_name_suffix)'
    if source.count(anchor)!=1:raise ValueError('REALTIME_SLOT_HELPER_DRIFT')
    addition='''  # DIAL one-cluster/many-database scope. Temporary replication slots are
  # cluster-wide, not database-local. Keep generated identifiers below 63 bytes.
  def replication_slot_name(schema, table, tenant_id) when is_binary(tenant_id) and byte_size(tenant_id) > 0 do
    scope = Enum.join([schema, table, tenant_id, to_string(slot_suffix() || "")], <<0>>)
    digest = :crypto.hash(:sha256, scope) |> Base.encode16(case: :lower) |> binary_part(0, 40)
    "dial_rt_messages_" <> digest
  end

'''
    return source.replace(anchor,addition+anchor,1)


def expected_slot(schema: str,table: str,tenant: str,suffix: str='') -> str:
    if not tenant or any('\0' in x for x in (schema,table,tenant,suffix)):
        raise ValueError('REALTIME_SLOT_SCOPE_INVALID')
    return 'dial_rt_messages_'+hashlib.sha256('\0'.join((schema,table,tenant,suffix)).encode()).hexdigest()[:40]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=pathlib.Path,required=True)
    parser.add_argument('--out',type=pathlib.Path,required=True)
    args=parser.parse_args(argv)
    try:
        source=patched_source(args.source.read_text())
        fd=os.open(args.out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as handle:handle.write(source)
        print('PATCHED_REALTIME_SOURCE_ONLY '+hashlib.sha256(source.encode()).hexdigest())
        return 0
    except (ValueError,OSError):
        print('REFUSED_REALTIME_SOURCE_PATCH')
        return 2

if __name__=='__main__':raise SystemExit(main())
