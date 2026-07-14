from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from database import Database, FAILED_STATUS


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "timertask.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_default_catalogs_are_created(self) -> None:
        projects = self.db.list_items("projects", active_only=True)
        activity_types = self.db.list_items("activity_types", active_only=True)
        self.assertGreaterEqual(len(projects), 1)
        self.assertGreaterEqual(len(activity_types), 1)

    def test_pending_record_lifecycle(self) -> None:
        record = {
            "registro_id": "record-1",
            "usuario": "Teste",
            "origem_registro": "TIMER",
            "projeto": "Geral",
            "tipo_atividade": "Teste",
            "descricao": "Validação",
            "inicio": "2026-07-11 08:00:00",
            "fim": "2026-07-11 09:00:00",
            "duracao_segundos": 3600,
            "duracao_formatada": "01:00:00",
            "observacao": "",
            "computador": "TESTE",
            "data_registro": "2026-07-11 09:00:00",
        }
        self.db.add_pending_record(record)
        self.assertEqual(self.db.pending_count(), 1)

        self.db.mark_pending_error("record-1", "Falha simulada")
        pending = self.db.list_pending_records()[0]
        self.assertEqual(pending["status"], FAILED_STATUS)
        self.assertEqual(pending["attempts"], 1)

        self.db.remove_pending_record("record-1")
        self.assertEqual(self.db.pending_count(), 0)

class AuditDatabaseTests(unittest.TestCase):
    def test_audit_action_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            db = Database(Path(temporary) / "timertask.db")
            action = {
                "acao_id": "action-1",
                "registro_id": "record-1",
                "acao": "EXCLUIR",
                "usuario_acao": "Teste",
                "inicio": "2026-07-11 08:00:00",
            }
            db.add_audit_action(action)
            self.assertEqual(db.audit_pending_count(), 1)
            db.mark_audit_error("action-1", "Rede indisponível")
            pending = db.list_audit_actions(pending_only=True)[0]
            self.assertEqual(pending["status"], FAILED_STATUS)
            db.mark_audit_synced("action-1")
            self.assertEqual(db.audit_pending_count(), 0)
            self.assertEqual(len(db.list_audit_actions()), 1)


if __name__ == "__main__":
    unittest.main()
