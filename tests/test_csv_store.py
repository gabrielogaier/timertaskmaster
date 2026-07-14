from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from csv_store import append_record, monthly_csv_path, read_records_for_date


class CsvStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_folder = self.temp_dir.name
        self.record = {
            "registro_id": "fixed-uuid",
            "usuario": "Usuário Teste",
            "origem_registro": "MANUAL",
            "projeto": "Projeto Público",
            "tipo_atividade": "Documentação",
            "descricao": "Criar README",
            "inicio": "2026-07-11 10:00:00",
            "fim": "2026-07-11 10:30:00",
            "duracao_segundos": 1800,
            "duracao_formatada": "00:30:00",
            "observacao": "Concluído",
            "computador": "PC-TESTE",
            "data_registro": "2026-07-11 10:30:00",
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_append_is_idempotent(self) -> None:
        first_path = append_record(self.base_folder, self.record)
        second_path = append_record(self.base_folder, self.record)
        self.assertEqual(first_path, second_path)

        with first_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            rows = list(csv.DictReader(csv_file, delimiter=";"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["registro_id"], "fixed-uuid")
        self.assertEqual(rows[0]["origem_registro"], "MANUAL")

    def test_read_records_for_selected_date(self) -> None:
        append_record(self.base_folder, self.record)
        rows = read_records_for_date(
            self.base_folder,
            self.record["usuario"],
            datetime(2026, 7, 11),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["projeto"], "Projeto Público")

    def test_monthly_path_is_separated_by_user(self) -> None:
        path = monthly_csv_path(
            self.base_folder,
            "Usuário Teste",
            datetime(2026, 7, 11),
        )
        self.assertEqual(path.name, "2026-07.csv")
        self.assertEqual(path.parent.name, "Usuário_Teste")
        self.assertEqual(path.parent.parent.name, "registros")

class CsvAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_folder = self.temp_dir.name
        self.record = {
            "registro_id": "record-delete-1",
            "usuario": "Usuário Teste",
            "origem_registro": "TIMER",
            "projeto": "Projeto A",
            "tipo_atividade": "Teste",
            "descricao": "Registro incorreto",
            "inicio": "2026-07-11 08:00:00",
            "fim": "2026-07-11 09:00:00",
            "duracao_segundos": 3600,
            "duracao_formatada": "01:00:00",
            "observacao": "",
            "computador": "PC-TESTE",
            "data_registro": "2026-07-11 09:00:01",
        }
        self.action = {
            "acao_id": "action-delete-1",
            "registro_id": "record-delete-1",
            "acao": "EXCLUIR",
            "data_hora_acao": "2026-07-11 10:00:00",
            "usuario_acao": "Usuário Teste",
            "motivo": "Timer iniciado por engano",
            "computador": "PC-TESTE",
            "projeto": "Projeto A",
            "tipo_atividade": "Teste",
            "descricao": "Registro incorreto",
            "inicio": "2026-07-11 08:00:00",
            "fim": "2026-07-11 09:00:00",
            "duracao_segundos": 3600,
            "duracao_formatada": "01:00:00",
            "origem_registro": "TIMER",
            "observacao": "",
            "data_registro": "2026-07-11 09:00:01",
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_soft_delete_preserves_original_and_is_idempotent(self) -> None:
        from csv_store import append_audit_action, audit_csv_path

        original_path = append_record(self.base_folder, self.record)
        append_audit_action(self.base_folder, self.action)
        append_audit_action(self.base_folder, self.action)

        with original_path.open("r", newline="", encoding="utf-8-sig") as handle:
            original_rows = list(csv.DictReader(handle, delimiter=";"))
        self.assertEqual(len(original_rows), 1)
        self.assertEqual(original_rows[0]["registro_id"], "record-delete-1")

        audit_path = audit_csv_path(
            self.base_folder,
            "Usuário Teste",
            datetime(2026, 7, 11),
        )
        with audit_path.open("r", newline="", encoding="utf-8-sig") as handle:
            audit_rows = list(csv.DictReader(handle, delimiter=";"))
        self.assertEqual(len(audit_rows), 1)
        self.assertEqual(audit_rows[0]["acao_id"], "action-delete-1")

        rows = read_records_for_date(
            self.base_folder,
            "Usuário Teste",
            datetime(2026, 7, 11),
        )
        self.assertEqual(rows[0]["status_registro"], "EXCLUÍDO")
        self.assertEqual(rows[0]["motivo_exclusao"], "Timer iniciado por engano")


if __name__ == "__main__":
    unittest.main()
