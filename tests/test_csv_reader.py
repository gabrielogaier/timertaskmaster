import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from csv_reader import discover_users, read_records, read_records_for_months


FIELDS = [
    "registro_id", "usuario", "origem_registro", "projeto",
    "tipo_atividade", "descricao", "inicio", "fim",
    "duracao_segundos", "observacao", "computador", "data_registro"
]


class CsvReaderTest(unittest.TestCase):
    def _write(self, path: Path, rows: list[dict[str, str]], fields=FIELDS):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

    def test_discovery_read_and_deduplication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            row = {
                "registro_id": "abc",
                "usuario": "Usuario A",
                "origem_registro": "MANUAL",
                "projeto": "Timer Task",
                "tipo_atividade": "Teste",
                "descricao": "Validar leitura",
                "inicio": "2026-07-13T08:00:00",
                "fim": "2026-07-13T09:00:00",
                "duracao_segundos": "3600",
                "observacao": "OK",
                "computador": "PC",
                "data_registro": "2026-07-13T09:00:01",
            }
            self._write(root / "registros" / "Usuario A" / "2026-07.csv", [row])
            # Cópia do mesmo UUID em outro caminho não pode dobrar o total.
            self._write(root / "copia" / "2026-07.csv", [row])

            self.assertEqual(discover_users(str(root)), ["Usuario A"])
            records = read_records(str(root), "Usuario A", date(2026, 7, 13))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].duration_seconds, 3600)
            self.assertEqual(records[0].origin, "MANUAL")

    def test_multiple_users_and_old_csv_without_origin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_fields = [field for field in FIELDS if field != "origem_registro"]
            usuario_a = {
                "registro_id": "g1", "usuario": "Usuario A", "projeto": "A",
                "tipo_atividade": "Teste", "descricao": "A",
                "inicio": "2026-07-13T10:00:00", "fim": "2026-07-13T10:30:00",
                "duracao_segundos": "1800", "observacao": "", "computador": "PC1",
                "data_registro": "2026-07-13T10:30:00",
            }
            maria = {
                "registro_id": "m1", "usuario": "Maria", "origem_registro": "TIMER",
                "projeto": "B", "tipo_atividade": "Atendimento", "descricao": "B",
                "inicio": "2026-07-13T11:00:00", "fim": "2026-07-13T12:00:00",
                "duracao_segundos": "3600", "observacao": "", "computador": "PC2",
                "data_registro": "2026-07-13T12:00:00",
            }
            self._write(root / "Usuario A" / "2026-07.csv", [usuario_a], old_fields)
            self._write(root / "Maria" / "2026-07.csv", [maria])

            self.assertEqual(discover_users(str(root)), ["Maria", "Usuario A"])
            records = read_records(str(root), "Usuario A", date(2026, 7, 13))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].origin, "TIMER")

class CsvReaderAuditTest(unittest.TestCase):
    @staticmethod
    def _write(path: Path, rows: list[dict[str, str]], fields=FIELDS):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

    def test_master_marks_deleted_without_counting_audit_as_task(self):
        from csv_store import AUDIT_FIELDS

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = {
                "registro_id": "r1", "usuario": "Usuario A", "origem_registro": "TIMER",
                "projeto": "A", "tipo_atividade": "Teste", "descricao": "A",
                "inicio": "2026-07-13T10:00:00", "fim": "2026-07-13T10:30:00",
                "duracao_segundos": "1800", "observacao": "", "computador": "PC1",
                "data_registro": "2026-07-13T10:30:00",
            }
            self._write(root / "registros" / "Usuario_A" / "2026-07.csv", [task])
            action = {
                "acao_id": "a1", "registro_id": "r1", "acao": "EXCLUIR",
                "data_hora_acao": "2026-07-13 11:00:00", "usuario_acao": "Usuario A",
                "motivo": "Registro incorreto", "computador": "PC1", "projeto": "A",
                "tipo_atividade": "Teste", "descricao": "A", "inicio": "2026-07-13T10:00:00",
                "fim": "2026-07-13T10:30:00", "duracao_segundos": "1800",
                "duracao_formatada": "00:30:00", "origem_registro": "TIMER",
                "observacao": "", "data_registro": "2026-07-13T10:30:00",
            }
            self._write(
                root / "registros" / "Usuario_A" / "auditoria" / "2026-07.csv",
                [action],
                AUDIT_FIELDS,
            )
            self.assertEqual(discover_users(str(root)), ["Usuario A"])
            records = read_records(str(root), "Usuario A", date(2026, 7, 13))
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0].deleted)
            self.assertEqual(records[0].deletion_reason, "Registro incorreto")


    def test_reads_selected_months_without_loading_unselected_month(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for month in (1, 6, 7):
                folder = root / "registros" / "usuario"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"2026-{month:02d}.csv"
                with path.open("w", newline="", encoding="utf-8-sig") as handle:
                    writer = csv.DictWriter(
                        handle,
                        fieldnames=[
                            "registro_id", "usuario", "projeto", "tipo_atividade",
                            "descricao", "inicio", "fim", "duracao_segundos",
                            "observacao", "computador", "data_registro", "origem_registro",
                        ],
                        delimiter=";",
                    )
                    writer.writeheader()
                    writer.writerow({
                        "registro_id": f"m-{month}",
                        "usuario": "Usuário Teste",
                        "projeto": "Projeto",
                        "tipo_atividade": "Teste",
                        "descricao": "Registro",
                        "inicio": f"2026-{month:02d}-10 08:00:00",
                        "fim": f"2026-{month:02d}-10 09:00:00",
                        "duracao_segundos": "3600",
                        "observacao": "",
                        "computador": "PC",
                        "data_registro": f"2026-{month:02d}-10 09:00:00",
                        "origem_registro": "TIMER",
                    })
            records = read_records_for_months(str(root), "Usuário Teste", 2026, [1, 6])
            self.assertEqual([record.record_id for record in records], ["m-1", "m-6"])



if __name__ == "__main__":
    unittest.main()
