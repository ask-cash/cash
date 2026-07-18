"""
test_secrets_exec.py — scoped executor for authenticated calls.

Covers the core guarantee (the secret never appears in the returned result),
secret injection sites (bearer/header/query), default-deny host/command
allowlisting, missing-secret handling, and output scrubbing for both the HTTP
and subprocess paths. Stdlib unittest with fake vault/transport/runner — no
network, no real subprocess.

Run:  ./venv/bin/python -m unittest tests.test_secrets_exec -v
"""

import unittest

from services import secrets_exec

SECRET = "sk-supersecret-123"


class _FakeVault:
    def __init__(self, store):
        self.store = store

    def get_secret(self, name, *, tenant_id=None):
        return self.store.get(name)


class _Resp:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


class _Base(unittest.TestCase):
    def setUp(self):
        self._orig_vault = secrets_exec.secret_vault
        secrets_exec.secret_vault = _FakeVault({"api_key": SECRET})

    def tearDown(self):
        secrets_exec.secret_vault = self._orig_vault


class HttpTest(_Base):
    def _echo_transport(self, method, url, headers, params, body):
        # Echo everything back so we can prove injection + scrubbing.
        return _Resp(200, f"{method} {url} headers={headers} params={params}")

    def test_bearer_injection_and_scrubbing(self):
        spec = {"url": "https://api.example.com/v1/thing", "allow_hosts": ["api.example.com"]}
        out = secrets_exec.run_authenticated_request("api_key", spec, transport=self._echo_transport)
        self.assertTrue(out["ok"])
        self.assertEqual(out["status_code"], 200)
        # The transport echoed the Authorization header (with the secret) — the
        # returned text must have it scrubbed.
        self.assertNotIn(SECRET, out["text"])
        self.assertIn("***", out["text"])

    def test_secret_never_in_returned_result(self):
        spec = {"url": "https://api.example.com/x", "allow_hosts": ["api.example.com"]}
        out = secrets_exec.run_authenticated_request("api_key", spec, transport=self._echo_transport)
        import json
        self.assertNotIn(SECRET, json.dumps(out))

    def test_header_injection(self):
        captured = {}

        def transport(method, url, headers, params, body):
            captured.update(headers=headers, params=params)
            return _Resp(200, "ok")

        spec = {
            "url": "https://api.example.com/x",
            "allow_hosts": ["api.example.com"],
            "inject": {"where": "header", "name": "X-API-Key"},
        }
        secrets_exec.run_authenticated_request("api_key", spec, transport=transport)
        self.assertEqual(captured["headers"]["X-API-Key"], SECRET)

    def test_query_injection(self):
        captured = {}

        def transport(method, url, headers, params, body):
            captured.update(params=params)
            return _Resp(200, "ok")

        spec = {
            "url": "https://api.example.com/x",
            "allow_hosts": ["api.example.com"],
            "inject": {"where": "query", "name": "token"},
        }
        secrets_exec.run_authenticated_request("api_key", spec, transport=transport)
        self.assertEqual(captured["params"]["token"], SECRET)

    def test_disallowed_host_rejected(self):
        spec = {"url": "https://evil.example.net/x"}
        with self.assertRaises(secrets_exec.NotAllowed):
            secrets_exec.run_authenticated_request("api_key", spec, transport=self._echo_transport)

    def test_missing_secret_rejected(self):
        spec = {"url": "https://api.example.com/x", "allow_hosts": ["api.example.com"]}
        with self.assertRaises(secrets_exec.MissingSecret):
            secrets_exec.run_authenticated_request("nope", spec, transport=self._echo_transport)

    def test_host_not_allowed_before_secret_fetch(self):
        # Ordering guarantee: an unlisted host is refused without ever touching
        # the vault (defense in depth).
        touched = {"n": 0}

        class CountingVault:
            def get_secret(self, name, *, tenant_id=None):
                touched["n"] += 1
                return SECRET

        secrets_exec.secret_vault = CountingVault()
        with self.assertRaises(secrets_exec.NotAllowed):
            secrets_exec.run_authenticated_request("api_key", {"url": "https://bad.com/x"})
        self.assertEqual(touched["n"], 0)


class _RunResult:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CommandTest(_Base):
    def test_allowed_command_injects_env_and_scrubs(self):
        seen = {}

        def runner(argv, env):
            seen.update(argv=argv, env=env)
            # Simulate a tool that echoes its token into stdout.
            return _RunResult(0, f"used {env['TOKEN']}", "")

        out = secrets_exec.run_authenticated_command(
            "api_key", ["mytool", "--go"], env_name="TOKEN",
            allow_commands=["mytool"], runner=runner,
        )
        self.assertEqual(seen["env"]["TOKEN"], SECRET)   # secret via env, not argv
        self.assertNotIn(SECRET, str(seen["argv"]))
        self.assertNotIn(SECRET, out["stdout"])
        self.assertIn("***", out["stdout"])
        self.assertEqual(out["returncode"], 0)

    def test_disallowed_command_rejected(self):
        with self.assertRaises(secrets_exec.NotAllowed):
            secrets_exec.run_authenticated_command(
                "api_key", ["rm", "-rf", "/"], env_name="T", runner=lambda a, e: None)

    def test_empty_argv_rejected(self):
        with self.assertRaises(secrets_exec.NotAllowed):
            secrets_exec.run_authenticated_command("api_key", [], env_name="T")


class ScrubTest(unittest.TestCase):
    def test_scrub_replaces_all_occurrences(self):
        self.assertEqual(secrets_exec._scrub("a X b X c", "X"), "a *** b *** c")

    def test_scrub_handles_empty(self):
        self.assertEqual(secrets_exec._scrub("", "X"), "")
        self.assertEqual(secrets_exec._scrub("hi", ""), "hi")


if __name__ == "__main__":
    unittest.main()
