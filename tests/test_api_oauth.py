"""Production Google OAuth client configuration."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import api


class GoogleOAuthConfigurationTest(unittest.TestCase):
    def test_secret_backed_client_config_does_not_require_a_file(self):
        flow = SimpleNamespace(redirect_uri=None)
        environment = {
            "GOOGLE_OAUTH_CLIENT_ID": "client-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
        }
        with patch.dict(os.environ, environment, clear=False), patch(
            "google_auth_oauthlib.flow.Flow.from_client_config",
            return_value=flow,
        ) as factory, patch(
            "google_auth_oauthlib.flow.Flow.from_client_secrets_file",
        ) as file_factory:
            configured = api._new_google_flow(
                ["openid"],
                "https://cash.example/api/auth/google/callback",
                state="signed-state",
            )

        self.assertIs(configured, flow)
        self.assertEqual(
            configured.redirect_uri,
            "https://cash.example/api/auth/google/callback",
        )
        self.assertEqual(
            factory.call_args.args[0]["web"]["client_id"],
            "client-id",
        )
        self.assertEqual(factory.call_args.kwargs["state"], "signed-state")
        file_factory.assert_not_called()

    def test_partial_environment_configuration_fails_closed(self):
        with patch.dict(
            os.environ,
            {
                "GOOGLE_OAUTH_CLIENT_ID": "client-id",
                "GOOGLE_OAUTH_CLIENT_SECRET": "",
            },
            clear=False,
        ), self.assertRaises(RuntimeError):
            api._new_google_flow(
                ["openid"],
                "https://cash.example/api/auth/google/callback",
            )


if __name__ == "__main__":
    unittest.main()
