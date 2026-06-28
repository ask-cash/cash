"""
test_tenant_admin.py — tenants.email + tenants.is_admin (admin vs owner).

Covers the new columns end-to-end on the registry, plus the SQLite
add-missing-columns migration in isolation.

Run:  ./venv/bin/python -m unittest tests.test_tenant_admin -v
"""

import sqlite3
import unittest

from services import db, tenant_registry
from services.tenancy import system_context


class TestTenantAdminFields(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.bootstrap()  # idempotent; ensures tenants has email/is_admin

    def test_admin_tenant_round_trip(self):
        with system_context():
            tenant_registry.ensure_tenant(
                "tnt_admin_test", display_name="Suhail",
                email="me@whysuhail.xyz", is_admin=True,
            )
            rec = tenant_registry.get_tenant("tnt_admin_test")
        self.assertIsNotNone(rec)
        self.assertTrue(rec.is_admin)
        self.assertEqual(rec.email, "me@whysuhail.xyz")

    def test_regular_tenant_defaults(self):
        with system_context():
            tenant_registry.ensure_tenant("tnt_regular_test", display_name="Acme")
            rec = tenant_registry.get_tenant("tnt_regular_test")
        self.assertFalse(rec.is_admin)
        self.assertEqual(rec.email, "")

    def test_set_tenant_meta_updates_existing(self):
        with system_context():
            tenant_registry.ensure_tenant("tnt_promote_test")
            tenant_registry.set_tenant_meta(
                "tnt_promote_test", is_admin=True, email="ops@example.com",
            )
            rec = tenant_registry.get_tenant("tnt_promote_test")
        self.assertTrue(rec.is_admin)
        self.assertEqual(rec.email, "ops@example.com")

    def test_get_admin_tenant_finds_admin(self):
        with system_context():
            tenant_registry.ensure_tenant(
                "tnt_admin_lookup", email="a@b.co", is_admin=True,
            )
            admin = tenant_registry.get_admin_tenant()
        self.assertIsNotNone(admin)
        self.assertTrue(admin.is_admin)


class TestSqliteColumnMigration(unittest.TestCase):
    def test_adds_only_missing_columns_idempotently(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE tenants (tenant_id TEXT PRIMARY KEY, display_name TEXT)")
        cols = {"email": "TEXT", "is_admin": "INTEGER NOT NULL DEFAULT 0"}
        db._sqlite_add_missing_columns(conn, "tenants", cols)
        present = {r[1] for r in conn.execute("PRAGMA table_info(tenants)").fetchall()}
        self.assertIn("email", present)
        self.assertIn("is_admin", present)
        # second run must be a no-op (no "duplicate column" error)
        db._sqlite_add_missing_columns(conn, "tenants", cols)
        conn.close()


if __name__ == "__main__":
    unittest.main()
