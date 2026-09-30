import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TEST_LOCALAPPDATA = tempfile.mkdtemp(prefix="timertaskmaster-ui-")
os.environ["LOCALAPPDATA"] = _TEST_LOCALAPPDATA

from PySide6.QtCore import QDate, QThreadPool
from PySide6.QtWidgets import QApplication, QMessageBox

import app as combined_app
from app import ExportOptionsDialog, MainWindow
from database import Database
from master_database import MasterDatabase
from timer_app import HistoryDetailsDialog, app_data_dir
from csv_store import append_audit_action, append_record


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_export_options_dialog_opens_without_checkbox_wordwrap_error(self):
        dialog = ExportOptionsDialog(
            None,
            __import__("datetime").date(2026, 7, 13),
            {
                "projeto": "Todos",
                "tipo": "Todos",
                "origem": "Todos",
                "status": "Todos",
            },
        )
        self.assertIn("origem e status", dialog.apply_filters_check.text())
        self.assertTrue(dialog.apply_filters_check.toolTip())
        dialog.close()

    def test_combined_window_keeps_timer_and_adds_management(self):
        db_path = app_data_dir() / "timertask.db"
        timer_db = Database(db_path)
        timer_db.set_setting("user_name", "Usuário Teste")
        timer_db.set_setting("base_folder", str(Path(_TEST_LOCALAPPDATA) / "registros"))
        master_db = MasterDatabase(db_path)

        window = MainWindow(timer_db, master_db)
        tabs = [window.tabs.tabText(index) for index in range(window.tabs.count())]
        self.assertEqual(
            tabs,
            [
                "Dashboard",
                "Timer",
                "Registro manual",
                "Histórico",
                "Cadastros",
                "Usuários monitorados",
                "Configurações",
            ],
        )
        self.assertEqual(len(master_db.list_users()), 1)
        window.force_quit = True
        window.close()

    def test_users_table_stays_open_when_network_folder_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "timertask.db"
            timer_db = Database(db_path)
            master_db = MasterDatabase(db_path)
            master_db.add_user("Gabriel", "Gabriel", r"\\server\\share")

            with patch("app.folder_is_available", return_value=False):
                window = MainWindow(timer_db, master_db)

            self.assertEqual(window.users_table.item(0, 3).text(), "0")
            self.assertEqual(window.users_table.item(0, 4).text(), "Pasta indisponível")
            window.force_quit = True
            window.close()

    def test_timer_tab_refreshes_total_for_current_date(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db_path = root / "timertask.db"
            csv_base = root / "base"
            today = QDate.currentDate()
            today_text = today.toString("yyyy-MM-dd")
            timer_db = Database(db_path)
            timer_db.set_setting("user_name", "Usuário Teste")
            timer_db.set_setting("base_folder", str(csv_base))
            record = {
                    "registro_id": "today-total-ui-1",
                    "usuario": "Usuário Teste",
                    "origem_registro": "TIMER",
                    "projeto": "Projeto UI",
                    "tipo_atividade": "Teste",
                    "descricao": "Registro de hoje",
                    "inicio": f"{today_text} 08:00:00",
                    "fim": f"{today_text} 08:01:30",
                    "duracao_segundos": 90,
                    "duracao_formatada": "00:01:30",
                    "observacao": "",
                    "computador": "PC",
                    "data_registro": f"{today_text} 08:01:30",
            }
            append_record(str(csv_base), record)
            timer_db.add_task_record(record)
            timer_db.mark_task_synced(record["registro_id"])
            master_db = MasterDatabase(db_path)
            window = MainWindow(timer_db, master_db)
            window.tabs.setCurrentWidget(window.dashboard_tab)
            window.history_date.setDate(today.addDays(-1))
            window.today_total_label.setText("Total registrado hoje: 06:22:27")

            window.tabs.setCurrentWidget(window.timer_tab)

            self.assertEqual(window.history_date.date(), today)
            self.assertEqual(
                window.today_total_label.text(),
                "Total registrado hoje: 00:01:30",
            )
            window.force_quit = True
            window.close()

    def test_double_click_opens_complete_history_details(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db_path = root / "timertask.db"
            csv_base = root / "base"
            timer_db = Database(db_path)
            timer_db.set_setting("user_name", "Usuário Teste")
            timer_db.set_setting("base_folder", str(csv_base))
            record = {
                    "registro_id": "history-details-1",
                    "usuario": "Usuário Teste",
                    "origem_registro": "MANUAL",
                    "projeto": "Projeto Detalhes",
                    "tipo_atividade": "Documentação",
                    "descricao": "Descrição completa da atividade",
                    "inicio": "2026-08-03 08:00:00",
                    "fim": "2026-08-03 09:15:00",
                    "duracao_segundos": 4500,
                    "duracao_formatada": "01:15:00",
                    "observacao": "Observação completa do registro",
                    "computador": "PC-DETALHES",
                    "data_registro": "2026-08-03 09:15:01",
            }
            append_record(str(csv_base), record)
            timer_db.add_task_record(record)
            timer_db.mark_task_synced(record["registro_id"])
            master_db = MasterDatabase(db_path)
            window = MainWindow(timer_db, master_db)
            window.history_date.setDate(QDate(2026, 8, 3))
            window.refresh_history()

            dialog = HistoryDetailsDialog(window.history_rows[0])
            self.assertEqual(
                set(dialog.value_labels),
                {key for key, _label in HistoryDetailsDialog.DETAIL_FIELDS},
            )
            self.assertEqual(dialog.value_labels["status"].text(), "ATIVO")
            self.assertEqual(
                dialog.value_labels["descricao"].text(),
                "Descrição completa da atividade",
            )
            self.assertEqual(
                dialog.value_labels["observacao"].text(),
                "Observação completa do registro",
            )
            dialog.close()

            deleted_dialog = HistoryDetailsDialog(
                {
                    **window.history_rows[0],
                    "excluido": "1",
                    "usuario_exclusao": "Gestor Teste",
                    "data_exclusao": "2026-08-03 10:00:00",
                    "motivo_exclusao": "Registro duplicado",
                    "acao_id_exclusao": "audit-details-1",
                }
            )
            self.assertEqual(deleted_dialog.value_labels["status"].text(), "EXCLUÍDO")
            self.assertEqual(
                deleted_dialog.value_labels["motivo_exclusao"].text(),
                "Registro duplicado",
            )
            deleted_dialog.close()

            with patch.object(HistoryDetailsDialog, "exec", return_value=0) as modal_exec:
                window.history_table.cellDoubleClicked.emit(0, 4)
            modal_exec.assert_called_once_with()

            window.force_quit = True
            window.close()

    def test_completed_record_is_saved_locally_without_network_access(self):
        from timer_app import MainWindow

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db = Database(root / "timertask.db")
            db.set_setting("user_name", "Usuário Teste")
            db.set_setting("base_folder", r"\\servidor-offline\registros")
            window = MainWindow(db)
            record = {
                "registro_id": "offline-save-1",
                "usuario": "Usuário Teste",
                "origem_registro": "TIMER",
                "projeto": "Projeto Offline",
                "tipo_atividade": "Teste",
                "descricao": "Salvar sem rede",
                "inicio": "2026-08-03 08:00:00",
                "fim": "2026-08-03 09:00:00",
                "duracao_segundos": 3600,
                "duracao_formatada": "01:00:00",
                "observacao": "",
                "computador": "PC",
                "data_registro": "2026-08-03 09:00:00",
            }

            with patch("timer_app.append_record", side_effect=OSError("rede indisponível")) as append_record:
                result = window._persist_completed_record(record)
                self.assertIsNone(result)
                self.assertTrue(QThreadPool.globalInstance().waitForDone(2000))
                self.qt_app.processEvents()
                append_record.assert_called_once()

            pending = db.list_task_records(pending_only=True)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["record_id"], "offline-save-1")
            self.assertEqual(pending[0]["status"], "FALHA")
            self.assertEqual(pending[0]["attempts"], 1)
            window.force_quit = True
            window.close()

    def test_deleted_record_is_red_and_not_counted_in_dashboard_or_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db_path = root / "timertask.db"
            csv_base = root / "base"
            timer_db = Database(db_path)
            timer_db.set_setting("user_name", "Usuário Teste")
            timer_db.set_setting("base_folder", str(csv_base))
            record = {
                "registro_id": "deleted-ui-1",
                "usuario": "Usuário Teste",
                "origem_registro": "TIMER",
                "projeto": "Projeto UI",
                "tipo_atividade": "Teste",
                "descricao": "Registro incorreto",
                "inicio": "2026-07-13 08:00:00",
                "fim": "2026-07-13 09:00:00",
                "duracao_segundos": 3600,
                "duracao_formatada": "01:00:00",
                "observacao": "",
                "computador": "PC",
                "data_registro": "2026-07-13 09:00:00",
            }
            action = {
                "acao_id": "deleted-ui-action-1",
                "registro_id": "deleted-ui-1",
                "acao": "EXCLUIR",
                "data_hora_acao": "2026-07-13 10:00:00",
                "usuario_acao": "Usuário Teste",
                "motivo": "Timer iniciado por engano",
                "computador": "PC",
                "projeto": "Projeto UI",
                "tipo_atividade": "Teste",
                "descricao": "Registro incorreto",
                "inicio": "2026-07-13 08:00:00",
                "fim": "2026-07-13 09:00:00",
                "duracao_segundos": 3600,
                "duracao_formatada": "01:00:00",
                "origem_registro": "TIMER",
                "observacao": "",
                "data_registro": "2026-07-13 09:00:00",
            }
            append_record(str(csv_base), record)
            append_audit_action(str(csv_base), action)
            timer_db.add_task_record(record)
            timer_db.mark_task_synced(record["registro_id"])
            timer_db.add_audit_action(action)
            timer_db.mark_audit_synced(action["acao_id"])
            master_db = MasterDatabase(db_path)
            window = MainWindow(timer_db, master_db)
            window.date_edit.setDate(QDate(2026, 7, 13))
            window.refresh_dashboard()
            self.assertEqual(window.total_hours_label.text(), "00:00:00")
            self.assertEqual(window.records_label.text(), "0")
            self.assertEqual(window.deleted_label.text(), "1")
            user_item = window.dashboard_tree.topLevelItem(0)
            project_item = user_item.child(0)
            record_item = project_item.child(0)
            self.assertEqual(record_item.text(4), "EXCLUÍDO")

            window.history_date.setDate(QDate(2026, 7, 13))
            window.history_status_filter.setCurrentText("Excluídos")
            window.refresh_history()
            self.assertEqual(window.history_table.rowCount(), 1)
            self.assertEqual(window.history_table.item(0, 7).text(), "EXCLUÍDO")
            self.assertEqual(window.history_total_label.text(), "Total válido: 00:00:00")
            window.force_quit = True
            window.close()


    def test_delete_action_preserves_original_and_creates_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db_path = root / "timertask.db"
            csv_base = root / "base"
            timer_db = Database(db_path)
            timer_db.set_setting("user_name", "Usuário Teste")
            timer_db.set_setting("base_folder", str(csv_base))
            record = {
                "registro_id": "delete-flow-1",
                "usuario": "Usuário Teste",
                "origem_registro": "MANUAL",
                "projeto": "Projeto Fluxo",
                "tipo_atividade": "Documentação",
                "descricao": "Lançamento incorreto",
                "inicio": "2026-07-13 13:00:00",
                "fim": "2026-07-13 14:00:00",
                "duracao_segundos": 3600,
                "duracao_formatada": "01:00:00",
                "observacao": "",
                "computador": "PC",
                "data_registro": "2026-07-13 14:00:00",
            }
            original_path = append_record(str(csv_base), record)
            timer_db.add_task_record(record)
            timer_db.mark_task_synced(record["registro_id"])
            master_db = MasterDatabase(db_path)
            window = MainWindow(timer_db, master_db)
            window.history_date.setDate(QDate(2026, 7, 13))
            window.refresh_history()
            self.assertEqual(window.history_table.rowCount(), 1)
            window.history_table.selectRow(0)

            with (
                patch("timer_app.QInputDialog.getMultiLineText", return_value=("Registro duplicado", True)),
                patch("timer_app.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes),
                patch("timer_app.QMessageBox.information"),
            ):
                window.delete_selected_history_record()

            self.assertTrue(original_path.exists())
            import csv
            with original_path.open("r", newline="", encoding="utf-8-sig") as handle:
                self.assertEqual(len(list(csv.DictReader(handle, delimiter=";"))), 1)
            actions = timer_db.list_audit_actions()
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["status"], "SINCRONIZADO")
            self.assertEqual(actions[0]["data"]["motivo"], "Registro duplicado")
            window.history_status_filter.setCurrentText("Excluídos")
            window.refresh_history()
            self.assertEqual(window.history_table.rowCount(), 1)
            self.assertEqual(window.history_total_label.text(), "Total válido: 00:00:00")
            window.force_quit = True
            window.close()

    def test_dashboard_export_creates_complete_excel_with_initial_filters(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db_path = root / "timertask.db"
            csv_base = root / "base"
            target = root / "relatorio-dashboard.xlsx"
            timer_db = Database(db_path)
            timer_db.set_setting("user_name", "Usuário Teste")
            timer_db.set_setting("base_folder", str(csv_base))
            append_record(
                str(csv_base),
                {
                    "registro_id": "export-ui-1",
                    "usuario": "Usuário Teste",
                    "origem_registro": "TIMER",
                    "projeto": "Projeto Exportação",
                    "tipo_atividade": "Teste",
                    "descricao": "Validar botão exportar",
                    "inicio": "2026-07-13 08:00:00",
                    "fim": "2026-07-13 09:00:00",
                    "duracao_segundos": 3600,
                    "duracao_formatada": "01:00:00",
                    "observacao": "OK",
                    "computador": "PC",
                    "data_registro": "2026-07-13 09:00:00",
                },
            )
            append_record(
                str(csv_base),
                {
                    "registro_id": "export-ui-2",
                    "usuario": "Usuário Teste",
                    "origem_registro": "TIMER",
                    "projeto": "Outro Projeto",
                    "tipo_atividade": "Atendimento",
                    "descricao": "Não deve entrar no filtro",
                    "inicio": "2026-07-13 10:00:00",
                    "fim": "2026-07-13 10:30:00",
                    "duracao_segundos": 1800,
                    "duracao_formatada": "00:30:00",
                    "observacao": "",
                    "computador": "PC",
                    "data_registro": "2026-07-13 10:30:00",
                },
            )
            master_db = MasterDatabase(db_path)
            window = MainWindow(timer_db, master_db)
            self.assertEqual(window.export_button.text(), "Exportar")
            window.date_edit.setDate(QDate(2026, 7, 13))
            window.refresh_dashboard()
            window.project_filter.setCurrentText("Projeto Exportação")

            with (
                patch.object(
                    window,
                    "_get_export_options",
                    return_value={
                        "mode": "dashboard",
                        "year": 2026,
                        "months": [7],
                        "apply_dashboard_filters": True,
                        "format": "xlsx",
                    },
                ),
                patch(
                    "app.QFileDialog.getSaveFileName",
                    return_value=(str(target), "Excel completo (*.xlsx)"),
                ),
                patch("app.QMessageBox.information"),
            ):
                window.export_dashboard()

            self.assertTrue(target.exists())
            from openpyxl import load_workbook
            workbook = load_workbook(target, read_only=True)
            self.assertEqual(workbook.sheetnames, ["Dashboard", "Registros"])
            # O filtro atual abre selecionado no Dashboard, mas a tabela leva
            # todos os registros da data para permitir trocar o recorte no Excel.
            self.assertEqual(workbook["Dashboard"]["C6"].value, "Projeto Exportação")
            self.assertEqual(workbook["Registros"].max_row, 3)
            self.assertEqual(workbook["Registros"]["C2"].value, "Projeto Exportação")
            self.assertEqual(workbook["Registros"]["C3"].value, "Outro Projeto")
            workbook.close()
            window.force_quit = True
            window.close()

    def test_dashboard_export_can_select_multiple_months(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db_path = root / "timertask.db"
            csv_base = root / "base"
            target = root / "relatorio-semestral.xlsx"
            timer_db = Database(db_path)
            timer_db.set_setting("user_name", "Usuário Teste")
            timer_db.set_setting("base_folder", str(csv_base))
            for record_id, month in (("period-1", 1), ("period-2", 6), ("period-3", 7)):
                append_record(
                    str(csv_base),
                    {
                        "registro_id": record_id,
                        "usuario": "Usuário Teste",
                        "origem_registro": "TIMER",
                        "projeto": "Projeto Período",
                        "tipo_atividade": "Teste",
                        "descricao": "Registro mensal",
                        "inicio": f"2026-{month:02d}-13 08:00:00",
                        "fim": f"2026-{month:02d}-13 09:00:00",
                        "duracao_segundos": 3600,
                        "duracao_formatada": "01:00:00",
                        "observacao": "",
                        "computador": "PC",
                        "data_registro": f"2026-{month:02d}-13 09:00:00",
                    },
                )
            master_db = MasterDatabase(db_path)
            window = MainWindow(timer_db, master_db)

            with (
                patch.object(
                    window,
                    "_get_export_options",
                    return_value={
                        "mode": "period",
                        "year": 2026,
                        "months": [1, 2, 3, 4, 5, 6],
                        "apply_dashboard_filters": False,
                        "format": "xlsx",
                    },
                ),
                patch(
                    "app.QFileDialog.getSaveFileName",
                    return_value=(str(target), "Excel completo (*.xlsx)"),
                ),
                patch("app.QMessageBox.information"),
            ):
                window.export_dashboard()

            from openpyxl import load_workbook
            workbook = load_workbook(target, read_only=True)
            self.assertEqual(workbook["Registros"].max_row, 3)
            self.assertEqual(workbook["Dashboard"]["B4"].value, "Janeiro a Junho de 2026")
            workbook.close()
            window.force_quit = True
            window.close()

    def test_upgrade_backup_copies_existing_database(self):
        source_dir = Path(tempfile.mkdtemp(prefix="timertaskmaster-backup-"))
        db_path = source_dir / "timertask.db"
        db_path.write_bytes(b"database-test")
        original_app_data_dir = combined_app.app_data_dir
        try:
            combined_app.app_data_dir = lambda: source_dir
            backup_dir = combined_app.backup_existing_timer_data()
            self.assertIsNotNone(backup_dir)
            self.assertEqual((backup_dir / "timertask.db").read_bytes(), b"database-test")
            self.assertIsNone(combined_app.backup_existing_timer_data())
        finally:
            combined_app.app_data_dir = original_app_data_dir


if __name__ == "__main__":
    unittest.main()
