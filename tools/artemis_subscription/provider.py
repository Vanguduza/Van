"""Direct ChatGPT subscription inference for native Artemis.

Codex manages the existing login. This module never opens auth.json, exports
tokens, selects API-key billing, or delegates phone control to Codex tools.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.utils.function_calling import convert_to_openai_tool

MODEL = "gpt-5.6-sol"
ACCOUNT = "tapiwaguduza@gmail.com"
_CLI_PATH = os.environ.get("VAN_ARTEMIS_SUBSCRIPTION_CLI_PATH", os.environ.get("PATH", os.defpath))
os.environ.setdefault("VAN_ARTEMIS_SUBSCRIPTION_CLI_PATH", _CLI_PATH)
_DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "multi_agent", "plugins", "hooks", "memories",
    "apps", "browser_use", "browser_use_external", "computer_use",
    "code_mode_host", "view_image", "sleep_tool",
)


def codex_command() -> list[str]:
    command = [os.environ.get("VAN_ARTEMIS_CODEX", "/home/ubuntu/.local/bin/codex"),
               "app-server", "--listen", "stdio://",
               "-c", 'model_provider="openai"', "-c", "mcp_servers={}",
               "-c", 'web_search="disabled"',
               "-c", "features.unbounded_connection_retries=false",
               "-c", "features.skip_host_skill_discovery=true"]
    for feature in _DISABLED_FEATURES:
        command += ["-c", f"features.{feature}=false"]
    return command


def subscription_environment() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = _CLI_PATH
    for name in ("LD_LIBRARY_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_FONTDIR"):
        env.pop(name, None)
    # The existing account cache is used in place. No credential file is copied.
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "AZURE_OPENAI_API_KEY",
                 "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
        env.pop(name, None)
    return env


def validate_account(account: dict | None) -> dict:
    if not account or account.get("type") != "chatgpt":
        raise PermissionError("Native Artemis requires a ChatGPT subscription login")
    if account.get("email", "").casefold() != ACCOUNT.casefold():
        raise PermissionError("Native Artemis ChatGPT account does not match the owner request")
    return {k: account.get(k) for k in ("type", "email", "planType")}


class SubscriptionSession:
    """One bounded stdio session; all subprocesses are owned and reaped."""

    def __init__(self, timeout: float = 180):
        self.timeout = timeout
        self.process = None
        self.next_id = 0
        self.thread_id = None
        self.account = None
        self.usage = None
        self.event_count = 0

    async def __aenter__(self):
        self.process = await asyncio.create_subprocess_exec(
            *codex_command(), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env=subscription_environment(), cwd=tempfile.gettempdir(),
            limit=8 * 1024 * 1024)
        try:
            await self.rpc("initialize", {"clientInfo": {
                "name": "van_artemis", "title": "VAN native Artemis", "version": "1.0.0"},
                "capabilities": {"experimentalApi": True}})
            await self.send({"method": "initialized", "params": {}})
            result = await self.rpc("account/read", {"refreshToken": False})
            self.account = validate_account(result.get("account"))
            return self
        except BaseException:
            await self.__aexit__(None, None, None)
            raise

    async def __aexit__(self, *unused):
        process = self.process
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    async def send(self, message):
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        await self.process.stdin.drain()

    async def receive(self):
        line = await asyncio.wait_for(self.process.stdout.readline(), self.timeout)
        if not line:
            raise RuntimeError("ChatGPT subscription transport closed before completion")
        message = json.loads(line)
        self.event_count += 1
        if self.event_count > 20000:
            raise RuntimeError("ChatGPT subscription event budget exceeded")
        # No tool execution or login challenge is accepted in this inference adapter.
        if message.get("method") and "id" in message:
            await self.send({"id": message["id"], "error": {
                "code": -32601, "message": "VAN Artemis inference does not execute Codex tools"}})
            raise PermissionError("Unexpected Codex tool or authentication request")
        return message

    async def rpc(self, method, params):
        self.next_id += 1
        request_id = self.next_id
        await self.send({"id": request_id, "method": method, "params": params})
        async with asyncio.timeout(self.timeout):
            while True:
                response = await self.receive()
                if response.get("id") == request_id:
                    if "error" in response:
                        raise RuntimeError("ChatGPT subscription RPC rejected: " + method)
                    return response["result"]

    async def complete(self, input_items, schema=None, effort="low"):
        thread = await self.rpc("thread/start", {
            "model": MODEL, "modelProvider": "openai", "ephemeral": True,
            "cwd": tempfile.gettempdir(), "sandbox": "read-only",
            "approvalPolicy": {"granular": {"mcp_elicitations": False,
                "sandbox_approval": False, "rules": False,
                "skill_approval": False, "request_permissions": False}},
            "baseInstructions": (
                "You are the inference model for native Artemis. Follow the supplied "
                "conversation and output contract. Do not execute tools, commands, "
                "browse, inspect files, or delegate. Return only the requested response. "
                "Artemis alone executes phone actions described in your response."),
            "developerInstructions": "Use exactly gpt-5.6-sol. Do not select another model.",
            "config": {"mcp_servers": {}, "web_search": "disabled"}})
        if thread.get("model") != MODEL or thread.get("modelProvider") != "openai":
            raise PermissionError("ChatGPT subscription model/provider readback mismatch")
        self.thread_id = thread["thread"]["id"]
        params = {"threadId": self.thread_id, "model": MODEL, "effort": effort,
                  "input": input_items}
        if schema is not None:
            params["outputSchema"] = schema
        await self.rpc("turn/start", params)
        final_messages = []
        async with asyncio.timeout(self.timeout):
            while True:
                event = await self.receive()
                method, data = event.get("method"), event.get("params", {})
                if method == "thread/tokenUsage/updated":
                    self.usage = data.get("tokenUsage")
                elif method in ("item/started", "item/completed"):
                    item = data.get("item", {})
                    item_type = item.get("type")
                    if item_type in ("commandExecution", "fileChange", "mcpToolCall",
                                     "webSearch", "collabAgentToolCall"):
                        raise PermissionError("Codex tried to execute a non-inference tool")
                    if method == "item/completed" and item_type == "agentMessage":
                        if item.get("phase") in (None, "final_answer"):
                            final_messages.append(item.get("text", ""))
                elif method == "turn/completed":
                    if data.get("turn", {}).get("status") != "completed":
                        raise RuntimeError("ChatGPT subscription turn did not complete")
                    text = "\n".join(final_messages).strip()
                    if not text:
                        raise RuntimeError("ChatGPT subscription returned no final response")
                    return text


async def read_subscription_account():
    async with SubscriptionSession(timeout=20) as session:
        return session.account


def messages_to_input(messages: list[BaseMessage]) -> list[dict]:
    """Preserve roles/tool results and attach only supplied image inputs."""
    conversation, images = [], []
    for message in messages:
        parts = []
        if isinstance(message.content, str):
            parts.append(message.content)
        else:
            for block in message.content:
                if isinstance(block, str):
                    parts.append(block)
                elif block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") in ("image_url", "image"):
                    image = block.get("image_url", block.get("url"))
                    if isinstance(image, dict):
                        image = image.get("url")
                    if not isinstance(image, str) or not (
                        image.startswith("data:image/") or image.startswith("https://")
                    ):
                        raise ValueError("Unsupported Artemis image input")
                    images.append({"type": "image", "url": image})
                    parts.append(f"[Attached image {len(images)}]")
                elif block.get("type") == "thinking":
                    continue
                else:
                    raise ValueError("Unsupported multimodal input; only text/images are qualified")
        row = {"role": message.type, "content": "\n".join(parts)}
        if getattr(message, "tool_calls", None):
            row["tool_calls"] = message.tool_calls
        if getattr(message, "tool_call_id", None):
            row["tool_call_id"] = message.tool_call_id
        conversation.append(row)
    if len(images) > 20:
        raise ValueError("Artemis image count exceeds this adapter's bound")
    text = "Respond to this Artemis conversation, preserving its roles:\n" + json.dumps(conversation)
    return [{"type": "text", "text": text}, *images]


def tool_response_schema(tools: list[dict]) -> dict:
    return {"type": "object", "properties": {
        "content": {"type": "string"},
        "tool_calls": {"type": "array", "items": {"type": "object",
            "properties": {"name": {"type": "string", "enum": [t["function"]["name"] for t in tools]},
                           "arguments_json": {"type": "string"}},
            "required": ["name", "arguments_json"], "additionalProperties": False}}},
        "required": ["content", "tool_calls"], "additionalProperties": False}


def response_message(text: str, tools: list[dict] | None = None) -> AIMessage:
    if not tools:
        return AIMessage(content=text)
    data = json.loads(text)
    allowed = {tool["function"]["name"] for tool in tools}
    calls = []
    for call in data["tool_calls"]:
        if call["name"] not in allowed:
            raise ValueError("Model selected an unbound Artemis tool")
        arguments = json.loads(call["arguments_json"])
        if not isinstance(arguments, dict):
            raise ValueError("Artemis tool arguments must be an object")
        calls.append({"name": call["name"], "args": arguments,
                      "id": "van_" + uuid4().hex, "type": "tool_call"})
    return AIMessage(content=data["content"], tool_calls=calls)


class ChatGPTSubscriptionChatModel(BaseChatModel):
    model_name: str = MODEL
    timeout_seconds: float = 180
    reasoning_effort: str = "low"

    @property
    def _llm_type(self):
        return "van-chatgpt-subscription"

    @property
    def _identifying_params(self):
        return {"model_name": self.model_name, "auth": "CHATGPT_SUBSCRIPTION",
                "account": ACCOUNT}

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        if tool_choice not in (None, "auto", "any", "required"):
            raise ValueError("Unsupported subscription tool_choice")
        return self.bind(_subscription_tools=[convert_to_openai_tool(t) for t in tools],
                         _subscription_tool_choice=tool_choice)

    def with_structured_output(self, schema, *, include_raw=False, **kwargs):
        schema_dict = schema.model_json_schema() if hasattr(schema, "model_json_schema") else schema
        if not isinstance(schema_dict, dict):
            raise TypeError("Structured output needs a model or JSON schema")
        bound = self.bind(_subscription_schema=schema_dict)
        def parse(message):
            try:
                value = json.loads(message.content)
                if hasattr(schema, "model_validate"):
                    value = schema.model_validate(value)
                return {"raw": message, "parsed": value, "parsing_error": None} if include_raw else value
            except Exception as error:
                if include_raw:
                    return {"raw": message, "parsed": None, "parsing_error": error}
                raise
        return bound | RunnableLambda(parse)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return asyncio.run(self._agenerate(messages, stop=stop, **kwargs))

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.model_name != MODEL:
            raise ValueError("This owner binding permits only gpt-5.6-sol")
        if stop:
            raise ValueError("Subscription adapter does not emulate stop sequences")
        tools = kwargs.get("_subscription_tools")
        schema = kwargs.get("_subscription_schema")
        inputs = messages_to_input(messages)
        if tools:
            if schema:
                raise ValueError("Combined tool and structured output is unsupported")
            schema = tool_response_schema(tools)
            choice = kwargs.get("_subscription_tool_choice")
            inputs[0]["text"] += "\nAvailable Artemis tools:\n" + json.dumps(tools)
            inputs[0]["text"] += (
                "\nReturn the response contract. Tool arguments are JSON object strings. "
                "Describe calls; do not execute them. "
                + ("Select at least one tool call." if choice in ("any", "required") else "Call tools only when needed."))
        started = time.monotonic()
        async with SubscriptionSession(timeout=self.timeout_seconds) as session:
            text = await session.complete(inputs, schema=schema, effort=self.reasoning_effort)
            message = response_message(text, tools)
            usage = (session.usage or {}).get("last") or (session.usage or {}).get("total")
            if usage:
                input_count = usage.get("inputTokens", 0)
                output_count = usage.get("outputTokens", 0)
                message.usage_metadata = {"input_tokens": input_count,
                    "output_tokens": output_count, "total_tokens": input_count + output_count}
            message.response_metadata = {"model_name": MODEL, "auth_route": "CHATGPT_SUBSCRIPTION",
                "account": session.account, "thread_id": session.thread_id,
                "elapsed_seconds": round(time.monotonic() - started, 3)}
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        result = await self._agenerate(messages, stop=stop, **kwargs)
        message = result.generations[0].message
        chunks = [{"name": call["name"], "args": json.dumps(call["args"]),
                   "id": call["id"], "index": index}
                  for index, call in enumerate(message.tool_calls)]
        yield ChatGenerationChunk(message=AIMessageChunk(content=message.content,
            tool_call_chunks=chunks, response_metadata=message.response_metadata,
            usage_metadata=message.usage_metadata))


def bind_native_artemis():
    """Register only this explicit custom endpoint and its real account probe."""
    from artemis.llm.router import ModelFactory, ModelProvider
    from artemis.core.diagnostics.probes.credentials_probe import LLMCredentialsProbe
    from artemis.core.diagnostics.schema import ProbeResult, ProbeStatus
    if getattr(ModelFactory, "_van_subscription_bound", False):
        return
    original = ModelFactory.create_model.__func__
    def create_model(cls, endpoint):
        if endpoint.provider == ModelProvider.CUSTOM and endpoint.model_name == MODEL:
            return ChatGPTSubscriptionChatModel(model_name=MODEL,
                timeout_seconds=max(180, endpoint.timeout_seconds),
                reasoning_effort=endpoint.reasoning_effort or "low")
        if os.environ.get("VAN_ARTEMIS_SUBSCRIPTION_BINDING") == "1":
            raise PermissionError("VAN native tasks require the exact owner subscription model")
        return original(cls, endpoint)
    ModelFactory.create_model = classmethod(create_model)
    ModelFactory._van_subscription_bound = True
    async def probe(self):
        try:
            account = await read_subscription_account()
        except Exception as error:
            return ProbeResult(id=self.probe_id, category=self.category,
                title="ChatGPT subscription model", status=ProbeStatus.FAIL,
                is_blocker=True, summary="Subscription binding unavailable",
                description="The requested existing ChatGPT account could not be verified.",
                metadata={"credential_values_exposed": False, "error_type": type(error).__name__})
        return ProbeResult(id=self.probe_id, category=self.category,
            title="ChatGPT subscription model", status=ProbeStatus.PASS,
            is_blocker=True, summary="ChatGPT subscription account confirmed",
            description="Codex manages the owner account authentication. Model inference is verified separately.",
            metadata={"account": account, "model": MODEL,
                      "credential_values_exposed": False, "inference_verified_by_this_probe": False})
    LLMCredentialsProbe.probe = probe
