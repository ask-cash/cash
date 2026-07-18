"""Production Google OAuth client configuration."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError
from starlette.requests import Request

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


class AuthTimezoneSchemaTest(unittest.TestCase):
    def test_signup_and_profile_accept_valid_iana_timezone(self):
        signup = api.SignUpBody(
            email="a@example.com",
            password="secret1",
            timezone="America/Los_Angeles",
        )
        profile = api.ProfileBody(timezone="Asia/Kolkata")
        self.assertEqual(signup.timezone, "America/Los_Angeles")
        self.assertEqual(profile.timezone, "Asia/Kolkata")

    def test_signup_and_profile_reject_invalid_timezone(self):
        with self.assertRaises(ValidationError):
            api.SignUpBody(
                email="a@example.com",
                password="secret1",
                timezone="not/a-real-zone",
            )
        with self.assertRaises(ValidationError):
            api.ProfileBody(timezone="../../etc/passwd")

    def test_account_view_returns_flat_timezone(self):
        account = {
            "person_id": "pers_1",
            "tenant_id": "tenant-1",
            "email": "a@example.com",
            "first_name": "A",
            "last_name": "",
            "role": None,
            "platforms": [],
            "onboarded": True,
            "plan": "free",
            "timezone": "Europe/Paris",
        }
        with patch.object(api.integrations, "is_connected", return_value=False):
            view = api._account_view(account)
        self.assertEqual(view["timezone"], "Europe/Paris")

    def test_profile_mutation_origin_guard_rejects_cross_site(self):
        request = Request(
            {
                "type": "http",
                "method": "PATCH",
                "path": "/api/auth/profile",
                "query_string": b"",
                "headers": [
                    (b"host", b"cash.example"),
                    (b"origin", b"https://evil.example"),
                    (b"sec-fetch-site", b"cross-site"),
                ],
                "scheme": "https",
                "server": ("cash.example", 443),
                "client": ("127.0.0.1", 1234),
            }
        )
        response = api._require_same_origin(request)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
