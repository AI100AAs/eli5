from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from server.gizmoapp_server.db import (
    LATEST_SCHEMA_VERSION,
    backup_database,
    database_readiness,
    initialize_database,
    verify_database_schema,
)


class DatabaseHardeningTests(unittest.TestCase):
    def test_database_uses_wal_busy_timeout_and_current_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.sqlite3"
            config = {"DB_PATH": db_path}
            initialize_database(config)

            connection = sqlite3.connect(db_path)
            try:
                journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(journal_mode.lower(), "wal")
            self.assertEqual(version, LATEST_SCHEMA_VERSION)
            verify_database_schema(config)
            self.assertTrue(database_readiness(config)[0])

    def test_backup_is_a_consistent_readable_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = {"DB_PATH": root / "app.sqlite3"}
            initialize_database(config)
            backup_path = backup_database(config, root / "backups" / "app.sqlite3")

            connection = sqlite3.connect(backup_path)
            try:
                version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(version, LATEST_SCHEMA_VERSION)

    def test_outdated_database_is_not_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {"DB_PATH": Path(temp_dir) / "empty.sqlite3"}
            sqlite3.connect(config["DB_PATH"]).close()

            ready, detail = database_readiness(config)
            self.assertFalse(ready)
            self.assertEqual(detail["database"], "schema-outdated")
            with self.assertRaisesRegex(RuntimeError, "schema is version 0"):
                verify_database_schema(config)


if __name__ == "__main__":
    unittest.main()
