from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


DEFAULT_ACTIVITY_TYPES = [
    "Desenvolvimento",
    "Correção",
    "Teste",
    "Documentação",
    "Atendimento",
    "Análise",
    "Reunião",
]

PENDING_STATUS = "PENDENTE"
FAILED_STATUS = "FALHA"
SYNCED_STATUS = "SINCRONIZADO"


class Database:
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

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS activity_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS active_timer (
                    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                    project_id INTEGER NOT NULL,
                    activity_type_id INTEGER NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id),
                    FOREIGN KEY(activity_type_id) REFERENCES activity_types(id)
                );

                CREATE TABLE IF NOT EXISTS pending_records (
                    record_id TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'PENDENTE',
                    last_attempt_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS audit_actions (
                    action_id TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'PENDENTE',
                    last_attempt_at TEXT NOT NULL DEFAULT '',
                    synced_at TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_audit_actions_record_id
                ON audit_actions(record_id);
                """
            )
            self._migrate_pending_records(connection)

            now = self.now_text()
            project_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            if project_count == 0:
                connection.execute(
                    "INSERT INTO projects(name, active, created_at, updated_at) VALUES (?, 1, ?, ?)",
                    ("Geral", now, now),
                )

            type_count = connection.execute("SELECT COUNT(*) FROM activity_types").fetchone()[0]
            if type_count == 0:
                connection.executemany(
                    "INSERT INTO activity_types(name, active, created_at, updated_at) VALUES (?, 1, ?, ?)",
                    [(name, now, now) for name in DEFAULT_ACTIVITY_TYPES],
                )

    @staticmethod
    def _migrate_pending_records(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(pending_records)").fetchall()
        }
        if "status" not in columns:
            connection.execute(
                "ALTER TABLE pending_records ADD COLUMN status TEXT NOT NULL DEFAULT 'PENDENTE'"
            )
        if "last_attempt_at" not in columns:
            connection.execute(
                "ALTER TABLE pending_records ADD COLUMN last_attempt_at TEXT NOT NULL DEFAULT ''"
            )
        connection.execute(
            """
            UPDATE pending_records
            SET status = CASE WHEN TRIM(last_error) <> '' THEN 'FALHA' ELSE 'PENDENTE' END
            WHERE status IS NULL OR TRIM(status) = '' OR status NOT IN ('PENDENTE', 'FALHA')
            """
        )
        connection.execute(
            """
            UPDATE pending_records
            SET status = 'FALHA'
            WHERE TRIM(last_error) <> '' AND status = 'PENDENTE'
            """
        )

    @staticmethod
    def now_text() -> str:
        return datetime.now().replace(microsecond=0).isoformat(sep=" ")

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def list_items(self, table: str, active_only: bool = False) -> list[sqlite3.Row]:
        if table not in {"projects", "activity_types"}:
            raise ValueError("Tabela inválida")
        query = f"SELECT id, name, active FROM {table}"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY active DESC, name COLLATE NOCASE"
        with self.connect() as connection:
            return list(connection.execute(query).fetchall())

    def add_item(self, table: str, name: str) -> None:
        if table not in {"projects", "activity_types"}:
            raise ValueError("Tabela inválida")
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Informe um nome")
        now = self.now_text()
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO {table}(name, active, created_at, updated_at) VALUES (?, 1, ?, ?)",
                (clean_name, now, now),
            )

    def rename_item(self, table: str, item_id: int, name: str) -> None:
        if table not in {"projects", "activity_types"}:
            raise ValueError("Tabela inválida")
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Informe um nome")
        with self.connect() as connection:
            connection.execute(
                f"UPDATE {table} SET name = ?, updated_at = ? WHERE id = ?",
                (clean_name, self.now_text(), item_id),
            )

    def toggle_item(self, table: str, item_id: int) -> None:
        if table not in {"projects", "activity_types"}:
            raise ValueError("Tabela inválida")
        with self.connect() as connection:
            connection.execute(
                f"UPDATE {table} SET active = CASE active WHEN 1 THEN 0 ELSE 1 END, updated_at = ? WHERE id = ?",
                (self.now_text(), item_id),
            )

    def get_active_timer(self) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT
                    t.project_id,
                    p.name AS project_name,
                    t.activity_type_id,
                    a.name AS activity_type_name,
                    t.description,
                    t.started_at
                FROM active_timer t
                JOIN projects p ON p.id = t.project_id
                JOIN activity_types a ON a.id = t.activity_type_id
                WHERE t.singleton_id = 1
                """
            ).fetchone()

    def start_timer(
        self,
        project_id: int,
        activity_type_id: int,
        description: str,
        started_at: str,
    ) -> None:
        with self.connect() as connection:
            existing = connection.execute("SELECT 1 FROM active_timer WHERE singleton_id = 1").fetchone()
            if existing:
                raise RuntimeError("Já existe um timer em andamento")
            connection.execute(
                """
                INSERT INTO active_timer(
                    singleton_id, project_id, activity_type_id, description, started_at
                ) VALUES (1, ?, ?, ?, ?)
                """,
                (project_id, activity_type_id, description.strip(), started_at),
            )

    def clear_active_timer(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM active_timer WHERE singleton_id = 1")

    def add_pending_record(self, record: dict[str, Any]) -> None:
        """Persiste localmente antes de qualquer tentativa de gravação no CSV."""
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO pending_records(
                    record_id, data_json, created_at, attempts, last_error, status, last_attempt_at
                ) VALUES (?, ?, ?, 0, '', ?, '')
                ON CONFLICT(record_id) DO UPDATE SET
                    data_json = excluded.data_json
                """,
                (
                    record["registro_id"],
                    json.dumps(record, ensure_ascii=False),
                    self.now_text(),
                    PENDING_STATUS,
                ),
            )

    def list_pending_records(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT record_id, data_json, created_at, attempts, last_error, status, last_attempt_at
                FROM pending_records
                ORDER BY created_at, record_id
                """
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "record_id": row["record_id"],
                    "data": json.loads(row["data_json"]),
                    "created_at": row["created_at"],
                    "attempts": row["attempts"],
                    "last_error": row["last_error"],
                    "status": row["status"],
                    "last_attempt_at": row["last_attempt_at"],
                }
            )
        return result

    def mark_pending_error(self, record_id: str, error: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE pending_records
                SET attempts = attempts + 1,
                    last_error = ?,
                    status = ?,
                    last_attempt_at = ?
                WHERE record_id = ?
                """,
                (error[:1000], FAILED_STATUS, self.now_text(), record_id),
            )

    def remove_pending_record(self, record_id: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM pending_records WHERE record_id = ?", (record_id,))

    def pending_count(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM pending_records").fetchone()[0])

    def failed_count(self) -> int:
        with self.connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM pending_records WHERE status = ?", (FAILED_STATUS,)
                ).fetchone()[0]
            )
    def add_audit_action(self, action: dict[str, Any]) -> None:
        """Mantém a ação de exclusão localmente, inclusive após sincronizar."""
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_actions(
                    action_id, record_id, action, data_json, created_at, attempts,
                    last_error, status, last_attempt_at, synced_at
                ) VALUES (?, ?, ?, ?, ?, 0, '', ?, '', '')
                ON CONFLICT(action_id) DO UPDATE SET
                    data_json = excluded.data_json,
                    record_id = excluded.record_id,
                    action = excluded.action
                """,
                (
                    action["acao_id"],
                    action["registro_id"],
                    str(action.get("acao") or "EXCLUIR").upper(),
                    json.dumps(action, ensure_ascii=False),
                    self.now_text(),
                    PENDING_STATUS,
                ),
            )

    def list_audit_actions(self, pending_only: bool = False) -> list[dict[str, Any]]:
        query = (
            "SELECT action_id, record_id, action, data_json, created_at, attempts, "
            "last_error, status, last_attempt_at, synced_at FROM audit_actions"
        )
        params: tuple[Any, ...] = ()
        if pending_only:
            query += " WHERE status <> ?"
            params = (SYNCED_STATUS,)
        query += " ORDER BY created_at, action_id"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            {
                "action_id": row["action_id"],
                "record_id": row["record_id"],
                "action": row["action"],
                "data": json.loads(row["data_json"]),
                "created_at": row["created_at"],
                "attempts": row["attempts"],
                "last_error": row["last_error"],
                "status": row["status"],
                "last_attempt_at": row["last_attempt_at"],
                "synced_at": row["synced_at"],
            }
            for row in rows
        ]

    def mark_audit_error(self, action_id: str, error: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE audit_actions
                SET attempts = attempts + 1,
                    last_error = ?,
                    status = ?,
                    last_attempt_at = ?
                WHERE action_id = ?
                """,
                (error[:1000], FAILED_STATUS, self.now_text(), action_id),
            )

    def mark_audit_synced(self, action_id: str) -> None:
        now = self.now_text()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE audit_actions
                SET status = ?, last_error = '', last_attempt_at = ?, synced_at = ?
                WHERE action_id = ?
                """,
                (SYNCED_STATUS, now, now, action_id),
            )

    def audit_pending_count(self) -> int:
        with self.connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM audit_actions WHERE status <> ?",
                    (SYNCED_STATUS,),
                ).fetchone()[0]
            )

    def audit_failed_count(self) -> int:
        with self.connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM audit_actions WHERE status = ?",
                    (FAILED_STATUS,),
                ).fetchone()[0]
            )

