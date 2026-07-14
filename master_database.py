from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator


class MasterDatabase:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def now_text() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS monitored_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    display_name TEXT NOT NULL,
                    source_user TEXT NOT NULL,
                    source_folder TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_folder, source_user)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def list_users(self, active_only: bool = False) -> list[dict[str, object]]:
        sql = (
            "SELECT id, display_name, source_user, source_folder, active, "
            "created_at, updated_at FROM monitored_users"
        )
        params: tuple[object, ...] = ()
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY display_name COLLATE NOCASE, id"
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def add_user(self, display_name: str, source_user: str, source_folder: str) -> int:
        name = display_name.strip()
        source_name = source_user.strip()
        folder = str(Path(source_folder).expanduser())
        if not name or not source_name or not folder.strip():
            raise ValueError("Nome e pasta são obrigatórios")
        now = self.now_text()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO monitored_users(
                    display_name, source_user, source_folder, active, created_at, updated_at
                ) VALUES (?, ?, ?, 1, ?, ?)
                """,
                (name, source_name, folder, now, now),
            )
            return int(cursor.lastrowid)

    def update_user_folder(
        self,
        user_id: int,
        display_name: str,
        source_user: str,
        source_folder: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE monitored_users
                SET display_name = ?, source_user = ?, source_folder = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    display_name.strip(),
                    source_user.strip(),
                    str(Path(source_folder).expanduser()),
                    self.now_text(),
                    user_id,
                ),
            )

    def set_user_active(self, user_id: int, active: bool) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE monitored_users SET active = ?, updated_at = ? WHERE id = ?",
                (1 if active else 0, self.now_text(), user_id),
            )

    def delete_user(self, user_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM monitored_users WHERE id = ?", (user_id,))

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row else default
