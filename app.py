from __future__ import annotations

import logging
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, QLockFile, QTimer, Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from csv_reader import (
    CsvRecord,
    apply_audit_actions_to_records,
    count_csv_files,
    discover_users,
    format_duration,
    read_records,
    read_records_for_months,
)
from database import Database
from master_database import MasterDatabase
from report_export import export_csv, export_excel
from timer_app import (
    LOG_PATH,
    MainWindow as TimerMainWindow,
    app_data_dir,
    exception_hook,
    load_app_icon,
)

APP_NAME = "Timer Task Master"

MONTH_NAMES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


class ExportOptionsDialog(QDialog):
    """Escolhe entre o estado atual do Dashboard e um período mensal."""

    def __init__(
        self,
        parent: QWidget,
        dashboard_date: date,
        dashboard_filters: dict[str, str],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exportar relatório")
        self.setMinimumWidth(560)
        self.dashboard_date = dashboard_date
        self.dashboard_filters = dashboard_filters

        layout = QVBoxLayout(self)
        self.current_radio = QRadioButton("Usar exatamente os filtros atuais do Dashboard")
        self.current_radio.setChecked(True)
        layout.addWidget(self.current_radio)

        current_summary = QLabel(
            f"Data: {dashboard_date:%d/%m/%Y} | "
            f"Projeto: {dashboard_filters.get('projeto', 'Todos')} | "
            f"Tipo: {dashboard_filters.get('tipo', 'Todos')} | "
            f"Origem: {dashboard_filters.get('origem', 'Todos')} | "
            f"Status: {dashboard_filters.get('status', 'Todos')}"
        )
        current_summary.setWordWrap(True)
        current_summary.setStyleSheet("color: #667085; padding-left: 22px;")
        layout.addWidget(current_summary)

        self.period_radio = QRadioButton("Selecionar ano e meses")
        layout.addWidget(self.period_radio)

        self.period_group = QGroupBox("Período do relatório")
        period_layout = QVBoxLayout(self.period_group)
        year_row = QHBoxLayout()
        year_row.addWidget(QLabel("Ano:"))
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2000, 2100)
        self.year_spin.setValue(dashboard_date.year)
        year_row.addWidget(self.year_spin)
        year_row.addStretch(1)
        period_layout.addLayout(year_row)

        month_grid = QGridLayout()
        self.month_checks: list[QCheckBox] = []
        for index, month_name in enumerate(MONTH_NAMES, start=1):
            check = QCheckBox(month_name)
            check.setChecked(index == dashboard_date.month)
            self.month_checks.append(check)
            month_grid.addWidget(check, (index - 1) // 3, (index - 1) % 3)
        period_layout.addLayout(month_grid)

        month_buttons = QHBoxLayout()
        select_all = QPushButton("Ano inteiro")
        select_all.clicked.connect(lambda _checked=False: self._set_all_months(True))
        clear_all = QPushButton("Limpar meses")
        clear_all.clicked.connect(lambda _checked=False: self._set_all_months(False))
        month_buttons.addWidget(select_all)
        month_buttons.addWidget(clear_all)
        month_buttons.addStretch(1)
        period_layout.addLayout(month_buttons)

        self.apply_filters_check = QCheckBox(
            "Usar os filtros de projeto, tipo, origem e status\n"
            "como seleção inicial do Dashboard exportado"
        )
        self.apply_filters_check.setChecked(False)
        self.apply_filters_check.setToolTip(
            "No Excel, a tabela Registros continua completa para o período. "
            "No CSV, somente as linhas que atendem aos filtros são exportadas."
        )
        period_layout.addWidget(self.apply_filters_check)
        layout.addWidget(self.period_group)

        format_group = QGroupBox("Formato")
        format_layout = QFormLayout(format_group)
        self.format_combo = QComboBox()
        self.format_combo.addItem("Excel completo (.xlsx)", "xlsx")
        self.format_combo.addItem("CSV detalhado (.csv)", "csv")
        format_layout.addRow("Exportar como:", self.format_combo)
        layout.addWidget(format_group)

        format_note = QLabel(
            "Excel: cria Dashboard + Registros completos para a data ou período; "
            "os filtros ficam editáveis no próprio arquivo."
        )
        format_note.setWordWrap(True)
        format_note.setStyleSheet("color: #667085;")
        layout.addWidget(format_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Escolher local e exportar")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.current_radio.toggled.connect(self._update_period_enabled)
        self.period_radio.toggled.connect(self._update_period_enabled)
        self._update_period_enabled()

    def _set_all_months(self, checked: bool) -> None:
        for month_check in self.month_checks:
            month_check.setChecked(checked)

    def _update_period_enabled(self) -> None:
        self.period_group.setEnabled(self.period_radio.isChecked())

    def _validate_and_accept(self) -> None:
        if self.period_radio.isChecked() and not self.selected_months():
            QMessageBox.warning(self, APP_NAME, "Selecione ao menos um mês para exportar.")
            return
        self.accept()

    def selected_months(self) -> list[int]:
        return [index for index, check in enumerate(self.month_checks, start=1) if check.isChecked()]

    def options(self) -> dict[str, object]:
        return {
            "mode": "period" if self.period_radio.isChecked() else "dashboard",
            "year": self.year_spin.value(),
            "months": self.selected_months(),
            "apply_dashboard_filters": self.apply_filters_check.isChecked(),
            "format": str(self.format_combo.currentData()),
        }


def backup_existing_timer_data() -> Path | None:
    """Cria um backup único do banco anterior antes da primeira abertura do Master."""
    data_dir = app_data_dir()
    database_path = data_dir / "timertask.db"
    marker = data_dir / "master_upgrade_backup.done"
    if not database_path.exists() or marker.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = data_dir / "backups" / f"antes-do-master-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for name in ("timertask.db", "timertask.db-wal", "timertask.db-shm"):
        source = data_dir / name
        if source.is_file():
            shutil.copy2(source, backup_dir / name)
    marker.write_text(str(backup_dir), encoding="utf-8")
    return backup_dir


class MainWindow(TimerMainWindow):
    """Timer Task completo com o módulo adicional de gestão."""

    def __init__(self, db: Database, master_db: MasterDatabase) -> None:
        self.master_db = master_db
        self.loaded_records: dict[int, list[CsvRecord]] = {}
        self.user_errors: dict[int, str] = {}
        super().__init__(db)

        self.setWindowTitle(APP_NAME)
        self.resize(1180, 760)

        self.dashboard_tab = QWidget()
        self.users_tab = QWidget()
        self.tabs.insertTab(0, self.dashboard_tab, "Dashboard")
        # Mantém Configurações como a última aba.
        settings_index = self.tabs.indexOf(self.settings_tab)
        self.tabs.insertTab(settings_index, self.users_tab, "Usuários monitorados")

        self._build_dashboard_tab()
        self._build_users_tab()
        self._append_management_settings()
        self._ensure_own_user_monitored()
        self.refresh_users_table()
        self.refresh_dashboard()

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_dashboard)
        self._load_management_settings()
        self._apply_auto_refresh()
        self._add_dashboard_tray_action()

    def _append_management_settings(self) -> None:
        layout = self.settings_tab.layout()
        if layout is None:
            layout = QVBoxLayout(self.settings_tab)

        group = QGroupBox("Atualização do dashboard de gestão")
        form = QFormLayout(group)
        self.auto_refresh_check = QCheckBox("Atualizar automaticamente")
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(15, 3600)
        self.interval_spin.setSuffix(" segundos")
        self.auto_refresh_check.toggled.connect(
            lambda _checked: self.save_management_settings()
        )
        self.interval_spin.valueChanged.connect(
            lambda _value: self.save_management_settings()
        )
        form.addRow(self.auto_refresh_check)
        form.addRow("Intervalo:", self.interval_spin)

        info_group = QGroupBox("Compatibilidade e dados")
        info_form = QFormLayout(info_group)
        info_form.addRow("Banco local preservado:", QLabel(str(app_data_dir() / "timertask.db")))
        info_form.addRow("Log:", QLabel(str(LOG_PATH)))
        note = QLabel(
            "O Master utiliza o mesmo banco e a mesma pasta local do Timer Task. "
            "Projetos, tipos, timer ativo, pendências e configurações anteriores são preservados."
        )
        note.setWordWrap(True)
        info_form.addRow(note)

        insert_at = max(0, layout.count() - 1)
        layout.insertWidget(insert_at, group)
        layout.insertWidget(insert_at + 1, info_group)

    def save_settings(self) -> None:
        """Salva as configurações pessoais e mantém o próprio usuário no dashboard."""
        super().save_settings()
        if hasattr(self, "master_db"):
            self._ensure_own_user_monitored()
            if hasattr(self, "users_table"):
                self.refresh_users_table()
                self.refresh_dashboard()

    def _ensure_own_user_monitored(self) -> None:
        """Inclui automaticamente o próprio usuário configurado, sem duplicar."""
        user_name = self.db.get_setting("user_name").strip()
        base_folder = self.db.get_setting("base_folder").strip()
        if not user_name or not base_folder:
            return
        normalized = str(Path(base_folder).expanduser())
        for user in self.master_db.list_users():
            if (
                str(user["source_user"]).casefold() == user_name.casefold()
                and str(Path(str(user["source_folder"])).expanduser()).casefold() == normalized.casefold()
            ):
                return
        try:
            self.master_db.add_user(user_name, user_name, normalized)
        except Exception as exc:
            logging.info("Não foi necessário cadastrar o próprio usuário no dashboard: %s", exc)

    def _load_management_settings(self) -> None:
        enabled = self.master_db.get_setting("master_auto_refresh", "1") == "1"
        try:
            interval = int(self.master_db.get_setting("master_refresh_interval_seconds", "60") or 60)
        except ValueError:
            interval = 60
        self.auto_refresh_check.blockSignals(True)
        self.interval_spin.blockSignals(True)
        self.auto_refresh_check.setChecked(enabled)
        self.interval_spin.setValue(max(15, min(3600, interval)))
        self.auto_refresh_check.blockSignals(False)
        self.interval_spin.blockSignals(False)

    def save_management_settings(self) -> None:
        self.master_db.set_setting(
            "master_auto_refresh", "1" if self.auto_refresh_check.isChecked() else "0"
        )
        self.master_db.set_setting(
            "master_refresh_interval_seconds", str(self.interval_spin.value())
        )
        self._apply_auto_refresh()

    def _apply_auto_refresh(self) -> None:
        if not hasattr(self, "auto_refresh_timer"):
            return
        self.auto_refresh_timer.stop()
        if self.auto_refresh_check.isChecked():
            self.auto_refresh_timer.start(self.interval_spin.value() * 1000)

    def _add_dashboard_tray_action(self) -> None:
        menu = self.tray.contextMenu()
        if menu is None:
            return
        refresh_action = QAction("Atualizar dashboard", self)
        refresh_action.triggered.connect(lambda _checked=False: self.refresh_dashboard())
        existing = menu.actions()
        if existing:
            menu.insertAction(existing[-1], refresh_action)
        else:
            menu.addAction(refresh_action)

    def _build_dashboard_tab(self) -> None:
        layout = QVBoxLayout(self.dashboard_tab)
        layout.setContentsMargins(20, 18, 20, 18)

        filters = QHBoxLayout()
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.dateChanged.connect(lambda _value: self.refresh_dashboard())

        self.project_filter = QComboBox()
        self.project_filter.addItem("Todos")
        self.project_filter.currentTextChanged.connect(lambda _value: self.populate_dashboard_tree())
        self.activity_filter = QComboBox()
        self.activity_filter.addItem("Todos")
        self.activity_filter.currentTextChanged.connect(lambda _value: self.populate_dashboard_tree())
        self.origin_filter = QComboBox()
        self.origin_filter.addItems(["Todos", "TIMER", "MANUAL"])
        self.origin_filter.currentTextChanged.connect(lambda _value: self.populate_dashboard_tree())
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Todos", "Ativos", "Excluídos"])
        self.status_filter.currentTextChanged.connect(lambda _value: self.populate_dashboard_tree())

        refresh_button = QPushButton("Atualizar")
        refresh_button.clicked.connect(lambda _checked=False: self.refresh_dashboard())
        self.export_button = QPushButton("Exportar")
        self.export_button.clicked.connect(lambda _checked=False: self.export_dashboard())
        expand_button = QPushButton("Expandir usuários")
        expand_button.clicked.connect(lambda _checked=False: self.expand_users())
        collapse_button = QPushButton("Recolher")
        collapse_button.clicked.connect(lambda: self.dashboard_tree.collapseAll())

        filters.addWidget(QLabel("Data:"))
        filters.addWidget(self.date_edit)
        filters.addSpacing(12)
        filters.addWidget(QLabel("Projeto:"))
        filters.addWidget(self.project_filter, 1)
        filters.addWidget(QLabel("Tipo:"))
        filters.addWidget(self.activity_filter, 1)
        filters.addWidget(QLabel("Origem:"))
        filters.addWidget(self.origin_filter)
        filters.addWidget(QLabel("Status:"))
        filters.addWidget(self.status_filter)
        filters.addWidget(refresh_button)
        filters.addWidget(self.export_button)
        filters.addWidget(expand_button)
        filters.addWidget(collapse_button)
        layout.addLayout(filters)

        cards = QHBoxLayout()
        self.monitored_label = self._metric_card("Usuários monitorados", "0")
        self.total_hours_label = self._metric_card("Horas válidas", "00:00:00")
        self.records_label = self._metric_card("Registros", "0")
        self.manual_label = self._metric_card("Registros manuais", "0")
        self.deleted_label = self._metric_card("Registros excluídos", "0")
        for widget in (
            self.monitored_label.parentWidget(),
            self.total_hours_label.parentWidget(),
            self.records_label.parentWidget(),
            self.manual_label.parentWidget(),
            self.deleted_label.parentWidget(),
        ):
            cards.addWidget(widget)
        layout.addLayout(cards)

        self.dashboard_tree = QTreeWidget()
        self.dashboard_tree.setColumnCount(9)
        self.dashboard_tree.setHeaderLabels(
            [
                "Usuário / Projeto / Atividade",
                "Tempo válido",
                "Registros",
                "Origem",
                "Status",
                "Início",
                "Fim",
                "Tipo",
                "Observação",
            ]
        )
        self.dashboard_tree.setAlternatingRowColors(True)
        self.dashboard_tree.setRootIsDecorated(True)
        self.dashboard_tree.setUniformRowHeights(False)
        self.dashboard_tree.setColumnWidth(0, 290)
        self.dashboard_tree.setColumnWidth(1, 95)
        self.dashboard_tree.setColumnWidth(2, 80)
        self.dashboard_tree.setColumnWidth(3, 90)
        self.dashboard_tree.setColumnWidth(4, 95)
        self.dashboard_tree.setColumnWidth(5, 80)
        self.dashboard_tree.setColumnWidth(6, 80)
        self.dashboard_tree.setColumnWidth(7, 145)
        self.dashboard_tree.setColumnWidth(8, 260)
        layout.addWidget(self.dashboard_tree, 1)

        self.dashboard_status = QLabel("")
        self.dashboard_status.setStyleSheet("color: #667085;")
        layout.addWidget(self.dashboard_status)

    def _metric_card(self, title: str, initial_value: str) -> QLabel:
        group = QGroupBox(title)
        group_layout = QVBoxLayout(group)
        value = QLabel(initial_value)
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value.setStyleSheet("font-size: 24px; font-weight: 700; padding: 8px;")
        group_layout.addWidget(value)
        value._metric_group = group
        return value

    def _build_users_tab(self) -> None:
        layout = QVBoxLayout(self.users_tab)
        layout.setContentsMargins(20, 18, 20, 18)

        info = QLabel(
            "Adicione a pasta que contém os CSVs do usuário. O nome é identificado pela coluna usuario dos registros. "
            "A pasta pode ser a base geral, a pasta registros\\usuario ou outra pasta que contenha os CSVs."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.users_table = QTableWidget(0, 5)
        self.users_table.setHorizontalHeaderLabels(["Nome detectado", "Pasta monitorada", "Ativo", "CSV", "Status"])
        self.users_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.users_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.users_table.setColumnWidth(0, 190)
        self.users_table.setColumnWidth(1, 500)
        self.users_table.setColumnWidth(2, 70)
        self.users_table.setColumnWidth(3, 60)
        self.users_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.users_table, 1)

        buttons = QHBoxLayout()
        add_button = QPushButton("Adicionar pasta de usuário")
        change_button = QPushButton("Alterar pasta")
        detect_button = QPushButton("Redetectar nome")
        toggle_button = QPushButton("Ativar / desativar")
        remove_button = QPushButton("Remover")
        refresh_button = QPushButton("Atualizar lista")
        add_button.clicked.connect(lambda _checked=False: self.add_user_folder())
        change_button.clicked.connect(lambda _checked=False: self.change_user_folder())
        detect_button.clicked.connect(lambda _checked=False: self.redetect_user())
        toggle_button.clicked.connect(lambda _checked=False: self.toggle_selected_user())
        remove_button.clicked.connect(lambda _checked=False: self.remove_selected_user())
        refresh_button.clicked.connect(lambda _checked=False: self.refresh_users_table())
        for button in (add_button, change_button, detect_button, toggle_button, remove_button):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(refresh_button)
        layout.addLayout(buttons)

    def _selected_user_row(self) -> tuple[int, dict[str, object]] | None:
        row = self.users_table.currentRow()
        users = self.master_db.list_users()
        if row < 0 or row >= len(users):
            QMessageBox.information(self, APP_NAME, "Selecione um usuário na tabela.")
            return None
        return row, users[row]

    def _choose_folder_and_user(self, initial: str = "") -> tuple[str, str] | None:
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta dos registros", initial)
        if not folder:
            return None
        detected = discover_users(folder)
        if not detected:
            QMessageBox.warning(
                self,
                APP_NAME,
                "Nenhum nome de usuário foi encontrado nos CSVs dessa pasta. "
                "Selecione uma pasta que já contenha registros do Timer Task.",
            )
            return None
        if len(detected) == 1:
            return folder, detected[0]
        name, accepted = QInputDialog.getItem(
            self,
            "Usuário detectado",
            "A pasta contém mais de um usuário. Selecione qual deseja monitorar:",
            detected,
            0,
            False,
        )
        return (folder, name) if accepted and name else None

    def add_user_folder(self) -> None:
        selected = self._choose_folder_and_user()
        if not selected:
            return
        folder, name = selected
        try:
            self.master_db.add_user(name, name, folder)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Não foi possível adicionar o usuário:\n{exc}")
            return
        self.refresh_users_table()
        self.refresh_dashboard()

    def change_user_folder(self) -> None:
        selected_row = self._selected_user_row()
        if not selected_row:
            return
        _, user = selected_row
        selected = self._choose_folder_and_user(str(user["source_folder"]))
        if not selected:
            return
        folder, name = selected
        try:
            self.master_db.update_user_folder(int(user["id"]), name, name, folder)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Não foi possível alterar a pasta:\n{exc}")
            return
        self.refresh_users_table()
        self.refresh_dashboard()

    def redetect_user(self) -> None:
        selected_row = self._selected_user_row()
        if not selected_row:
            return
        _, user = selected_row
        detected = discover_users(str(user["source_folder"]))
        if not detected:
            QMessageBox.warning(self, APP_NAME, "Nenhum usuário foi encontrado na pasta configurada.")
            return
        current = str(user["source_user"])
        index = detected.index(current) if current in detected else 0
        name, accepted = QInputDialog.getItem(
            self,
            "Redetectar usuário",
            "Selecione o usuário associado a esta pasta:",
            detected,
            index,
            False,
        )
        if accepted and name:
            self.master_db.update_user_folder(int(user["id"]), name, name, str(user["source_folder"]))
            self.refresh_users_table()
            self.refresh_dashboard()

    def toggle_selected_user(self) -> None:
        selected_row = self._selected_user_row()
        if not selected_row:
            return
        _, user = selected_row
        self.master_db.set_user_active(int(user["id"]), not bool(user["active"]))
        self.refresh_users_table()
        self.refresh_dashboard()

    def remove_selected_user(self) -> None:
        selected_row = self._selected_user_row()
        if not selected_row:
            return
        _, user = selected_row
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"Remover {user['display_name']} do monitoramento?\nOs CSVs não serão alterados.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.master_db.delete_user(int(user["id"]))
            self.refresh_users_table()
            self.refresh_dashboard()

    def refresh_users_table(self) -> None:
        users = self.master_db.list_users()
        self.users_table.setRowCount(len(users))
        for row, user in enumerate(users):
            folder = str(user["source_folder"])
            path = Path(folder)
            file_count = count_csv_files(folder) if path.is_dir() else 0
            status = "OK" if path.is_dir() else "Pasta indisponível"
            values = [
                str(user["display_name"]),
                folder,
                "Sim" if bool(user["active"]) else "Não",
                str(file_count),
                status,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if status != "OK" and column == 4:
                    item.setForeground(QColor("#b42318"))
                self.users_table.setItem(row, column, item)

    def refresh_dashboard(self) -> None:
        selected = self.date_edit.date().toPython()
        self.loaded_records.clear()
        self.user_errors.clear()
        users = self.master_db.list_users(active_only=True)
        all_projects: set[str] = set()
        all_types: set[str] = set()

        for user in users:
            user_id = int(user["id"])
            try:
                records = read_records(
                    str(user["source_folder"]),
                    str(user["source_user"]),
                    selected,
                )
                local_actions = [item["data"] for item in self.db.list_audit_actions()]
                records = apply_audit_actions_to_records(records, local_actions)
                self.loaded_records[user_id] = records
                all_projects.update(record.project for record in records)
                all_types.update(record.activity_type for record in records)
            except Exception as exc:
                logging.exception("Falha ao ler os registros de %s", user["display_name"])
                self.loaded_records[user_id] = []
                self.user_errors[user_id] = str(exc)

        self._replace_combo_items(self.project_filter, ["Todos", *sorted(all_projects, key=str.casefold)])
        self._replace_combo_items(self.activity_filter, ["Todos", *sorted(all_types, key=str.casefold)])
        self.populate_dashboard_tree()
        self.refresh_users_table()
        self.dashboard_status.setText(
            f"Atualizado em {datetime.now():%d/%m/%Y %H:%M:%S}. "
            f"Data consultada: {selected:%d/%m/%Y}."
        )

    def _replace_combo_items(self, combo: QComboBox, values: list[str]) -> None:
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        index = combo.findText(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    @staticmethod
    def _filter_records(records: list[CsvRecord], filters: dict[str, str]) -> list[CsvRecord]:
        project = filters.get("projeto", "Todos")
        activity = filters.get("tipo", "Todos")
        origin = filters.get("origem", "Todos")
        status = filters.get("status", "Todos")
        return [
            record
            for record in records
            if (project == "Todos" or record.project == project)
            and (activity == "Todos" or record.activity_type == activity)
            and (origin == "Todos" or record.origin == origin)
            and (
                status == "Todos"
                or (status == "Ativos" and not record.deleted)
                or (status == "Excluídos" and record.deleted)
            )
        ]

    def _current_dashboard_filters(self) -> dict[str, str]:
        return {
            "projeto": self.project_filter.currentText(),
            "tipo": self.activity_filter.currentText(),
            "origem": self.origin_filter.currentText(),
            "status": self.status_filter.currentText(),
        }

    def _filtered_records(self, records: list[CsvRecord]) -> list[CsvRecord]:
        return self._filter_records(records, self._current_dashboard_filters())

    def populate_dashboard_tree(self) -> None:
        self.dashboard_tree.clear()
        users = self.master_db.list_users(active_only=True)
        total_seconds = 0
        total_records = 0
        manual_records = 0
        deleted_records = 0

        bold_font = self.dashboard_tree.font()
        bold_font.setBold(True)
        red_background = QColor("#FEE4E2")
        red_text = QColor("#B42318")

        for user in users:
            user_id = int(user["id"])
            records = self._filtered_records(self.loaded_records.get(user_id, []))
            active_records = [record for record in records if not record.deleted]
            excluded_records = [record for record in records if record.deleted]
            seconds = sum(record.duration_seconds for record in active_records)
            manual = sum(1 for record in active_records if record.origin == "MANUAL")
            total_seconds += seconds
            total_records += len(active_records)
            manual_records += manual
            deleted_records += len(excluded_records)

            status_summary = (
                f"{len(excluded_records)} excluído(s)" if excluded_records else ""
            )
            user_item = QTreeWidgetItem(
                [
                    str(user["display_name"]),
                    format_duration(seconds),
                    str(len(active_records)),
                    f"{manual} manual" if manual else "",
                    status_summary,
                    "",
                    "",
                    "",
                    self.user_errors.get(user_id, ""),
                ]
            )
            for column in range(self.dashboard_tree.columnCount()):
                user_item.setFont(column, bold_font)
            if user_id in self.user_errors:
                user_item.setForeground(0, red_text)
            self.dashboard_tree.addTopLevelItem(user_item)

            grouped: dict[str, list[CsvRecord]] = defaultdict(list)
            for record in records:
                grouped[record.project].append(record)

            for project_name in sorted(grouped, key=str.casefold):
                project_records = grouped[project_name]
                project_active = [record for record in project_records if not record.deleted]
                project_deleted = [record for record in project_records if record.deleted]
                project_seconds = sum(record.duration_seconds for record in project_active)
                project_manual = sum(1 for record in project_active if record.origin == "MANUAL")
                project_item = QTreeWidgetItem(
                    [
                        project_name,
                        format_duration(project_seconds),
                        str(len(project_active)),
                        f"{project_manual} manual" if project_manual else "",
                        f"{len(project_deleted)} excluído(s)" if project_deleted else "",
                        "",
                        "",
                        "",
                        "",
                    ]
                )
                user_item.addChild(project_item)

                for record in project_records:
                    label = record.description or record.activity_type
                    observation = record.observation
                    if record.deleted:
                        audit_note = (
                            f"Excluído por {record.deleted_by} em {record.deleted_at}. "
                            f"Motivo: {record.deletion_reason}"
                        ).strip()
                        observation = f"{observation} | {audit_note}" if observation else audit_note
                    record_item = QTreeWidgetItem(
                        [
                            label,
                            format_duration(record.duration_seconds),
                            "0" if record.deleted else "1",
                            record.origin,
                            "EXCLUÍDO" if record.deleted else "ATIVO",
                            record.start.strftime("%H:%M"),
                            record.end.strftime("%H:%M"),
                            record.activity_type,
                            observation,
                        ]
                    )
                    record_item.setToolTip(0, record.description)
                    record_item.setToolTip(
                        8,
                        f"Arquivo: {record.source_file}\nComputador: {record.computer}",
                    )
                    if record.origin == "MANUAL" and not record.deleted:
                        record_item.setForeground(3, red_text)
                    if record.deleted:
                        for column in range(self.dashboard_tree.columnCount()):
                            record_item.setBackground(column, red_background)
                            record_item.setForeground(column, red_text)
                    project_item.addChild(record_item)

        self.monitored_label.setText(str(len(users)))
        self.total_hours_label.setText(format_duration(total_seconds))
        self.records_label.setText(str(total_records))
        self.manual_label.setText(str(manual_records))
        self.deleted_label.setText(str(deleted_records))

        if not users:
            self.dashboard_tree.addTopLevelItem(
                QTreeWidgetItem(["Nenhum usuário monitorado. Adicione uma pasta na aba Usuários monitorados."])
            )

    def _dashboard_export_entries(
        self,
        filters: dict[str, str] | None = None,
    ) -> list[tuple[str, CsvRecord]]:
        entries: list[tuple[str, CsvRecord]] = []
        selected_filters = filters or self._current_dashboard_filters()
        for user in self.master_db.list_users(active_only=True):
            user_id = int(user["id"])
            display_name = str(user["display_name"])
            records = self._filter_records(
                self.loaded_records.get(user_id, []),
                selected_filters,
            )
            for record in records:
                entries.append((display_name, record))
        return sorted(entries, key=lambda item: (item[0].casefold(), item[1].start, item[1].record_id))

    def _period_export_entries(
        self,
        year: int,
        months: list[int],
        filters: dict[str, str],
    ) -> tuple[list[tuple[str, CsvRecord]], list[str]]:
        entries: list[tuple[str, CsvRecord]] = []
        errors: list[str] = []
        local_actions = [item["data"] for item in self.db.list_audit_actions()]
        for user in self.master_db.list_users(active_only=True):
            try:
                records = read_records_for_months(
                    str(user["source_folder"]),
                    str(user["source_user"]),
                    year,
                    months,
                )
                records = apply_audit_actions_to_records(records, local_actions)
                for record in self._filter_records(records, filters):
                    entries.append((str(user["display_name"]), record))
            except Exception as exc:
                logging.exception("Falha ao ler período para %s", user["display_name"])
                errors.append(f"{user['display_name']}: {exc}")
        entries.sort(key=lambda item: (item[0].casefold(), item[1].start, item[1].record_id))
        return entries, errors

    @staticmethod
    def _period_label(year: int, months: list[int]) -> str:
        ordered = sorted(set(months))
        if ordered == list(range(1, 13)):
            return f"Ano inteiro de {year}"
        names = [MONTH_NAMES[month - 1] for month in ordered]
        if len(names) == 1:
            return f"{names[0]} de {year}"
        consecutive = ordered == list(range(ordered[0], ordered[-1] + 1))
        if consecutive:
            return f"{names[0]} a {names[-1]} de {year}"
        return f"{', '.join(names[:-1])} e {names[-1]} de {year}"

    @staticmethod
    def _period_filename(year: int, months: list[int]) -> str:
        ordered = sorted(set(months))
        if ordered == list(range(1, 13)):
            return f"TimerTask_Relatorio_{year}_ano-inteiro"
        if len(ordered) == 1:
            return f"TimerTask_Relatorio_{year}-{ordered[0]:02d}"
        consecutive = ordered == list(range(ordered[0], ordered[-1] + 1))
        if consecutive:
            return f"TimerTask_Relatorio_{year}-{ordered[0]:02d}_a_{year}-{ordered[-1]:02d}"
        months_text = "-".join(f"{month:02d}" for month in ordered)
        return f"TimerTask_Relatorio_{year}_meses-{months_text}"

    def _get_export_options(self) -> dict[str, object] | None:
        dialog = ExportOptionsDialog(
            self,
            self.date_edit.date().toPython(),
            self._current_dashboard_filters(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.options()

    def export_dashboard(self) -> None:
        options = self._get_export_options()
        if options is None:
            return

        current_filters = self._current_dashboard_filters()
        all_filters = {
            "projeto": "Todos",
            "tipo": "Todos",
            "origem": "Todos",
            "status": "Todos",
        }
        mode = str(options["mode"])
        export_format = str(options["format"])
        report_date = self.date_edit.date().toPython()
        period_label: str | None = None
        errors: list[str] = []

        if mode == "period":
            year = int(options["year"])
            months = [int(month) for month in options["months"]]
            apply_filters = bool(options["apply_dashboard_filters"])
            filters = current_filters if apply_filters else all_filters
            filters = dict(filters)
            filters["escopo"] = (
                "Período selecionado com filtros iniciais do Dashboard"
                if apply_filters
                else "Período selecionado — todos os registros"
            )
            data_filters = all_filters if export_format == "xlsx" else filters
            entries, errors = self._period_export_entries(year, months, data_filters)
            period_label = self._period_label(year, months)
            default_base = self._period_filename(year, months)
            report_date = date(year, months[0], 1)
        else:
            filters = dict(current_filters)
            filters["escopo"] = "Data atual com filtros iniciais do Dashboard"
            data_filters = all_filters if export_format == "xlsx" else current_filters
            entries = self._dashboard_export_entries(data_filters)
            default_base = f"TimerTask_Relatorio_{report_date:%Y-%m-%d}"

        documents = Path.home() / "Documents"
        initial_folder = documents if documents.is_dir() else Path.home()
        suffix = ".csv" if export_format == "csv" else ".xlsx"
        file_filter = "CSV detalhado (*.csv)" if export_format == "csv" else "Excel completo (*.xlsx)"
        file_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Exportar relatório do Dashboard",
            str(initial_folder / f"{default_base}{suffix}"),
            file_filter,
        )
        if not file_path:
            return

        try:
            if export_format == "csv":
                exported = export_csv(file_path, entries)
            else:
                exported = export_excel(
                    file_path,
                    entries,
                    report_date,
                    filters,
                    period_label=period_label,
                )
        except Exception as exc:
            logging.exception("Falha ao exportar o relatório do Dashboard")
            QMessageBox.critical(
                self,
                APP_NAME,
                f"Não foi possível exportar o relatório:\n{exc}",
            )
            return

        message = f"Relatório exportado com sucesso:\n{exported}"
        if errors:
            message += "\n\nAlgumas pastas não puderam ser lidas:\n" + "\n".join(errors)
        QMessageBox.information(self, APP_NAME, message)

    def expand_users(self) -> None:
        for index in range(self.dashboard_tree.topLevelItemCount()):
            self.dashboard_tree.topLevelItem(index).setExpanded(True)

def main() -> int:
    sys.excepthook = exception_hook
    application = QApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    application.setQuitOnLastWindowClosed(False)
    app_icon = load_app_icon()
    if not app_icon.isNull():
        application.setWindowIcon(app_icon)

    data_dir = app_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    # Usa a mesma trava do Timer Task para impedir que as duas edições rodem juntas.
    instance_lock = QLockFile(str(data_dir / "timertask.lock"))
    instance_lock.setStaleLockTime(30_000)
    if not instance_lock.tryLock(100):
        QMessageBox.information(
            None,
            APP_NAME,
            "O Timer Task ou Timer Task Master já está aberto. Verifique a bandeja do Windows.",
        )
        return 0

    db_path = data_dir / "timertask.db"
    try:
        backup_dir = backup_existing_timer_data()
        if backup_dir is not None:
            logging.info("Backup anterior ao Master criado em %s", backup_dir)
    except Exception as exc:
        logging.exception("Não foi possível criar o backup anterior ao Master")
        QMessageBox.critical(
            None,
            APP_NAME,
            "O banco anterior foi encontrado, mas não foi possível criar o backup de segurança. "
            f"A inicialização foi cancelada para preservar os dados.\n\n{exc}",
        )
        return 1

    timer_db = Database(db_path)
    master_db = MasterDatabase(db_path)
    window = MainWindow(timer_db, master_db)
    window.instance_lock = instance_lock
    window.show()
    logging.info("Timer Task Master iniciado com o módulo de timer e gestão")
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
