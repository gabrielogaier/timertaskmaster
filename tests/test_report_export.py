import csv
import tempfile
import unittest
import zipfile
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from csv_reader import CsvRecord
from report_export import EXCEL_DURATION_FORMAT, export_csv, export_excel, format_report_duration


class ReportExportTests(unittest.TestCase):
    @staticmethod
    def _record(record_id: str, *, deleted: bool = False, origin: str = "TIMER") -> CsvRecord:
        return CsvRecord(
            record_id=record_id,
            user="Usuário Teste",
            origin=origin,
            project="Projeto Exportação",
            activity_type="Teste",
            description="Validar exportação",
            start=datetime(2026, 7, 13, 8, 0),
            end=datetime(2026, 7, 13, 9, 0),
            duration_seconds=3600,
            observation="Observação",
            computer="PC-TESTE",
            registered_at="2026-07-13 09:00:00",
            source_file="dados-ficticios/2026-07.csv",
            deleted=deleted,
            deletion_reason="Registro incorreto" if deleted else "",
            deleted_at="2026-07-13 10:00:00" if deleted else "",
            deleted_by="Usuário Teste" if deleted else "",
            audit_action_id="acao-1" if deleted else "",
        )


    def test_report_duration_rounds_to_nearest_minute(self):
        self.assertEqual(format_report_duration(round(6.47 * 3600)), "06:28 h")
        self.assertEqual(format_report_duration(round(2.92 * 3600)), "02:55 h")
        self.assertEqual(format_report_duration(26 * 3600 + 5 * 60), "26:05 h")

    def test_csv_contains_filtered_records_and_audit_columns(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "relatorio.csv"
            export_csv(
                target,
                [
                    ("Usuário monitorado", self._record("r1")),
                    ("Usuário monitorado", self._record("r2", deleted=True, origin="MANUAL")),
                ],
            )
            with target.open("r", newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle, delimiter=";"))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["status"], "ATIVO")
            self.assertEqual(rows[1]["status"], "EXCLUÍDO")
            self.assertEqual(rows[1]["motivo_exclusao"], "Registro incorreto")
            self.assertEqual(rows[1]["origem_registro"], "MANUAL")
            self.assertEqual(rows[0]["duracao_formatada"], "01:00 h")

    def test_excel_has_dynamic_dashboard_and_complete_records_table(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "relatorio.xlsx"
            export_excel(
                target,
                [
                    ("Usuário monitorado", self._record("r1")),
                    ("Usuário monitorado", self._record("r2", deleted=True, origin="MANUAL")),
                ],
                date(2026, 7, 13),
                {"projeto": "Todos", "tipo": "Todos", "origem": "Todos", "status": "Todos"},
                generated_at=datetime(2026, 7, 13, 12, 0),
                period_label="Janeiro a Junho de 2026",
            )
            workbook = load_workbook(target, data_only=False)
            self.assertEqual(workbook.sheetnames, ["Dashboard", "Registros"])
            self.assertEqual(len(workbook["Dashboard"]._charts), 3)
            self.assertEqual(workbook["Dashboard"]["B4"].value, "Janeiro a Junho de 2026")
            self.assertEqual(workbook["Registros"].max_row, 3)
            self.assertEqual(workbook["Registros"]["K3"].value, "EXCLUÍDO")
            self.assertEqual(workbook["Registros"]["M3"].value, "Registro incorreto")
            self.assertTrue(workbook["Registros"].column_dimensions["T"].hidden)
            self.assertTrue(workbook["Registros"].column_dimensions["X"].hidden)
            self.assertEqual(workbook["Registros"].tables["tbRegistros"].ref, "A1:X3")
            self.assertIn("SUMPRODUCT", workbook["Dashboard"]["A14"].value)
            self.assertIn("'Registros'!", workbook["Dashboard"]["A14"].value)
            self.assertEqual(workbook["Dashboard"]["A6"].value, "Todos")
            self.assertEqual(workbook["Dashboard"]["C6"].value, "Todos")
            self.assertEqual(workbook["Dashboard"]["E6"].value, "Todos")
            self.assertEqual(workbook["Dashboard"]["G6"].value, "Todos")
            self.assertEqual(workbook["Dashboard"]["E9"].value, "Todos")
            self.assertEqual(len(workbook["Dashboard"].data_validations.dataValidation), 5)
            self.assertTrue(workbook["Dashboard"].column_dimensions["J"].hidden)
            self.assertTrue(workbook["Dashboard"].column_dimensions["Y"].hidden)
            self.assertEqual(workbook.calculation.calcMode, "auto")
            self.assertTrue(workbook.calculation.fullCalcOnLoad)
            self.assertTrue(workbook.calculation.forceFullCalc)

            # Durações são armazenadas como frações de dia e exibidas em [h]:mm,
            # sem horas decimais. Isso preserva soma, filtros e gráficos.
            self.assertEqual(workbook["Registros"]["I2"].value.total_seconds(), 3600)
            self.assertEqual(workbook["Registros"]["I2"].number_format, EXCEL_DURATION_FORMAT)
            self.assertEqual(workbook["Registros"]["T2"].value.total_seconds(), 3600)
            self.assertEqual(workbook["Registros"]["U2"].value, 1)
            self.assertEqual(workbook["Registros"]["V2"].value, 0)
            self.assertEqual(workbook["Registros"]["W2"].value, 0)
            self.assertEqual(workbook["Registros"]["T3"].value.total_seconds(), 0)
            self.assertEqual(workbook["Registros"]["U3"].value, 0)
            self.assertEqual(workbook["Registros"]["V3"].value, 0)
            self.assertEqual(workbook["Registros"]["W3"].value, 1)
            self.assertEqual(workbook["Registros"]["X2"].value, datetime(2026, 7, 13))
            self.assertTrue(workbook["Registros"].column_dimensions["H"].hidden)
            self.assertEqual(workbook["Dashboard"]["A14"].number_format, EXCEL_DURATION_FORMAT)

            # Uma tabela do Excel já contém seu próprio AutoFiltro. A planilha
            # não pode declarar outro AutoFiltro sobre o mesmo intervalo, pois
            # o Excel repara e remove a tabela ao abrir o arquivo.
            with zipfile.ZipFile(target) as archive:
                registros_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
                self.assertNotIn("<autoFilter", registros_xml)
                self.assertIn("<tableParts", registros_xml)


if __name__ == "__main__":
    unittest.main()
