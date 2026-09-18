from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from van_gateway.context.models import SourceTrust
from van_gateway.knowledge.evidence import KnowledgeEvidenceStore
from van_gateway.knowledge.models import (
    KnowledgeProvider,
    ObsidianIndexResult,
    ObsidianQueryRequest,
    ObsidianQueryResult,
    ProviderState,
    ProviderStatus,
)
from van_gateway.knowledge.schema import KnowledgeSchema
from van_gateway.storage.db import Store


class ObsidianProviderError(RuntimeError):
    pass


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd)\b\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}\b"),
    re.compile(r"(?i)\b(?:otp|one[- ]time password|verification code)\b.{0,32}\b\d{4,8}\b"),
)


class ObsidianKnowledgeProvider:
    def __init__(
        self,
        store: Store,
        schema: KnowledgeSchema,
        evidence: KnowledgeEvidenceStore,
        *,
        enabled: bool,
        vault_path: str,
        max_file_bytes: int = 2_000_000,
        max_files: int = 20_000,
        refresh_interval_seconds: int = 30,
    ) -> None:
        self.store = store
        self.schema = schema
        self.evidence = evidence
        self.enabled = enabled
        self.vault_path = vault_path.strip()
        self.max_file_bytes = max(4096, min(max_file_bytes, 20_000_000))
        self.max_files = max(1, min(max_files, 100_000))
        self.refresh_interval_ms = max(1, refresh_interval_seconds) * 1000
        self._last_refresh_ms = 0
        self._lock = asyncio.Lock()

    def _root(self) -> Path:
        if not self.vault_path:
            raise ObsidianProviderError("obsidian_vault_unconfigured")
        root = Path(self.vault_path).expanduser()
        try:
            resolved = root.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise ObsidianProviderError("obsidian_vault_unavailable") from exc
        if not resolved.is_dir():
            raise ObsidianProviderError("obsidian_vault_not_directory")
        return resolved

    async def status(self) -> ProviderStatus:
        certification = await self.evidence.certification(KnowledgeProvider.OBSIDIAN)
        if not self.enabled:
            state = ProviderState.DISABLED
        elif not self.vault_path:
            state = ProviderState.UNCONFIGURED
        else:
            try:
                self._root()
            except ObsidianProviderError:
                state = ProviderState.DEGRADED
            else:
                state = ProviderState.READY if certification and certification["state"] == ProviderState.READY.value else ProviderState.CONFIGURED
        return ProviderStatus(
            provider=KnowledgeProvider.OBSIDIAN,
            state=state,
            credential_locus="local-owner-filesystem",
            evidence_pointer=certification["evidence_pointer"] if certification else None,
            details={
                "incremental_index": True,
                "fts_enabled": self.schema.fts_enabled,
                "automatic_owner_truth_promotion": False,
                "secret_content_indexed": False,
            },
        )

    @staticmethod
    def _document_id(relative_path: str) -> str:
        return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()

    @staticmethod
    def _digest(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
        if not text.startswith("---\n"):
            return {}, text
        end = text.find("\n---\n", 4)
        if end < 0:
            return {}, text
        raw = text[4:end]
        body = text[end + 5:]
        result: dict[str, Any] = {}
        for line in raw.splitlines():
            if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().casefold()
            value = value.strip()
            if not key:
                continue
            if value.startswith("[") and value.endswith("]"):
                result[key] = [part.strip().strip("'\"") for part in value[1:-1].split(",") if part.strip()]
            else:
                result[key] = value.strip("'\"")
        return result, body

    @staticmethod
    def _tags(frontmatter: dict[str, Any], body: str) -> list[str]:
        tags: set[str] = set()
        raw = frontmatter.get("tags")
        if isinstance(raw, list):
            tags.update(str(item).strip().lstrip("#") for item in raw if str(item).strip())
        elif isinstance(raw, str):
            tags.update(part.strip().lstrip("#") for part in re.split(r"[,\s]+", raw) if part.strip())
        tags.update(match.group(1) for match in re.finditer(r"(?<!\w)#([\w/-]+)", body))
        return sorted(tags)

    @staticmethod
    def _links(body: str) -> list[str]:
        links = {match.group(1).strip() for match in re.finditer(r"\[\[([^\]|#]+)", body) if match.group(1).strip()}
        links.update(match.group(1).strip() for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", body) if match.group(1).strip())
        return sorted(links)

    @staticmethod
    def _title(frontmatter: dict[str, Any], relative_path: str, body: str) -> str:
        title = frontmatter.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
        for line in body.splitlines():
            if line.startswith("# ") and line[2:].strip():
                return line[2:].strip()
        return Path(relative_path).stem

    @staticmethod
    def _blocked_reason(frontmatter: dict[str, Any], text: str) -> str | None:
        sensitivity = str(frontmatter.get("van_sensitivity") or frontmatter.get("sensitivity") or "").casefold()
        if sensitivity in {"secret", "credential", "credentials"}:
            return "SECRET_FRONTMATTER"
        if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
            return "SECRET_LIKE_MATERIAL"
        return None

    async def _upsert_fts(self, document_id: str, title: str, body: str, tags: list[str], links: list[str]) -> None:
        if not self.schema.fts_enabled:
            return
        async with self.store.connection() as db:
            await db.execute("DELETE FROM obsidian_fts WHERE document_id=?", (document_id,))
            await db.execute(
                "INSERT INTO obsidian_fts(document_id,title,body_text,tags,links) VALUES (?,?,?,?,?)",
                (document_id, title, body, " ".join(tags), " ".join(links)),
            )
            await db.commit()

    async def index(self, *, force: bool = False) -> ObsidianIndexResult:
        if not self.enabled:
            raise ObsidianProviderError("obsidian_disabled")
        root = self._root()
        async with self._lock:
            candidates = sorted(path for path in root.rglob("*.md") if path.is_file())
            if len(candidates) > self.max_files:
                raise ObsidianProviderError("obsidian_file_limit_exceeded")
            now = int(time.time() * 1000)
            seen: set[str] = set()
            scanned = indexed = unchanged = blocked = 0
            for path in candidates:
                try:
                    resolved = path.resolve(strict=True)
                    relative = resolved.relative_to(root).as_posix()
                except (OSError, ValueError):
                    blocked += 1
                    continue
                if resolved.is_symlink() or not resolved.is_file():
                    blocked += 1
                    continue
                stat = resolved.stat()
                scanned += 1
                doc_id = self._document_id(relative)
                seen.add(relative)
                existing = await self.store.fetchone(
                    "SELECT mtime_ns,size_bytes,content_digest,blocked_reason FROM obsidian_documents WHERE relative_path=?",
                    (relative,),
                )
                if not force and existing is not None and int(existing["mtime_ns"]) == stat.st_mtime_ns and int(existing["size_bytes"]) == stat.st_size:
                    unchanged += 1
                    if existing["blocked_reason"]:
                        blocked += 1
                    continue
                if stat.st_size > self.max_file_bytes:
                    reason = "FILE_TOO_LARGE"
                    text = ""
                    frontmatter: dict[str, Any] = {}
                    body = ""
                else:
                    try:
                        text = resolved.read_text(encoding="utf-8")
                    except (UnicodeDecodeError, OSError):
                        reason = "UNREADABLE_UTF8"
                        text = ""
                        frontmatter = {}
                        body = ""
                    else:
                        frontmatter, body = self._parse_frontmatter(text)
                        reason = self._blocked_reason(frontmatter, text)
                title = self._title(frontmatter, relative, body)
                tags = self._tags(frontmatter, body) if not reason else []
                links = self._links(body) if not reason else []
                digest = self._digest(text) if text else self._digest(f"{relative}:{reason}")
                safe_body = body if not reason else ""
                await self.store.execute(
                    """INSERT INTO obsidian_documents(
                      document_id,relative_path,title,mtime_ns,size_bytes,content_digest,body_text,
                      tags_json,links_json,frontmatter_json,indexed_at_unix_ms,deleted_at_unix_ms,blocked_reason
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(relative_path) DO UPDATE SET title=excluded.title,mtime_ns=excluded.mtime_ns,
                      size_bytes=excluded.size_bytes,content_digest=excluded.content_digest,body_text=excluded.body_text,
                      tags_json=excluded.tags_json,links_json=excluded.links_json,frontmatter_json=excluded.frontmatter_json,
                      indexed_at_unix_ms=excluded.indexed_at_unix_ms,deleted_at_unix_ms=NULL,blocked_reason=excluded.blocked_reason""",
                    (doc_id, relative, title, stat.st_mtime_ns, stat.st_size, digest, safe_body,
                     Store.dumps(tags), Store.dumps(links), Store.dumps(frontmatter if not reason else {}), now, None, reason),
                )
                if reason:
                    blocked += 1
                    if self.schema.fts_enabled:
                        await self.store.execute("DELETE FROM obsidian_fts WHERE document_id=?", (doc_id,))
                else:
                    await self._upsert_fts(doc_id, title, safe_body, tags, links)
                    indexed += 1
            active = await self.store.fetchall("SELECT document_id,relative_path FROM obsidian_documents WHERE deleted_at_unix_ms IS NULL")
            deleted = 0
            for row in active:
                relative = str(row["relative_path"])
                if relative in seen:
                    continue
                deleted += 1
                await self.store.execute("UPDATE obsidian_documents SET deleted_at_unix_ms=? WHERE document_id=?", (now, row["document_id"]))
                if self.schema.fts_enabled:
                    await self.store.execute("DELETE FROM obsidian_fts WHERE document_id=?", (row["document_id"],))
            self._last_refresh_ms = now
            pointer = f"gateway://knowledge/obsidian/index/{now}"
            return ObsidianIndexResult(
                scanned=scanned, indexed=indexed, unchanged=unchanged, blocked=blocked,
                deleted=deleted, fts_enabled=self.schema.fts_enabled, evidence_pointer=pointer,
            )

    @staticmethod
    def _tokens(value: str) -> list[str]:
        return [part.casefold() for part in re.findall(r"[\w/-]+", value, flags=re.UNICODE) if len(part) > 1]

    async def _query_rows(self, query: str, max_results: int) -> tuple[list[Any], bool]:
        tokens = self._tokens(query)
        if self.schema.fts_enabled and tokens:
            fts_query = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens[:24])
            try:
                rows = await self.store.fetchall(
                    """SELECT d.*, bm25(obsidian_fts, 0.0, 8.0, 2.0, 4.0, 2.0) AS rank
                    FROM obsidian_fts JOIN obsidian_documents d USING(document_id)
                    WHERE obsidian_fts MATCH ? AND d.deleted_at_unix_ms IS NULL AND d.blocked_reason IS NULL
                    ORDER BY rank ASC, d.relative_path ASC LIMIT ?""",
                    (fts_query, max_results),
                )
                return rows, True
            except Exception:
                pass
        rows = await self.store.fetchall(
            "SELECT *, 0.0 AS rank FROM obsidian_documents WHERE deleted_at_unix_ms IS NULL AND blocked_reason IS NULL ORDER BY relative_path ASC"
        )
        qset = set(tokens)
        ranked = []
        for row in rows:
            searchable = " ".join((str(row["title"] or ""), str(row["body_text"] or ""), str(row["tags_json"] or ""), str(row["links_json"] or "")))
            score = len(qset.intersection(self._tokens(searchable)))
            if score:
                ranked.append((-score, str(row["relative_path"]), row))
        ranked.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in ranked[:max_results]], False

    async def query(self, request: ObsidianQueryRequest) -> ObsidianQueryResult:
        if not self.enabled:
            raise ObsidianProviderError("obsidian_disabled")
        now = int(time.time() * 1000)
        refreshed = False
        if request.refresh and now - self._last_refresh_ms >= self.refresh_interval_ms:
            await self.index()
            refreshed = True
        rows, fts_used = await self._query_rows(request.query, request.max_results)
        query_id = str(uuid.uuid4())
        evidence_items = []
        for row in rows:
            relative = str(row["relative_path"])
            body = str(row["body_text"] or "")
            item = await self.evidence.persist(
                provider=KnowledgeProvider.OBSIDIAN,
                query_id=query_id,
                source_ref=f"obsidian://{relative}#{row['content_digest']}",
                title=str(row["title"] or Path(relative).stem),
                source_trust=SourceTrust.TRUSTED_OWNER_FILE,
                scope=request.scope,
                content={"path": relative, "digest": str(row["content_digest"]), "body": body},
                snippet=body[:8000],
                metadata={"relative_path": relative, "tags": json.loads(row["tags_json"] or "[]"), "links": json.loads(row["links_json"] or "[]")},
            )
            evidence_items.append(item)
        pointer = f"gateway://knowledge/obsidian/query/{query_id}"
        return ObsidianQueryResult(
            query_id=query_id, query=request.query, evidence=evidence_items,
            evidence_pointer=pointer, index_refreshed=refreshed, fts_used=fts_used,
        )

    async def certify(self) -> ProviderStatus:
        result = await self.index(force=True)
        await self.evidence.certify(
            KnowledgeProvider.OBSIDIAN,
            ProviderState.READY,
            evidence_pointer=result.evidence_pointer,
            details={"scanned": result.scanned, "blocked": result.blocked, "fts_enabled": result.fts_enabled, "contains_secrets": False},
        )
        return await self.status()