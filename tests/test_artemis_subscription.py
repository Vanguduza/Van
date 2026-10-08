"""Contract tests; fixtures do not constitute handset or provider acceptance."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path("/opt/hermes-mobile-fabric/artemis/current").resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/artemis_subscription"))
try:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from provider import (ACCOUNT, MODEL, ChatGPTSubscriptionChatModel, codex_command,
        messages_to_input, response_message, subscription_environment, validate_account)
except ModuleNotFoundError as error:
    raise unittest.SkipTest("Run these optional adapter tests in the native Artemis environment") from error


class SubscriptionContracts(unittest.TestCase):
    def test_matching_chatgpt_account(self):
        account = validate_account({"type": "chatgpt", "email": ACCOUNT, "planType": "prolite"})
        self.assertEqual(account["email"], ACCOUNT)

    def test_different_account_refused(self):
        with self.assertRaises(PermissionError):
            validate_account({"type": "chatgpt", "email": "fixture@example.invalid"})

    def test_api_key_login_refused(self):
        with self.assertRaises(PermissionError):
            validate_account({"type": "apiKey"})

    def test_missing_login_refused(self):
        with self.assertRaises(PermissionError):
            validate_account(None)

    def test_process_environment_excludes_api_billing(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-only",
                                   "OPENAI_BASE_URL": "https://fixture.invalid",
                                   "CODEX_ACCESS_TOKEN": "fixture-only"}):
            env = subscription_environment()
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("OPENAI_BASE_URL", env)
        self.assertNotIn("CODEX_ACCESS_TOKEN", env)

    def test_codex_environment_excludes_native_loader_settings(self):
        with patch.dict(os.environ, {"LD_LIBRARY_PATH": "/fixture/native",
                                   "QT_QPA_FONTDIR": "/fixture/fonts",
                                   "QT_QPA_PLATFORM_PLUGIN_PATH": "/fixture/plugins",
                                   "CODEX_HOME": "/fixture/existing-account"}):
            env = subscription_environment()
        self.assertNotIn("LD_LIBRARY_PATH", env)
        self.assertNotIn("QT_QPA_FONTDIR", env)
        self.assertNotIn("QT_QPA_PLATFORM_PLUGIN_PATH", env)
        self.assertEqual(env["CODEX_HOME"], "/fixture/existing-account")

    def test_command_disables_execution_and_delegation(self):
        command = codex_command()
        self.assertIn("features.shell_tool=false", command)
        self.assertIn("features.unified_exec=false", command)
        self.assertIn("features.multi_agent=false", command)
        self.assertIn("mcp_servers={}", command)

    def test_role_and_tool_result_preserved(self):
        inputs = messages_to_input([HumanMessage(content="fixture"),
            AIMessage(content="", tool_calls=[{"name": "tap", "args": {"x": 1}, "id": "a"}]),
            ToolMessage(content="done", tool_call_id="a")])
        rows = json.loads(inputs[0]["text"].split("\n", 1)[1])
        self.assertEqual([r["role"] for r in rows], ["human", "ai", "tool"])
        self.assertEqual(rows[2]["tool_call_id"], "a")
        self.assertEqual(rows[1]["tool_calls"][0]["name"], "tap")

    def test_inline_image_preserved(self):
        image = "data:image/png;base64,fixture-only"
        inputs = messages_to_input([HumanMessage(content=[
            {"type": "text", "text": "inspect"},
            {"type": "image_url", "image_url": {"url": image}}])])
        self.assertEqual(inputs[1], {"type": "image", "url": image})
        self.assertIn("Attached image 1", inputs[0]["text"])

    def test_non_image_payload_refused(self):
        with self.assertRaises(ValueError):
            messages_to_input([HumanMessage(content=[{"type": "audio", "data": "fixture"}])])

    def test_local_file_url_refused(self):
        with self.assertRaises(ValueError):
            messages_to_input([HumanMessage(content=[
                {"type": "image_url", "image_url": {"url": "file:///fixture"}}])])

    def test_bound_tool_call_returned_to_artemis(self):
        tools = [{"function": {"name": "tap"}}]
        message = response_message(json.dumps({"content": "", "tool_calls": [
            {"name": "tap", "arguments_json": '{"x":1}'}]}), tools)
        self.assertEqual(message.tool_calls[0]["args"], {"x": 1})

    def test_unbound_tool_refused(self):
        with self.assertRaises(ValueError):
            response_message(json.dumps({"content": "", "tool_calls": [
                {"name": "erase", "arguments_json": "{}"}]}), [{"function": {"name": "tap"}}])

    def test_non_object_tool_arguments_refused(self):
        with self.assertRaises(ValueError):
            response_message(json.dumps({"content": "", "tool_calls": [
                {"name": "tap", "arguments_json": "[]"}]}), [{"function": {"name": "tap"}}])

    def test_every_profile_node_and_fallback_is_exact_model(self):
        profile = json.loads((Path(__file__).resolve().parents[1] /
                              "tools/artemis_subscription/profile.json").read_text())
        nodes = [v for k, v in profile.items() if k != "utils"] + list(profile["utils"].values())
        self.assertEqual(len(nodes), 20)
        for node in nodes:
            self.assertEqual((node["provider"], node["model"]), ("custom", MODEL))
            self.assertEqual(node["fallback"]["model"], MODEL)
        self.assertIn("planner_validation", profile)
        self.assertIn("validator_pixel_safety_net", profile)

    def test_different_requested_model_refused_before_transport(self):
        with self.assertRaises(ValueError):
            ChatGPTSubscriptionChatModel(model_name="fixture").invoke("test")

    def test_binding_is_idempotent_and_refuses_unbound_provider(self):
        from provider import bind_native_artemis
        from artemis.llm.router import ModelFactory
        from types import SimpleNamespace
        with patch.dict(os.environ, {"VAN_ARTEMIS_SUBSCRIPTION_BINDING": "1"}):
            bind_native_artemis()
            first = ModelFactory.create_model.__func__
            bind_native_artemis()
            self.assertIs(first, ModelFactory.create_model.__func__)
            with self.assertRaises(PermissionError):
                ModelFactory.create_model(SimpleNamespace(provider="fixture", model_name="fixture"))

    def test_fresh_native_task_child_inherits_binding(self):
        import subprocess
        profile_dir = Path(__file__).resolve().parents[1] / "tools/artemis_subscription"
        env = dict(os.environ)
        env["VAN_ARTEMIS_SUBSCRIPTION_BINDING"] = "1"
        env["ARTEMIS_ARTEMIS_JSONC"] = str(profile_dir / "profile.json")
        env["PYTHONPATH"] = os.pathsep.join([str(profile_dir), str(ROOT)])
        code = (
            "from artemis.llm.router import ModelFactory, ModelProvider; "
            "from types import SimpleNamespace; "
            "m=ModelFactory.create_model(SimpleNamespace(provider=ModelProvider.CUSTOM, "
            "model_name='gpt-5.6-sol', timeout_seconds=180, reasoning_effort='low')); "
            "import json; print(json.dumps({'model_class':type(m).__name__,"
            "'model_name':m.model_name,'binding':getattr(ModelFactory,'_van_subscription_bound',False)}))"
        )
        result = subprocess.run([sys.executable, "-c", code], env=env, text=True,
                                capture_output=True, timeout=60, check=True)
        data = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(data, {"model_class": "ChatGPTSubscriptionChatModel",
                               "model_name": MODEL, "binding": True})


if __name__ == "__main__":
    unittest.main()
