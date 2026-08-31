from __future__ import annotations

import sqlite3
import json
import time
from pathlib import Path
from typing import Any

from flask import current_app, g

SCHEMA_MIGRATIONS = {
    1: """
CREATE TABLE IF NOT EXISTS sample_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    description TEXT NOT NULL,
    accent_color TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    radius REAL NOT NULL DEFAULT 0.11,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""",
    2: """
CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""",
}

ARTICLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT 'Saved story',
    summary TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    relationship TEXT NOT NULL DEFAULT '',
    relationship_type TEXT NOT NULL DEFAULT '',
    is_recommended INTEGER NOT NULL DEFAULT 0,
    tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
LATEST_SCHEMA_VERSION = max(SCHEMA_MIGRATIONS)
BUSY_TIMEOUT_MS = 10_000
WRITE_RETRY_DELAYS = (0.05, 0.15, 0.35)


def _connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return connection


def _ensure_migration_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _applied_migrations(connection: sqlite3.Connection) -> set[int]:
    rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(row["version"]) for row in rows}


def _apply_migrations(connection: sqlite3.Connection) -> None:
    _ensure_migration_table(connection)
    applied = _applied_migrations(connection)

    for version, sql in sorted(SCHEMA_MIGRATIONS.items()):
        if version in applied:
            continue
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                f"{sql}\n"
                f"INSERT INTO schema_migrations (version) VALUES ({int(version)});\n"
                "COMMIT;"
            )
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = _connect(str(current_app.config["DB_PATH"]))
    return g.db


def close_db(_: BaseException | None = None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def initialize_database(config: dict) -> None:
    connection = _connect(str(config["DB_PATH"]))
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.executescript(ARTICLE_SCHEMA)
        article_columns = {row[1] for row in connection.execute("PRAGMA table_info(articles)")}
        if "tags_json" not in article_columns:
            connection.execute("ALTER TABLE articles ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'")
        _apply_migrations(connection)
        seed_articles(connection)
        connection.commit()
    finally:
        connection.close()


def schema_version(connection: sqlite3.Connection) -> int:
    try:
        row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row[0] or 0)


def verify_database_schema(config: dict) -> None:
    connection = _connect(str(config["DB_PATH"]))
    try:
        current_version = schema_version(connection)
    finally:
        connection.close()
    if current_version != LATEST_SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema is version {current_version}; expected {LATEST_SCHEMA_VERSION}. "
            "Run: python server/manage.py init-db"
        )


def database_readiness(config: dict) -> tuple[bool, dict[str, Any]]:
    try:
        connection = _connect(str(config["DB_PATH"]))
        try:
            connection.execute("SELECT 1").fetchone()
            current_version = schema_version(connection)
            connection.execute("PRAGMA busy_timeout = 1000")
            connection.execute("BEGIN IMMEDIATE")
            connection.rollback()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return False, {"database": "unavailable", "detail": str(exc)}

    ready = current_version == LATEST_SCHEMA_VERSION
    return ready, {
        "database": "ready" if ready else "schema-outdated",
        "schemaVersion": current_version,
        "expectedSchemaVersion": LATEST_SCHEMA_VERSION,
    }


def backup_database(config: dict, output_path: Path) -> Path:
    source_path = Path(config["DB_PATH"])
    if not source_path.exists():
        raise FileNotFoundError(f"Database does not exist: {source_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source = _connect(str(source_path))
    destination = sqlite3.connect(output_path)
    try:
        source.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source.close()
    return output_path


def fetch_sample_nodes(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, slug, label, description, accent_color, x, y, radius, created_at
        FROM sample_nodes
        ORDER BY id
        LIMIT 500
        """
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_articles(connection: sqlite3.Connection, query: str = "") -> list[dict[str, Any]]:
    term = query.strip().lower()
    pattern = f"%{term}%"
    rows = connection.execute(
        """
        SELECT id, title, source, url, published_at, topic, summary, body,
               relationship, relationship_type, is_recommended, tags_json, created_at
        FROM articles
        WHERE ? = '' OR lower(title) LIKE ? OR lower(source) LIKE ?
           OR lower(topic) LIKE ? OR lower(summary) LIKE ? OR lower(tags_json) LIKE ?
        ORDER BY published_at DESC, id DESC
        LIMIT 200
        """,
        (term, pattern, pattern, pattern, pattern, pattern),
    ).fetchall()
    return [_article_payload(row) for row in rows]


def fetch_article(connection: sqlite3.Connection, article_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM articles WHERE id = ?", (article_id,)
    ).fetchone()
    return _article_payload(row) if row else None


def _article_payload(row: sqlite3.Row) -> dict[str, Any]:
    article = dict(row)
    try:
        tags = json.loads(article.pop("tags_json", "[]"))
    except (TypeError, json.JSONDecodeError):
        tags = []
    article["tags"] = tags if isinstance(tags, list) else []
    return article


def insert_article(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    cursor = connection.execute(
        """
        INSERT INTO articles (title, source, url, published_at, topic, summary, body,
                               relationship, relationship_type, is_recommended, tags_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (payload["title"], payload["source"], payload.get("url", ""),
         payload["published_at"], payload.get("topic", "Saved story"),
          payload.get("summary", "Not simplified yet."), payload.get("body", ""),
          payload.get("relationship", ""), payload.get("relationship_type", ""),
          int(payload.get("is_recommended", 0)), json.dumps(payload.get("tags", []))),
    )
    connection.commit()
    return fetch_article(connection, cursor.lastrowid)  # type: ignore[return-value]


def batch_insert_articles(connection: sqlite3.Connection, payloads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    inserted_ids: list[int] = []
    skipped = 0
    try:
        connection.execute("BEGIN")
        for payload in payloads:
            duplicate = connection.execute(
                """
                SELECT id FROM articles
                WHERE (? <> '' AND url = ?)
                   OR (title = ? AND source = ? AND published_at = ?)
                LIMIT 1
                """,
                (payload.get("url", ""), payload.get("url", ""), payload["title"], payload["source"], payload["published_at"]),
            ).fetchone()
            if duplicate:
                skipped += 1
                continue
            cursor = connection.execute(
                """
                INSERT INTO articles (title, source, url, published_at, topic, summary, body,
                                       relationship, relationship_type, is_recommended, tags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (payload["title"], payload["source"], payload.get("url", ""), payload["published_at"],
                 payload.get("topic", "Saved story"), payload.get("summary", "Not simplified yet."),
                 payload.get("body", ""), payload.get("relationship", ""), payload.get("relationship_type", ""),
                 int(payload.get("is_recommended", 0)), json.dumps(payload.get("tags", []))),
            )
            inserted_ids.append(cursor.lastrowid)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return [fetch_article(connection, article_id) for article_id in inserted_ids], skipped  # type: ignore[misc]


def update_article_summary(connection: sqlite3.Connection, article_id: int, summary: str) -> dict[str, Any] | None:
    connection.execute("UPDATE articles SET summary = ? WHERE id = ?", (summary, article_id))
    connection.commit()
    return fetch_article(connection, article_id)


def update_article_tags(connection: sqlite3.Connection, article_id: int, tags: list[str]) -> dict[str, Any] | None:
    connection.execute("UPDATE articles SET tags_json = ? WHERE id = ?", (json.dumps(tags), article_id))
    connection.commit()
    return fetch_article(connection, article_id)


def delete_article(connection: sqlite3.Connection, article_id: int) -> bool:
    cursor = connection.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    connection.commit()
    return cursor.rowcount > 0


def seed_articles(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0]:
        return
    seed = [
        ("Cities are turning empty parking spaces into tiny parks", "The Civic Journal", "2025-08-06", "Cities", "Some cities are removing a few parking spaces and replacing them with small public gardens. The goal is to give people shade and places to sit.", "A practical experiment in making busy streets more comfortable.", "", 1),
        ("What the new ocean heat report actually says", "Northline Science", "2025-08-05", "Climate", "The ocean is still getting warmer, but the report says the pace changes from year to year. Scientists are watching the long-term trend, not one unusual month.", "This builds on your saved climate story from June.", "update", 0),
        ("A cheaper battery could make home solar more useful", "Future Grid", "2025-08-02", "Energy", "Researchers made a battery with less expensive materials. It is still being tested, so it is not ready to buy yet.", "Related to your note about neighborhood solar storage.", "related", 1),
        ("Why one viral chart about school lunches is misleading", "The Verify Desk", "2025-07-28", "Media literacy", "The chart leaves out several years of data. The full dataset shows a smaller change than the post suggests.", "Contradicts the claim in the saved post from July 20.", "contradiction", 0),
        ("The 15-minute city, explained without the buzzwords", "Common Ground", "2025-06-14", "Cities", "The idea is that daily needs should be close enough to reach by walking, biking, or a short ride. It does not mean people cannot drive.", "A starting point for your cities thread.", "", 0),
    ]
    connection.executemany(
        """INSERT INTO articles (title, source, published_at, topic, summary, relationship,
           relationship_type, is_recommended) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", seed
    )
    connection.commit()


def search_sample_nodes(connection: sqlite3.Connection, query: str, limit: int = 8) -> list[dict[str, Any]]:
    term = query.strip().lower()
    if not term:
        return []

    rows = connection.execute(
        """
        SELECT id, slug, label, description, accent_color, x, y, radius, created_at
        FROM sample_nodes
        WHERE lower(slug) LIKE ?
           OR lower(label) LIKE ?
           OR lower(description) LIKE ?
        ORDER BY id
        LIMIT ?
        """,
        (f"%{term}%", f"%{term}%", f"%{term}%", limit),
    ).fetchall()
    return [dict(row) for row in rows]


def insert_sample_node(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    parameters = (
        payload["slug"],
        payload["label"],
        payload["description"],
        payload["accent_color"],
        payload["x"],
        payload["y"],
        payload["radius"],
    )
    for delay in (*WRITE_RETRY_DELAYS, None):
        try:
            cursor = connection.execute(
                """
                INSERT INTO sample_nodes (slug, label, description, accent_color, x, y, radius)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                parameters,
            )
            connection.commit()
            break
        except sqlite3.OperationalError as exc:
            connection.rollback()
            if "locked" not in str(exc).lower() or delay is None:
                raise
            time.sleep(delay)

    row = connection.execute(
        """
        SELECT id, slug, label, description, accent_color, x, y, radius, created_at
        FROM sample_nodes
        WHERE id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    return dict(row)


def database_summary(config: dict) -> dict[str, Any]:
    connection = _connect(str(config["DB_PATH"]))
    try:
        count = connection.execute("SELECT COUNT(*) FROM sample_nodes").fetchone()[0]
        state_count = connection.execute("SELECT COUNT(*) FROM app_state").fetchone()[0]
        event_count = connection.execute("SELECT COUNT(*) FROM app_events").fetchone()[0]
        current_schema_version = schema_version(connection)
    finally:
        connection.close()

    return {
        "database_path": str(config["DB_PATH"]),
        "sample_node_count": count,
        "app_state_count": state_count,
        "app_event_count": event_count,
        "schema_version": current_schema_version,
    }
