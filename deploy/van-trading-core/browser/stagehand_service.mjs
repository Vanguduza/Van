#!/usr/bin/env node
/**
 * Private VAN Stagehand semantic worker.
 *
 * The worker does not own autonomy or authority. It exposes one semantic primitive at a
 * time to VAN Gateway and attaches to the Chromium instance already owned by the Browser
 * Harness worker. Direct Stagehand agent loops are intentionally refused: L5 autonomy is
 * implemented by BrowserSubagentRunner repeatedly asking for one observed action and
 * enforcing Hermes's domain/action-class/payment/budget bounds before replay.
 */
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { Stagehand, localBrowser } from "@browserbasehq/stagehand";
import { z } from "zod";

const STAGEHAND_VERSION = "4.1.0";
const SERVICE_VERSION = "van-stagehand-worker/1";
const MAX_BODY_BYTES = 131072;
const MAX_RESPONSE_BYTES = 1024 * 1024;
const PROFILE_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const DOMAIN_PART_RE = /^[a-z0-9-]{1,63}$/;
const PROVIDER_RE = /^[a-z0-9._-]{1,64}$/;
const MODEL_RE = /^[A-Za-z0-9._:/-]{1,180}$/;
const SECRET_RE = /^secretref:\/\/browser\/([A-Za-z0-9._-]{1,128})$/;

const BIND = process.env.VAN_STAGEHAND_BIND || "127.0.0.1";
const PORT = Number(process.env.VAN_STAGEHAND_PORT || "9140");
const HARNESS_URL = (process.env.VAN_HARNESS_INTERNAL_URL || "http://127.0.0.1:9141").replace(/\/$/, "");
const RUNTIME_ROOT = path.resolve(process.env.VAN_BROWSER_RUNTIME_ROOT || "/run/van-browser");
const SECRET_ROOT = path.resolve(process.env.VAN_BROWSER_SECRET_ROOT || "/var/lib/van-trading/browser/secrets");
const MODEL_KEY_REF = process.env.VAN_STAGEHAND_MODEL_KEY_REF || "secretref://browser/stagehand-model";
const REQUEST_TIMEOUT_MS = Number(process.env.VAN_BROWSER_WORKER_TIMEOUT_SECONDS || "45") * 1000;

if (!["127.0.0.1", "::1", "localhost"].includes(BIND)) {
  throw new Error("stagehand worker refuses a non-loopback bind");
}

class WorkerError extends Error {
  constructor(code, status = 400) {
    super(code);
    this.code = code;
    this.status = status;
  }
}

function safeAlias(value) {
  const alias = String(value || "").trim();
  if (!PROFILE_RE.test(alias)) throw new WorkerError("PROFILE_ALIAS_INVALID", 422);
  return alias;
}

function safeDomain(value) {
  const domain = String(value || "").trim().toLowerCase().replace(/\.$/, "");
  if (!domain || domain.length > 253 || !domain.split(".").every((p) => DOMAIN_PART_RE.test(p))) {
    throw new WorkerError("TARGET_DOMAIN_INVALID", 422);
  }
  return domain;
}

function safeProvider(value) {
  const provider = String(value || "").trim().toLowerCase();
  if (!PROVIDER_RE.test(provider)) throw new WorkerError("MODEL_PROVIDER_INVALID", 422);
  return provider;
}

function safeModel(value, provider) {
  const raw = String(value || "").trim();
  if (!MODEL_RE.test(raw)) throw new WorkerError("MODEL_NAME_INVALID", 422);
  if (raw.includes("/") && !raw.startsWith(provider + "/")) {
    throw new WorkerError("MODEL_PROVIDER_MISMATCH", 422);
  }
  return raw.includes("/") ? raw : provider + "/" + raw;
}

function safeChild(root, name) {
  const candidate = path.resolve(root, name);
  if (path.dirname(candidate) !== root) throw new WorkerError("REFERENCE_PATH_INVALID", 422);
  return candidate;
}

function resolveSecret(ref) {
  const match = SECRET_RE.exec(String(ref || ""));
  if (!match) throw new WorkerError("MODEL_KEY_REFERENCE_INVALID", 503);
  const file = safeChild(SECRET_ROOT, match[1]);
  let stat;
  try {
    stat = fs.statSync(file);
  } catch {
    throw new WorkerError("MODEL_KEY_UNAVAILABLE", 503);
  }
  if (!stat.isFile() || stat.size < 1 || stat.size > 16384) {
    throw new WorkerError("MODEL_KEY_UNAVAILABLE", 503);
  }
  return fs.readFileSync(file, "utf8").trim();
}

function modelKeyPresent() {
  try {
    return Boolean(resolveSecret(MODEL_KEY_REF));
  } catch {
    return false;
  }
}

function instruction(value) {
  const text = String(value || "").trim();
  if (!text || text.length > 8000) throw new WorkerError("INSTRUCTION_INVALID", 422);
  return text;
}

function sanitizeControl(raw) {
  const item = raw && typeof raw === "object" ? raw : {};
  const result = {
    description: String(item.description || "").slice(0, 2000),
    method: String(item.method || "").slice(0, 64),
    arguments: Array.isArray(item.arguments)
      ? item.arguments.slice(0, 32).map((v) => String(v).slice(0, 2000))
      : [],
    selector: String(item.selector || "").slice(0, 4096),
  };
  if (!result.method || !result.selector) {
    throw new WorkerError("STAGEHAND_ACTION_INVALID", 502);
  }
  return result;
}

function zodFromJsonSchema(schema, depth = 0) {
  if (depth > 6 || !schema || typeof schema !== "object" || Array.isArray(schema)) {
    throw new WorkerError("EXTRACTION_SCHEMA_INVALID", 422);
  }
  if (Object.prototype.hasOwnProperty.call(schema, "const")) {
    return z.literal(schema.const);
  }
  if (Array.isArray(schema.enum) && schema.enum.length > 0 && schema.enum.length <= 64) {
    const values = schema.enum;
    if (values.every((v) => typeof v === "string")) {
      return z.enum(values);
    }
    return z.union(values.map((v) => z.literal(v)));
  }

  switch (schema.type) {
    case "string":
      return z.string().max(Math.min(Number(schema.maxLength || 8192), 32768));
    case "number":
      return z.number();
    case "integer":
      return z.number().int();
    case "boolean":
      return z.boolean();
    case "array": {
      const maxItems = Math.min(Number(schema.maxItems || 100), 200);
      return z.array(zodFromJsonSchema(schema.items || {}, depth + 1)).max(maxItems);
    }
    case "object": {
      const props = schema.properties && typeof schema.properties === "object" ? schema.properties : {};
      const entries = Object.entries(props);
      if (entries.length > 64) throw new WorkerError("EXTRACTION_SCHEMA_TOO_WIDE", 422);
      const required = new Set(Array.isArray(schema.required) ? schema.required.map(String) : []);
      const shape = {};
      for (const [key, value] of entries) {
        if (!/^[A-Za-z0-9_.-]{1,128}$/.test(key)) {
          throw new WorkerError("EXTRACTION_SCHEMA_KEY_INVALID", 422);
        }
        const field = zodFromJsonSchema(value, depth + 1);
        shape[key] = required.has(key) ? field : field.optional();
      }
      return z.object(shape).strict();
    }
    default:
      throw new WorkerError("EXTRACTION_SCHEMA_TYPE_UNSUPPORTED", 422);
  }
}

async function ensureHarnessSession(alias, domain) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(HARNESS_URL + "/page_info", {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        task_id: "stagehand-session-prime",
        profile_alias: alias,
        target_domain: domain,
        mode: "PRODUCTION_ACTUATOR",
        allow_helper_authoring: false,
      }),
    });
    const body = await response.text();
    if (!response.ok) {
      throw new WorkerError("HARNESS_SESSION_UNAVAILABLE", response.status >= 500 ? 503 : 409);
    }
    try {
      return JSON.parse(body);
    } catch {
      throw new WorkerError("HARNESS_SESSION_RESPONSE_INVALID", 502);
    }
  } catch (error) {
    if (error instanceof WorkerError) throw error;
    throw new WorkerError("HARNESS_SESSION_UNAVAILABLE", 503);
  } finally {
    clearTimeout(timer);
  }
}

function readCdpEndpoint(alias) {
  const runtime = safeChild(RUNTIME_ROOT, alias);
  const file = path.join(runtime, "cdp-endpoint.json");
  let data;
  try {
    data = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    throw new WorkerError("CDP_HANDOFF_UNAVAILABLE", 503);
  }
  const cdpUrl = String(data.cdp_url || "");
  if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(cdpUrl)) {
    throw new WorkerError("CDP_HANDOFF_INVALID", 503);
  }
  return cdpUrl;
}

const aliasLocks = new Map();

async function withAliasLock(alias, fn) {
  const previous = aliasLocks.get(alias) || Promise.resolve();
  let release;
  const current = new Promise((resolve) => { release = resolve; });
  aliasLocks.set(alias, previous.then(() => current));
  await previous;
  try {
    return await fn();
  } finally {
    release();
    if (aliasLocks.get(alias) === current) aliasLocks.delete(alias);
  }
}

async function withStagehand(body, fn) {
  if (body.allow_model_self_selection !== false) {
    throw new WorkerError("MODEL_SELF_SELECTION_FORBIDDEN", 403);
  }
  if (body.allow_unbounded_agent_loop !== false) {
    throw new WorkerError("UNBOUNDED_AGENT_LOOP_FORBIDDEN", 403);
  }
  const alias = safeAlias(body.profile_alias);
  const domain = safeDomain(body.target_domain);
  const provider = safeProvider(body.model_provider);
  const modelName = safeModel(body.model_name, provider);
  const apiKey = resolveSecret(MODEL_KEY_REF);

  return withAliasLock(alias, async () => {
    await ensureHarnessSession(alias, domain);
    const cdpUrl = readCdpEndpoint(alias);
    let stagehand;
    try {
      const browser = await localBrowser.connect({ cdpUrl });
      stagehand = await Stagehand.create({
        browser,
        model: { modelName, apiKey },
      });
      return await fn(stagehand, alias, domain);
    } catch (error) {
      if (error instanceof WorkerError) throw error;
      throw new WorkerError("STAGEHAND_OPERATION_FAILED", 502);
    } finally {
      if (stagehand) {
        try { await stagehand.close(); } catch {}
      }
    }
  });
}

async function observe(body) {
  const prompt = instruction(body.instruction);
  return withStagehand(body, async (stagehand) => {
    const result = await stagehand.observe(prompt);
    const raw = Array.isArray(result?.data) ? result.data.slice(0, 32) : [];
    const controls = raw.map(sanitizeControl);
    return { controls, extraction: {}, stagehand_version: STAGEHAND_VERSION };
  });
}

async function extract(body) {
  const prompt = instruction(body.instruction);
  const schema = zodFromJsonSchema(body.schema);
  return withStagehand(body, async (stagehand) => {
    const result = await stagehand.extract(prompt, schema);
    return {
      extraction: result?.data ?? {},
      controls: [],
      stagehand_version: STAGEHAND_VERSION,
    };
  });
}

async function act(body) {
  const action = sanitizeControl(body.action);
  return withStagehand(body, async (stagehand, alias, domain) => {
    await stagehand.act(action);
    const page = await ensureHarnessSession(alias, domain);
    return {
      acted: true,
      page: {
        url: String(page.url || "").slice(0, 4096),
        title: String(page.title || "").slice(0, 1024),
      },
      stagehand_version: STAGEHAND_VERSION,
    };
  });
}

const OPERATIONS = new Map([
  ["/observe", observe],
  ["/extract", extract],
  ["/act", act],
]);

function sendJson(res, status, payload) {
  let encoded = Buffer.from(JSON.stringify(payload), "utf8");
  if (encoded.length > MAX_RESPONSE_BYTES) {
    status = 502;
    encoded = Buffer.from(JSON.stringify({ error: "RESPONSE_TOO_LARGE" }), "utf8");
  }
  res.writeHead(status, {
    "content-type": "application/json",
    "content-length": String(encoded.length),
    "cache-control": "no-store",
  });
  res.end(encoded);
}

const server = http.createServer((req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    return sendJson(res, 200, {
      ok: true,
      service: SERVICE_VERSION,
      runtime_version: STAGEHAND_VERSION,
      bind: BIND,
      model_key_present: modelKeyPresent(),
      direct_agent_loop: false,
      model_self_selection: false,
    });
  }
  if (req.method === "POST" && req.url === "/agent") {
    return sendJson(res, 409, { error: "DIRECT_STAGEHAND_AGENT_LOOP_FORBIDDEN" });
  }
  const operation = req.method === "POST" ? OPERATIONS.get(req.url || "") : undefined;
  if (!operation) return sendJson(res, 404, { error: "NOT_FOUND" });

  const rawLength = req.headers["content-length"];
  const length = Number(rawLength);
  if (!Number.isInteger(length) || length < 0) {
    return sendJson(res, 411, { error: "CONTENT_LENGTH_REQUIRED" });
  }
  if (length > MAX_BODY_BYTES) {
    return sendJson(res, 413, { error: "REQUEST_TOO_LARGE" });
  }

  const chunks = [];
  let seen = 0;
  req.on("data", (chunk) => {
    seen += chunk.length;
    if (seen > MAX_BODY_BYTES) req.destroy();
    else chunks.push(chunk);
  });
  req.on("end", async () => {
    try {
      const body = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
      if (!body || typeof body !== "object" || Array.isArray(body)) {
        throw new WorkerError("REQUEST_BODY_NOT_OBJECT", 422);
      }
      const result = await operation(body);
      sendJson(res, 200, result);
    } catch (error) {
      if (error instanceof WorkerError) {
        sendJson(res, error.status, { error: error.code });
      } else {
        sendJson(res, 502, { error: "STAGEHAND_WORKER_FAILURE" });
      }
    }
  });
});

server.listen(PORT, BIND, () => {
  process.stdout.write(\`[van-stagehand] listening on \${BIND}:\${PORT}\\n\`);
});

function shutdown() {
  server.close(() => process.exit(0));
}
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
