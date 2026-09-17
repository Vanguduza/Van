"""Schema-driven protobuf (proto2) codec for the cTrader Open API.

The official .proto files are vendored under `proto/` (PROVENANCE.json) and parsed at
import time: no protoc, no generated classes, nothing to drift. Only the subset of proto2
the Open API uses is implemented — scalar varints, doubles, strings, bytes, enums,
nested messages, `repeated` fields and `[default = …]` on `payloadType` — and anything
outside it raises rather than guessing."""

from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

PROTO_DIR = Path(__file__).resolve().parent / "proto"
VARINT_TYPES = {"int32", "int64", "uint32", "uint64", "bool", "sint32", "sint64"}
SCALARS = VARINT_TYPES | {"double", "float", "string", "bytes", "fixed64", "sfixed64", "fixed32", "sfixed32"}


@dataclass(frozen=True)
class Field:
    name: str
    number: int
    label: str          # optional | required | repeated
    type: str           # scalar name, enum name or message name
    default: Any = None


class ProtoSchemaError(ValueError):
    pass


class Schema:
    def __init__(self, files: list[Path]) -> None:
        self.messages: dict[str, list[Field]] = {}
        self.enums: dict[str, dict[str, int]] = {}
        self.files_sha256: dict[str, str] = {}
        for f in files:
            text = f.read_text(encoding="utf-8")
            self.files_sha256[f.name] = hashlib.sha256(text.encode()).hexdigest()
            self._parse(text)
        self.enum_reverse = {e: {v: k for k, v in m.items()} for e, m in self.enums.items()}
        # message name → payload type number (from payloadType's default), and the reverse
        self.payload_type: dict[str, int] = {}
        for name, fields in self.messages.items():
            pt = next((fl for fl in fields if fl.name == "payloadType" and fl.default), None)
            if pt is not None:
                self.payload_type[name] = self.enums[pt.type][pt.default]
        self.message_for_payload: dict[int, str] = {v: k for k, v in self.payload_type.items()}

    # ------------------------------------------------------------- parsing
    def _parse(self, text: str) -> None:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"//[^\n]*", "", text)
        pos = 0
        for m in re.finditer(r"\b(message|enum)\s+(\w+)\s*\{", text):
            kind, name = m.group(1), m.group(2)
            depth, i = 1, m.end()
            while depth and i < len(text):
                if text[i] == "{": depth += 1
                elif text[i] == "}": depth -= 1
                i += 1
            body = text[m.end():i - 1]
            if kind == "enum":
                self.enums[name] = {k: int(v) for k, v in re.findall(r"(\w+)\s*=\s*(-?\d+)\s*;", body)}
            else:
                if re.search(r"\b(message|enum)\s+\w+\s*\{", body):
                    raise ProtoSchemaError(f"nested definitions in {name} are not supported")
                fields = []
                for fm in re.finditer(r"(optional|required|repeated)\s+([\w.]+)\s+(\w+)\s*=\s*(\d+)\s*(\[[^\]]*\])?\s*;", body):
                    label, ftype, fname, num, opts = fm.groups()
                    default = None
                    if opts:
                        dm = re.search(r"default\s*=\s*([\w.\-]+)", opts)
                        default = dm.group(1) if dm else None
                    fields.append(Field(fname, int(num), label, ftype, default))
                self.messages[name] = fields

    def fields(self, message: str) -> list[Field]:
        try:
            return self.messages[message]
        except KeyError:
            raise ProtoSchemaError(f"unknown message {message}") from None

    # ------------------------------------------------------------- encoding
    @staticmethod
    def _varint(n: int) -> bytes:
        if n < 0:
            n += 1 << 64
        out = bytearray()
        while True:
            b = n & 0x7F; n >>= 7
            if n:
                out.append(b | 0x80)
            else:
                out.append(b); return bytes(out)

    def _encode_value(self, f: Field, v: Any) -> bytes:
        t = f.type
        if t in ("int32", "int64", "uint32", "uint64"):
            return self._varint(1 << 3 | 0)[:0] + self._tag(f.number, 0) + self._varint(int(v))
        if t == "bool":
            return self._tag(f.number, 0) + self._varint(1 if v else 0)
        if t in ("sint32", "sint64"):
            n = int(v); return self._tag(f.number, 0) + self._varint((n << 1) ^ (n >> 63))
        if t == "double":
            return self._tag(f.number, 1) + struct.pack("<d", float(v))
        if t in ("fixed64", "sfixed64"):
            return self._tag(f.number, 1) + struct.pack("<q" if t == "sfixed64" else "<Q", int(v))
        if t == "float":
            return self._tag(f.number, 5) + struct.pack("<f", float(v))
        if t in ("fixed32", "sfixed32"):
            return self._tag(f.number, 5) + struct.pack("<i" if t == "sfixed32" else "<I", int(v))
        if t == "string":
            b = str(v).encode("utf-8"); return self._tag(f.number, 2) + self._varint(len(b)) + b
        if t == "bytes":
            b = bytes(v); return self._tag(f.number, 2) + self._varint(len(b)) + b
        if t in self.enums:
            n = self.enums[t][v] if isinstance(v, str) else int(v)
            return self._tag(f.number, 0) + self._varint(n)
        if t in self.messages:
            b = self.encode(t, v); return self._tag(f.number, 2) + self._varint(len(b)) + b
        raise ProtoSchemaError(f"unsupported type {t} for {f.name}")

    @classmethod
    def _tag(cls, number: int, wire: int) -> bytes:
        return cls._varint(number << 3 | wire)

    def encode(self, message: str, values: dict[str, Any]) -> bytes:
        out = bytearray()
        fields = {f.name: f for f in self.fields(message)}
        unknown = set(values) - set(fields)
        if unknown:
            raise ProtoSchemaError(f"{message}: unknown fields {sorted(unknown)}")
        for f in self.fields(message):
            if f.name in values and values[f.name] is not None:
                v = values[f.name]
                if f.label == "repeated":
                    for item in v:
                        out += self._encode_value(f, item)
                else:
                    out += self._encode_value(f, v)
            elif f.name == "payloadType" and f.default is not None:
                out += self._encode_value(f, f.default)
            elif f.label == "required" and f.name != "payloadType":
                raise ProtoSchemaError(f"{message}: required field {f.name} missing")
        return bytes(out)

    # ------------------------------------------------------------- decoding
    @staticmethod
    def _read_varint(data: bytes, i: int) -> tuple[int, int]:
        shift = n = 0
        while True:
            b = data[i]; i += 1
            n |= (b & 0x7F) << shift
            if not b & 0x80:
                return n, i
            shift += 7
            if shift > 70:
                raise ProtoSchemaError("varint too long")

    def _raw_fields(self, data: bytes) -> Iterator[tuple[int, int, Any]]:
        i = 0
        while i < len(data):
            key, i = self._read_varint(data, i)
            number, wire = key >> 3, key & 7
            if wire == 0:
                v, i = self._read_varint(data, i)
            elif wire == 1:
                v, i = data[i:i + 8], i + 8
            elif wire == 2:
                ln, i = self._read_varint(data, i); v, i = data[i:i + ln], i + ln
            elif wire == 5:
                v, i = data[i:i + 4], i + 4
            else:
                raise ProtoSchemaError(f"unsupported wire type {wire}")
            yield number, wire, v

    def _decode_value(self, f: Field, wire: int, raw: Any) -> Any:
        t = f.type
        if t in ("int32", "int64"):
            n = raw; return n - (1 << 64) if n >= 1 << 63 else n
        if t in ("uint32", "uint64"):
            return raw
        if t == "bool":
            return bool(raw)
        if t in ("sint32", "sint64"):
            return (raw >> 1) ^ -(raw & 1)
        if t == "double":
            return struct.unpack("<d", raw)[0]
        if t in ("fixed64", "sfixed64"):
            return struct.unpack("<q" if t == "sfixed64" else "<Q", raw)[0]
        if t == "float":
            return struct.unpack("<f", raw)[0]
        if t in ("fixed32", "sfixed32"):
            return struct.unpack("<i" if t == "sfixed32" else "<I", raw)[0]
        if t == "string":
            return raw.decode("utf-8", "replace")
        if t == "bytes":
            return bytes(raw)
        if t in self.enums:
            return self.enum_reverse[t].get(raw, raw)
        if t in self.messages:
            return self.decode(t, raw)
        raise ProtoSchemaError(f"unsupported type {t}")

    def decode(self, message: str, data: bytes) -> dict[str, Any]:
        by_num = {f.number: f for f in self.fields(message)}
        out: dict[str, Any] = {}
        for number, wire, raw in self._raw_fields(data):
            f = by_num.get(number)
            if f is None:
                continue   # unknown field: forward-compatible skip
            v = self._decode_value(f, wire, raw)
            if f.label == "repeated":
                out.setdefault(f.name, []).append(v)
            else:
                out[f.name] = v
        for f in by_num.values():
            if f.name not in out and f.default is not None and f.label != "repeated":
                out[f.name] = f.default if (f.type in self.enums or f.type == "string") else (f.default.lower() == "true" if f.type == "bool" else (float(f.default) if f.type in ("double", "float") else int(f.default)))
        return out

    # ------------------------------------------------------------- framing helpers
    def wrap(self, message: str, values: dict[str, Any], client_msg_id: str | None = None) -> bytes:
        """ProtoMessage envelope bytes for a typed payload."""
        pt = self.payload_type.get(message)
        if pt is None:
            raise ProtoSchemaError(f"{message} has no payloadType default")
        env = {"payloadType": pt, "payload": self.encode(message, values)}
        if client_msg_id:
            env["clientMsgId"] = client_msg_id
        return self.encode("ProtoMessage", env)

    def unwrap(self, data: bytes) -> tuple[str | None, dict[str, Any], str | None]:
        env = self.decode("ProtoMessage", data)
        name = self.message_for_payload.get(env.get("payloadType"))
        body = self.decode(name, env.get("payload", b"")) if name else {"payloadType": env.get("payloadType"), "raw": env.get("payload")}
        return name, body, env.get("clientMsgId")


def load_schema() -> Schema:
    files = sorted(PROTO_DIR.glob("*.proto"))
    prov = json.loads((PROTO_DIR / "PROVENANCE.json").read_text())
    s = Schema(files)
    for name, digest in prov["files"].items():
        if s.files_sha256.get(name) != digest:
            raise ProtoSchemaError(f"vendored {name} does not match PROVENANCE.json; refusing to speak an unverified protocol")
    return s


SCHEMA = load_schema()
