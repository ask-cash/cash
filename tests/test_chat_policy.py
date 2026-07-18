"""Dashboard model entitlements, context trimming, and surface isolation."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from services import ai_brain, chat_policy, platform_commands
from services.providers import ProviderResult
from services.providers.catalog import MANAGED_MODELS


class ModelPolicyTest(unittest.TestCase):
    def test_capabilities_include_every_active_claude_model(self):
        view = chat_policy.capabilities("free")
        self.assertEqual(
            [model["id"] for model in view["models"]],
            [model.id for model in MANAGED_MODELS],
        )
        self.assertEqual(view["defaultModelId"], "claude-haiku-4-5-20251001")
        self.assertEqual(view["contextLimitTokens"], 32_000)

    def test_free_model_access_is_server_enforced(self):
        self.assertEqual(
            chat_policy.require_model("free", "claude-haiku-4-5-20251001").id,
            "claude-haiku-4-5-20251001",
        )
        with self.assertRaises(chat_policy.ChatPolicyError) as raised:
            chat_policy.require_model("free", "claude-opus-4-8")
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(
            chat_policy.require_model("pro", "claude-opus-4-8").id,
            "claude-opus-4-8",
        )

    def test_free_context_cap_is_configurable(self):
        with patch.dict(os.environ, {"FREE_CHAT_CONTEXT_TOKENS": "24000"}):
            model = chat_policy.require_model("free", "claude-haiku-4-5-20251001")
            self.assertEqual(chat_policy.context_limit("free", model), 24_000)

    def test_history_keeps_recent_turns_and_reports_truncation(self):
        messages = [
            {"role": "user", "content": "old " * 500, "attachments": []},
            {"role": "assistant", "content": "middle " * 500, "attachments": []},
            {"role": "user", "content": "recent", "attachments": []},
        ]
        history, state = chat_policy.assemble_history(
            messages,
            limit_tokens=9_000,
            prompt_reserve_tokens=6_000,
        )
        self.assertIn("recent", history)
        self.assertNotIn("old", history)
        self.assertTrue(state.truncated)
        self.assertLessEqual(state.used_tokens, state.limit_tokens)


class SurfacePolicyTest(unittest.TestCase):
    def test_dashboard_prompt_has_no_telegram_command(self):
        prompt = ai_brain._build_system_prompt("dashboard")
        self.assertNotIn("/connect_google", prompt)
        self.assertIn("Library → Integrations", prompt)

    def test_telegram_prompt_owns_telegram_command(self):
        self.assertIn("/connect_google", ai_brain._build_system_prompt("telegram"))

    def test_new_surfaces_fail_closed_without_foreign_commands(self):
        prompt = ai_brain._build_system_prompt("slack")
        self.assertNotIn("/connect_google", prompt)
        self.assertNotIn("/cash-directives", prompt)
        self.assertIn("Library → Integrations", prompt)

    def test_dashboard_intercepts_slash_syntax(self):
        reply = platform_commands.dashboard_command_reply("/connect_google")
        self.assertIsNotNone(reply)
        self.assertIn("Library → Integrations", reply)

    def test_dashboard_claude_selection_pins_anthropic_provider(self):
        result = ProviderResult(
            text='{"action":"chat","params":{},"reply":"ok","memory_ops":[]}',
            model="claude-haiku-4-5-20251001",
        )
        with patch.object(
            ai_brain, "load_profile", return_value={}
        ), patch.object(
            ai_brain, "get_tasks_summary", return_value={"pending": [], "done": []}
        ), patch.object(
            ai_brain, "build_memory_context", return_value=""
        ), patch.object(
            ai_brain, "get_active_decisions", return_value=[]
        ), patch.object(
            ai_brain.memory_brief, "build_brief", return_value=""
        ), patch.object(
            ai_brain.memory_recall, "recall_block", return_value=""
        ), patch.object(
            ai_brain.providers,
            "send_message_result",
            return_value=result,
        ) as send:
            ai_brain.interpret_message(
                "hello",
                surface="dashboard",
                model="claude-haiku-4-5-20251001",
            )
        self.assertEqual(send.call_args.kwargs["provider"], "anthropic")


if __name__ == "__main__":
    unittest.main()
