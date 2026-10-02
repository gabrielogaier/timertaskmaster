from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from database import Database
from dashboard_data import read_local_records


def record(user="Ana", record_id="local", **changes):
    return {
        "registro_id": record_id, "usuario": user, "projeto": "Projeto A",
        "tipo_atividade": "Desenvolvimento", "descricao": "Atividade",
        "inicio": "2026-10-02 08:00:00", "fim": "2026-10-02 09:00:00",
        "duracao_segundos": 3600, "origem_registro": "MANUAL", **changes,
    }


class LocalDashboardTests(unittest.TestCase):
    def test_local_dashboard_is_private_and_includes_all_sync_states(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = Database(Path(temporary) / "test.db")
            db.set_setting("user_name", "Ana")
            for record_id in ["pending", "failed", "synced"]:
                db.add_task_record(record(record_id=record_id))
            db.mark_task_error("failed", "offline")
            db.mark_task_synced("synced")
            db.add_task_record(record("Bruno", "other-user"))
            db.add_task_record(record(record_id="other-day", inicio="2026-10-01 08:00:00"))
            records = read_local_records(db, date(2026, 10, 2))
            self.assertEqual({r.record_id for r in records}, {"pending", "failed", "synced"})
            self.assertEqual(sum(r.duration_seconds for r in records), 10800)
            self.assertTrue(all(r.source_file == str(db.db_path) for r in records))

    def test_missing_identity_never_exposes_other_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = Database(Path(temporary) / "test.db")
            db.add_task_record(record())
            self.assertEqual(read_local_records(db), [])
            db.set_setting("user_name", "Bruno")
            self.assertEqual(read_local_records(db), [])

    def test_local_audit_and_month_selection_preserve_deleted_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = Database(Path(temporary) / "test.db")
            db.set_setting("user_name", "Ana")
            db.add_task_record(record())
            db.add_audit_action({"acao_id": "delete", "registro_id": "local", "acao": "EXCLUIR",
                                 "data_hora_acao": "2026-10-02 10:00:00", "usuario_acao": "Ana",
                                 "motivo": "Duplicado"})
            records = read_local_records(db, year=2026, months=[10])
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0].deleted)
            self.assertEqual(records[0].deletion_reason, "Duplicado")
            self.assertEqual(read_local_records(db, year=2026, months=[9]), [])
            self.assertEqual(len(db.list_task_records()), 1)
