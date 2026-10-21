"""Authenticated reuse of the existing Site task API; never a second Muse registry.

The Site must explicitly trust this gateway signing key and map it to the same owner.
Missing linkage is unavailable, not a reason to forward a browser cookie or impersonate
Sites identity. The browser-facing BFF implementation is in web/muse-interaction/bff.mjs.
"""
from __future__ import annotations
import json
import uuid
from urllib.parse import urlsplit
import httpx
from .models import MuseError, canonical, digest
from .security import protected_read, signer

READS = frozenset({"muse_get_overview", "muse_get_job", "muse_get_command"})
WRITES = frozenset({"muse_create_project", "muse_resolve_project", "muse_submit_task", "muse_continue_task", "muse_cancel_task"})


def validate_task_call(operation, args):
    if operation not in READS | WRITES or not isinstance(args, dict) or len(canonical(args)) > 48000:
        raise MuseError("muse_task_operation_invalid", 422)
    if operation == "muse_get_overview" and args:
        raise MuseError("muse_task_arguments_invalid", 422)
    if operation == "muse_get_job" and (set(args) != {"job_id"} or not str(args["job_id"]).startswith("muse_")):
        raise MuseError("muse_task_arguments_invalid", 422)
    if operation == "muse_get_command" and (len(args) != 1 or not set(args) <= {"command_id", "idempotency_key"}):
        raise MuseError("muse_task_arguments_invalid", 422)
    if operation in WRITES:
        key=args.get("idempotency_key")
        if not isinstance(key, str) or not 8 <= len(key) <= 128:
            raise MuseError("muse_task_idempotency_required", 422)
    if operation == "muse_cancel_task" and (not str(args.get("job_id", "")).startswith("muse_") or args.get("job_id") != args.get("confirmed_job_id")):
        raise MuseError("muse_exact_task_confirmation_required", 422)


class MuseTasks:
    def __init__(self, settings, *, now, transport=None):
        self.settings,self.now,self.transport=settings,now,transport

    async def call(self, operation, args, *, principal):
        validate_task_call(operation,args)
        try:
            config=json.loads(protected_read(self.settings.muse_tasks_config_file))
            origin=config["site_origin"]
            u=urlsplit(origin)
            if u.scheme!='https' or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
                raise ValueError()
            connection=json.loads(protected_read(config['connection_file']))
            access=connection['site_access_token']
            if not isinstance(access,str) or not 16 <= len(access) <= 8192 or any(c.isspace() for c in access):
                raise ValueError()
            now=self.now()
            envelope={"schema_version":1,"issuer":"VAN_MUSE_GATEWAY","audience":config['audience'],"subject":config['owner_subject'],"principal":principal,"operation":operation,"arguments":args,"payload_hash":digest({"operation":operation,"arguments":args}),"request_id":str(uuid.uuid4()),"issued_at_ms":now,"expires_at_ms":now+60000}
            signed=signer(self.settings.muse_command_signing_key_file)(envelope)
        except MuseError:
            raise
        except (ValueError,KeyError,TypeError) as exc:
            raise MuseError('muse_task_link_unconfigured',503) from exc
        try:
            async with httpx.AsyncClient(transport=self.transport,timeout=20,follow_redirects=False,trust_env=False) as client:
                response=await client.post(origin.rstrip('/')+'/api/muse/van-owner',json=signed,headers={'OAI-Sites-Authorization':'Bearer '+access,'Accept':'application/json'})
            if response.status_code in (401,403,404) or response.status_code>=500 or 300<=response.status_code<400:
                raise MuseError('muse_task_link_unavailable',503)
            if len(response.content)>2*1024*1024 or access.encode() in response.content:
                raise MuseError('muse_task_response_refused',503)
            value=response.json()
            if not isinstance(value,dict):raise ValueError()
            if value.get("ok") is False:
                raise MuseError("muse_task_request_refused",422)
            if response.status_code>=400:
                raise MuseError('muse_task_request_refused',response.status_code)
            return value
        except MuseError:
            raise
        except (httpx.HTTPError,ValueError) as exc:
            raise MuseError('muse_task_link_unavailable',503) from exc
