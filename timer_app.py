from __future__ import annotations

import logging
import os
import shutil
import socket
import sys
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QDateTime, QLockFile, QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCompleter,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class CatalogComboBox(QComboBox):
    """Campo de catálogo com busca incremental e criação por Enter."""

    def __init__(self, table_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table_name = table_name
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.lineEdit().setPlaceholderText("Digite para buscar ou criar")
        completer = self.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

from csv_store import (
    append_audit_action,
    append_record,
    apply_audit_actions,
    read_all_records,
    test_write_access,
)
from database import Database


APP_NAME = "Timer Task Master"


class CsvSyncSignals(QObject):
    finished = Signal(str, bool, str)


class CsvSyncWorker(QRunnable):
    """Grava um registro no CSV sem bloquear a interface."""

    def __init__(self, base_folder: str, record: dict) -> None:
        super().__init__()
        self.base_folder = base_folder
        self.record = record
        self.signals = CsvSyncSignals()

    def run(self) -> None:
        record_id = str(self.record["registro_id"])
        try:
            append_record(self.base_folder, self.record)
            self.signals.finished.emit(record_id, True, "")
        except Exception as exc:
            self.signals.finished.emit(record_id, False, str(exc))


def application_dir() -> Path:
    bundled_dir = getattr(sys, "_MEIPASS", None)
    if bundled_dir:
        return Path(bundled_dir)
    return Path(__file__).resolve().parent


def load_app_icon() -> QIcon:
    """Carrega o primeiro arquivo ICO disponível na pasta icons."""
    icons_dir = application_dir() / "icons"
    if icons_dir.is_dir():
        for path in sorted(icons_dir.glob("*.ico"), key=lambda item: item.name.lower()):
            if path.is_file():
                return QIcon(str(path))
    return QIcon()


def app_data_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or str(Path.home() / ".timertask"))


def app_data_dir() -> Path:
    return app_data_root() / "TimerTask"


def migrate_legacy_app_data() -> None:
    """Copia os dados da estrutura antiga para a pasta definitiva do produto."""
    legacy_dir = app_data_root() / "TimerTaskV1"
    target_dir = app_data_dir()
    target_db = target_dir / "timertask.db"

    if target_db.exists() or not legacy_dir.exists():
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    for name in ("timertask.db", "timertask.db-wal", "timertask.db-shm"):
        source = legacy_dir / name
        if source.is_file():
            shutil.copy2(source, target_dir / name)


migrate_legacy_app_data()


def configure_logging() -> Path:
    log_dir = app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "timertask.log"
    handlers: list[logging.Handler] = [
        logging.FileHandler(log_path, encoding="utf-8")
    ]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
    )
    return log_path


LOG_PATH = configure_logging()


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class FinishDialog(QDialog):
    def __init__(self, elapsed_seconds: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Finalizar atividade")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        duration = QLabel(f"Duração registrada: <b>{format_duration(elapsed_seconds)}</b>")
        layout.addWidget(duration)
        layout.addWidget(QLabel("Observação final (opcional):"))

        self.observation = QTextEdit()
        self.observation.setPlaceholderText("Ex.: Ajuste concluído e validado.")
        self.observation.setMaximumHeight(130)
        layout.addWidget(self.observation)

        buttons = QHBoxLayout()
        cancel_button = QPushButton("Cancelar")
        save_button = QPushButton("Salvar registro")
        save_button.setDefault(True)
        cancel_button.clicked.connect(self.reject)
        save_button.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

    def value(self) -> str:
        return self.observation.toPlainText().strip()


class HistoryDetailsDialog(QDialog):
    DETAIL_FIELDS = [
        ("status", "Status"),
        ("registro_id", "ID do registro"),
        ("usuario", "Usuário"),
        ("origem_registro", "Origem"),
        ("projeto", "Projeto"),
        ("tipo_atividade", "Tipo de atividade"),
        ("descricao", "Descrição"),
        ("inicio", "Início"),
        ("fim", "Fim"),
        ("duracao_formatada", "Duração"),
        ("duracao_segundos", "Duração em segundos"),
        ("observacao", "Observação"),
        ("computador", "Computador"),
        ("data_registro", "Registrado em"),
        ("usuario_exclusao", "Excluído por"),
        ("data_exclusao", "Excluído em"),
        ("motivo_exclusao", "Motivo da exclusão"),
        ("acao_id_exclusao", "ID da exclusão"),
    ]

    def __init__(self, record: dict[str, object], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Detalhes do registro")
        self.resize(680, 560)

        layout = QVBoxLayout(self)
        title = QLabel("Informações completas do registro selecionado")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        deleted = str(record.get("excluido", "0")) == "1"
        values = dict(record)
        values["status"] = "EXCLUÍDO" if deleted else "ATIVO"
        values["origem_registro"] = record.get("origem_registro") or "TIMER"
        if not str(values.get("duracao_formatada", "")).strip():
            try:
                values["duracao_formatada"] = format_duration(
                    int(record.get("duracao_segundos", 0))
                )
            except (TypeError, ValueError):
                values["duracao_formatada"] = ""

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.value_labels: dict[str, QLabel] = {}
        for key, label_text in self.DETAIL_FIELDS:
            value_label = QLabel(self._display_value(values.get(key)))
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.value_labels[key] = value_label
            form.addRow(f"{label_text}:", value_label)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close_button = QPushButton("Fechar")
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    @staticmethod
    def _display_value(value: object) -> str:
        text = "" if value is None else str(value).strip()
        return text or "—"


class MainWindow(QMainWindow):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self._csv_sync_pool = QThreadPool.globalInstance()
        self._csv_sync_workers: set[CsvSyncWorker] = set()
        self.force_quit = False
        self.setWindowTitle(APP_NAME)
        self.resize(820, 600)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.timer_tab = QWidget()
        self.manual_tab = QWidget()
        self.history_tab = QWidget()
        self.catalog_tab = QWidget()
        self.settings_tab = QWidget()
        self.tabs.addTab(self.timer_tab, "Timer")
        self.tabs.addTab(self.manual_tab, "Registro manual")
        self.tabs.addTab(self.history_tab, "Histórico")
        self.tabs.addTab(self.catalog_tab, "Cadastros")
        self.tabs.addTab(self.settings_tab, "Configurações")

        self._build_timer_tab()
        self._build_manual_tab()
        self._build_history_tab()
        self._build_catalog_tab()
        self._build_settings_tab()
        self._build_tray()
        self.tabs.currentChanged.connect(self._refresh_today_on_timer_tab)

        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self.refresh_timer_state)
        self.clock_timer.start()

        self.reload_catalogs()
        self.load_settings()
        self.refresh_timer_state()
        self.refresh_history()

        QTimer.singleShot(200, self.ensure_initial_configuration)

    def _build_timer_tab(self) -> None:
        layout = QVBoxLayout(self.timer_tab)
        layout.setContentsMargins(24, 24, 24, 24)

        self.timer_status_label = QLabel("Nenhuma atividade em andamento")
        self.timer_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_status_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(self.timer_status_label)

        self.elapsed_label = QLabel("00:00:00")
        self.elapsed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.elapsed_label.setStyleSheet("font-size: 48px; font-weight: 700; margin: 12px;")
        layout.addWidget(self.elapsed_label)

        form_group = QGroupBox("Atividade")
        form = QFormLayout(form_group)
        self.project_combo = CatalogComboBox("projects")
        self.activity_combo = CatalogComboBox("activity_types")
        self.project_combo.lineEdit().returnPressed.connect(lambda: self.ensure_catalog_entry(self.project_combo))
        self.activity_combo.lineEdit().returnPressed.connect(lambda: self.ensure_catalog_entry(self.activity_combo))
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("Descrição breve do que será realizado")
        form.addRow("Projeto:", self.project_combo)
        form.addRow("Tipo de atividade:", self.activity_combo)
        form.addRow("Descrição:", self.description_edit)
        layout.addWidget(form_group)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("Iniciar timer")
        self.finish_button = QPushButton("Finalizar timer")
        self.cancel_timer_button = QPushButton("Cancelar timer")
        self.start_button.clicked.connect(self.start_timer)
        self.finish_button.clicked.connect(self.finish_timer)
        self.cancel_timer_button.clicked.connect(self.cancel_timer)
        buttons.addStretch()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.finish_button)
        buttons.addWidget(self.cancel_timer_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.today_total_label = QLabel("Total registrado hoje: 00:00:00")
        self.today_total_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.today_total_label)

        self.connection_label = QLabel("")
        self.connection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.connection_label)

        pending_row = QHBoxLayout()
        pending_row.addStretch()
        self.timer_pending_label = QLabel("Tasks pendentes: 0")
        self.register_tasks_button = QPushButton("Registrar Tasks")
        self.register_tasks_button.setToolTip(
            "Tenta registrar no CSV somente as tasks que ficaram pendentes ou com falha."
        )
        self.register_tasks_button.clicked.connect(
            lambda: self.register_pending_records(show_result=True)
        )
        pending_row.addWidget(self.timer_pending_label)
        pending_row.addWidget(self.register_tasks_button)
        pending_row.addStretch()
        layout.addLayout(pending_row)
        layout.addStretch()

    def _build_manual_tab(self) -> None:
        layout = QVBoxLayout(self.manual_tab)
        layout.setContentsMargins(24, 24, 24, 24)

        notice = QLabel(
            "Use esta tela somente para lançar uma atividade que não foi marcada pelo timer. "
            "O CSV identificará o registro com a origem MANUAL para fins de auditoria."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("font-weight: 600;")
        layout.addWidget(notice)

        form_group = QGroupBox("Dados do registro manual")
        form = QFormLayout(form_group)
        self.manual_project_combo = CatalogComboBox("projects")
        self.manual_activity_combo = CatalogComboBox("activity_types")
        self.manual_project_combo.lineEdit().returnPressed.connect(lambda: self.ensure_catalog_entry(self.manual_project_combo))
        self.manual_activity_combo.lineEdit().returnPressed.connect(lambda: self.ensure_catalog_entry(self.manual_activity_combo))
        self.manual_start_edit = QDateTimeEdit(QDateTime.currentDateTime().addSecs(-3600))
        self.manual_end_edit = QDateTimeEdit(QDateTime.currentDateTime())
        for editor in (self.manual_start_edit, self.manual_end_edit):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("dd/MM/yyyy HH:mm:ss")

        self.manual_description_edit = QLineEdit()
        self.manual_description_edit.setPlaceholderText("Descrição breve da atividade realizada")
        self.manual_observation_edit = QTextEdit()
        self.manual_observation_edit.setPlaceholderText("Observação do registro manual")
        self.manual_observation_edit.setMaximumHeight(130)

        form.addRow("Projeto:", self.manual_project_combo)
        form.addRow("Tipo de atividade:", self.manual_activity_combo)
        form.addRow("Data/hora de início:", self.manual_start_edit)
        form.addRow("Data/hora de fim:", self.manual_end_edit)
        form.addRow("Descrição:", self.manual_description_edit)
        form.addRow("Observação:", self.manual_observation_edit)
        layout.addWidget(form_group)

        button_row = QHBoxLayout()
        button_row.addStretch()
        save_button = QPushButton("Salvar registro manual")
        save_button.setDefault(True)
        save_button.clicked.connect(self.save_manual_record)
        button_row.addWidget(save_button)
        button_row.addStretch()
        layout.addLayout(button_row)
        layout.addStretch()

    def _build_history_tab(self) -> None:
        layout = QVBoxLayout(self.history_tab)
        top = QHBoxLayout()
        top.addWidget(QLabel("Data:"))
        self.history_date = QDateEdit(QDate.currentDate())
        self.history_date.setCalendarPopup(True)
        self.history_date.setDisplayFormat("dd/MM/yyyy")
        self.history_date.dateChanged.connect(self.refresh_history)
        top.addWidget(self.history_date)

        top.addWidget(QLabel("Exibir:"))
        self.history_status_filter = QComboBox()
        self.history_status_filter.addItems(["Ativos", "Excluídos", "Todos"])
        self.history_status_filter.currentTextChanged.connect(
            lambda _value: self.refresh_history()
        )
        top.addWidget(self.history_status_filter)

        refresh_button = QPushButton("Atualizar")
        refresh_button.clicked.connect(self.refresh_history)
        top.addWidget(refresh_button)
        self.delete_history_button = QPushButton("Excluir registro")
        self.delete_history_button.clicked.connect(self.delete_selected_history_record)
        top.addWidget(self.delete_history_button)
        top.addStretch()
        self.history_total_label = QLabel("Total válido: 00:00:00")
        top.addWidget(self.history_total_label)
        layout.addLayout(top)

        history_hint = QLabel("Clique duas vezes em uma linha para ver os detalhes completos.")
        history_hint.setStyleSheet("color: #667085;")
        layout.addWidget(history_hint)

        headers = [
            "Início", "Fim", "Projeto", "Tipo", "Descrição", "Duração",
            "Origem", "Status", "Observação"
        ]
        self.history_table = QTableWidget(0, len(headers))
        self.history_table.setHorizontalHeaderLabels(headers)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history_table.cellDoubleClicked.connect(self.show_history_details)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setColumnWidth(0, 70)
        self.history_table.setColumnWidth(1, 70)
        self.history_table.setColumnWidth(2, 140)
        self.history_table.setColumnWidth(3, 130)
        self.history_table.setColumnWidth(4, 220)
        self.history_table.setColumnWidth(5, 90)
        self.history_table.setColumnWidth(6, 80)
        self.history_table.setColumnWidth(7, 90)
        self.history_rows: list[dict[str, object]] = []
        layout.addWidget(self.history_table)

    def _build_catalog_tab(self) -> None:
        layout = QGridLayout(self.catalog_tab)

        project_group = QGroupBox("Projetos")
        project_layout = QVBoxLayout(project_group)
        self.projects_table = self._make_catalog_table()
        project_layout.addWidget(self.projects_table)
        project_buttons = QHBoxLayout()
        add_project = QPushButton("Adicionar")
        rename_project = QPushButton("Renomear")
        toggle_project = QPushButton("Ativar/Desativar")
        add_project.clicked.connect(lambda: self.add_catalog_item("projects"))
        rename_project.clicked.connect(lambda: self.rename_catalog_item("projects"))
        toggle_project.clicked.connect(lambda: self.toggle_catalog_item("projects"))
        project_buttons.addWidget(add_project)
        project_buttons.addWidget(rename_project)
        project_buttons.addWidget(toggle_project)
        project_layout.addLayout(project_buttons)

        activity_group = QGroupBox("Tipos de atividade")
        activity_layout = QVBoxLayout(activity_group)
        self.activities_table = self._make_catalog_table()
        activity_layout.addWidget(self.activities_table)
        activity_buttons = QHBoxLayout()
        add_activity = QPushButton("Adicionar")
        rename_activity = QPushButton("Renomear")
        toggle_activity = QPushButton("Ativar/Desativar")
        add_activity.clicked.connect(lambda: self.add_catalog_item("activity_types"))
        rename_activity.clicked.connect(lambda: self.rename_catalog_item("activity_types"))
        toggle_activity.clicked.connect(lambda: self.toggle_catalog_item("activity_types"))
        activity_buttons.addWidget(add_activity)
        activity_buttons.addWidget(rename_activity)
        activity_buttons.addWidget(toggle_activity)
        activity_layout.addLayout(activity_buttons)

        layout.addWidget(project_group, 0, 0)
        layout.addWidget(activity_group, 0, 1)

    def _build_settings_tab(self) -> None:
        layout = QVBoxLayout(self.settings_tab)
        form_group = QGroupBox("Configuração local")
        form = QFormLayout(form_group)

        self.user_name_edit = QLineEdit()
        self.base_folder_edit = QLineEdit()
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.base_folder_edit)
        choose_button = QPushButton("Selecionar")
        choose_button.clicked.connect(self.choose_base_folder)
        folder_row.addWidget(choose_button)

        form.addRow("Nome do usuário:", self.user_name_edit)
        form.addRow("Pasta-base dos CSVs:", folder_row)
        layout.addWidget(form_group)

        buttons = QHBoxLayout()
        test_button = QPushButton("Testar acesso")
        save_button = QPushButton("Salvar configurações")
        sync_button = QPushButton("Registrar Tasks")
        import_button = QPushButton("Importar CSVs")
        rebuild_button = QPushButton("Reconstruir CSVs")
        test_button.clicked.connect(self.test_base_folder)
        save_button.clicked.connect(self.save_settings)
        sync_button.clicked.connect(lambda: self.register_pending_records(show_result=True))
        import_button.clicked.connect(self.import_existing_csvs)
        rebuild_button.clicked.connect(self.reconcile_csv_records)
        buttons.addWidget(test_button)
        buttons.addWidget(save_button)
        buttons.addWidget(sync_button)
        buttons.addWidget(import_button)
        buttons.addWidget(rebuild_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.pending_label = QLabel("Registros pendentes: 0")
        self.local_db_label = QLabel(f"Banco local: {self.db.db_path}")
        self.log_label = QLabel(f"Log: {LOG_PATH}")
        self.local_db_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.log_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.pending_label)

        pending_group = QGroupBox("Itens aguardando registro nos CSVs")
        pending_layout = QVBoxLayout(pending_group)
        pending_headers = [
            "Item", "Projeto", "Tipo / ação", "Origem", "Início", "Status",
            "Tentativas", "Último erro"
        ]
        self.pending_table = QTableWidget(0, len(pending_headers))
        self.pending_table.setHorizontalHeaderLabels(pending_headers)
        self.pending_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pending_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.pending_table.setColumnWidth(0, 85)
        self.pending_table.setColumnWidth(1, 130)
        self.pending_table.setColumnWidth(2, 120)
        self.pending_table.setColumnWidth(3, 80)
        self.pending_table.setColumnWidth(4, 135)
        self.pending_table.setColumnWidth(5, 90)
        self.pending_table.setColumnWidth(6, 75)
        self.pending_table.horizontalHeader().setStretchLastSection(True)
        pending_layout.addWidget(self.pending_table)
        layout.addWidget(pending_group)

        layout.addWidget(self.local_db_label)
        layout.addWidget(self.log_label)
        layout.addStretch()

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        icon = load_app_icon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        self.tray.setIcon(icon)
        self.tray.setToolTip(APP_NAME)

        menu = self.tray.contextMenu()
        if menu is None:
            from PySide6.QtWidgets import QMenu

            menu = QMenu()
        open_action = QAction("Abrir Timer Task Master", self)
        open_action.triggered.connect(self.show_from_tray)
        register_action = QAction("Registrar Tasks", self)
        register_action.triggered.connect(lambda: self.register_pending_records(show_result=True))
        exit_action = QAction("Sair", self)
        exit_action.triggered.connect(self.exit_application)
        menu.addAction(open_action)
        menu.addAction(register_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    @staticmethod
    def _make_catalog_table() -> QTableWidget:
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["ID", "Nome", "Status"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setColumnWidth(0, 45)
        table.setColumnWidth(1, 220)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def ensure_initial_configuration(self) -> None:
        if self.db.get_setting("user_name") and self.db.get_setting("base_folder"):
            return
        self.tabs.setCurrentWidget(self.settings_tab)
        QMessageBox.information(
            self,
            "Configuração inicial",
            "Informe o nome do usuário e selecione a pasta compartilhada onde os CSVs serão gravados.",
        )

    def load_settings(self) -> None:
        self.user_name_edit.setText(self.db.get_setting("user_name"))
        self.base_folder_edit.setText(self.db.get_setting("base_folder"))
        self.update_pending_status()

    def save_settings(self) -> None:
        user_name = self.user_name_edit.text().strip()
        base_folder = self.base_folder_edit.text().strip()
        if not user_name:
            QMessageBox.warning(self, "Configurações", "Informe o nome do usuário.")
            return
        if not base_folder:
            QMessageBox.warning(self, "Configurações", "Selecione a pasta-base dos registros.")
            return
        try:
            test_write_access(base_folder)
        except Exception as exc:
            answer = QMessageBox.question(
                self,
                "Pasta indisponível",
                f"Não foi possível gravar na pasta informada:\n{exc}\n\nSalvar mesmo assim?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self.db.set_setting("user_name", user_name)
        self.db.set_setting("base_folder", base_folder)
        QMessageBox.information(self, "Configurações", "Configurações salvas.")
        self.refresh_history()
        self.update_pending_status()

    def choose_base_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Selecione a pasta-base do Timer Task",
            self.base_folder_edit.text() or str(Path.home()),
        )
        if selected:
            self.base_folder_edit.setText(selected)

    def test_base_folder(self) -> None:
        folder = self.base_folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "Teste", "Selecione uma pasta.")
            return
        try:
            test_write_access(folder)
            QMessageBox.information(self, "Teste", "Leitura e gravação realizadas com sucesso.")
        except Exception as exc:
            QMessageBox.critical(self, "Teste", f"Falha no acesso à pasta:\n{exc}")

    def reload_catalogs(self) -> None:
        current_project = self.project_combo.currentData()
        current_activity = self.activity_combo.currentData()
        current_manual_project = self.manual_project_combo.currentData()
        current_manual_activity = self.manual_activity_combo.currentData()

        projects = self.db.list_items("projects", active_only=True)
        activities = self.db.list_items("activity_types", active_only=True)

        self.project_combo.clear()
        self.manual_project_combo.clear()
        for row in projects:
            self.project_combo.addItem(row["name"], row["id"])
            self.manual_project_combo.addItem(row["name"], row["id"])

        self.activity_combo.clear()
        self.manual_activity_combo.clear()
        for row in activities:
            self.activity_combo.addItem(row["name"], row["id"])
            self.manual_activity_combo.addItem(row["name"], row["id"])

        self._fill_catalog_table(self.projects_table, self.db.list_items("projects"))
        self._fill_catalog_table(self.activities_table, self.db.list_items("activity_types"))

        self._restore_combo_value(self.project_combo, current_project)
        self._restore_combo_value(self.activity_combo, current_activity)
        self._restore_combo_value(self.manual_project_combo, current_manual_project)
        self._restore_combo_value(self.manual_activity_combo, current_manual_activity)

    @staticmethod
    def _restore_combo_value(combo: QComboBox, value: object) -> None:
        if value is None:
            return
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def ensure_catalog_entry(self, combo: CatalogComboBox) -> bool:
        """Seleciona um item exato ou cria o texto digitado no catálogo."""
        name = combo.currentText().strip()
        if not name:
            return False
        exact_index = combo.findText(name, Qt.MatchFlag.MatchFixedString)
        if exact_index >= 0:
            combo.setCurrentIndex(exact_index)
            return combo.currentData() is not None
        try:
            self.db.add_item(combo.table_name, name)
        except Exception as exc:
            label = "o projeto" if combo.table_name == "projects" else "o tipo de atividade"
            QMessageBox.warning(self, "Cadastro", f"Não foi possível criar {label}:\n{exc}")
            return False
        self.reload_catalogs()
        exact_index = combo.findText(name, Qt.MatchFlag.MatchFixedString)
        if exact_index < 0:
            return False
        combo.setCurrentIndex(exact_index)
        return combo.currentData() is not None

    @staticmethod
    def _fill_catalog_table(table: QTableWidget, rows: list) -> None:
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            table.setItem(row_index, 0, QTableWidgetItem(str(row["id"])))
            table.setItem(row_index, 1, QTableWidgetItem(row["name"]))
            table.setItem(row_index, 2, QTableWidgetItem("Ativo" if row["active"] else "Inativo"))

    def selected_catalog_id(self, table_name: str) -> int | None:
        table = self.projects_table if table_name == "projects" else self.activities_table
        row_index = table.currentRow()
        if row_index < 0:
            return None
        item = table.item(row_index, 0)
        return int(item.text()) if item else None

    def add_catalog_item(self, table_name: str) -> None:
        title = "Novo projeto" if table_name == "projects" else "Novo tipo de atividade"
        name, accepted = QInputDialog.getText(self, title, "Nome:")
        if not accepted:
            return
        try:
            self.db.add_item(table_name, name)
            self.reload_catalogs()
        except Exception as exc:
            QMessageBox.warning(self, title, f"Não foi possível adicionar:\n{exc}")

    def rename_catalog_item(self, table_name: str) -> None:
        item_id = self.selected_catalog_id(table_name)
        if item_id is None:
            QMessageBox.warning(self, "Cadastros", "Selecione um item.")
            return
        table = self.projects_table if table_name == "projects" else self.activities_table
        current_name = table.item(table.currentRow(), 1).text()
        name, accepted = QInputDialog.getText(self, "Renomear", "Novo nome:", text=current_name)
        if not accepted:
            return
        try:
            self.db.rename_item(table_name, item_id, name)
            self.reload_catalogs()
        except Exception as exc:
            QMessageBox.warning(self, "Renomear", f"Não foi possível renomear:\n{exc}")

    def toggle_catalog_item(self, table_name: str) -> None:
        item_id = self.selected_catalog_id(table_name)
        if item_id is None:
            QMessageBox.warning(self, "Cadastros", "Selecione um item.")
            return
        try:
            self.db.toggle_item(table_name, item_id)
            self.reload_catalogs()
        except Exception as exc:
            QMessageBox.warning(self, "Cadastros", f"Não foi possível alterar o item:\n{exc}")

    def start_timer(self) -> None:
        if self.db.get_active_timer():
            QMessageBox.warning(self, "Timer", "Já existe uma atividade em andamento.")
            return
        if not self.ensure_catalog_entry(self.project_combo) or not self.ensure_catalog_entry(self.activity_combo):
            QMessageBox.warning(self, "Timer", "Cadastre e selecione um projeto e um tipo de atividade.")
            return
        started_at = datetime.now().replace(microsecond=0).isoformat(sep=" ")
        try:
            self.db.start_timer(
                int(self.project_combo.currentData()),
                int(self.activity_combo.currentData()),
                self.description_edit.text(),
                started_at,
            )
            self.refresh_timer_state()
        except Exception as exc:
            logging.exception("Falha ao iniciar timer")
            QMessageBox.critical(self, "Timer", f"Não foi possível iniciar:\n{exc}")

    def _persist_completed_record(self, record: dict) -> None:
        """Salva localmente e tenta gravar no CSV em segundo plano."""
        self.db.add_task_record(record)
        base_folder = self.db.get_setting("base_folder").strip()
        if not base_folder:
            logging.info("Task %s salva no SQLite; pasta CSV não configurada", record["registro_id"])
            return

        worker = CsvSyncWorker(base_folder, record)
        worker.signals.finished.connect(self._on_csv_sync_finished)
        self._csv_sync_workers.add(worker)
        self._csv_sync_pool.start(worker)

    def _on_csv_sync_finished(self, record_id: str, succeeded: bool, error: str) -> None:
        self._csv_sync_workers = {
            worker for worker in self._csv_sync_workers
            if str(worker.record.get("registro_id")) != record_id
        }
        if succeeded:
            self.db.mark_task_synced(record_id)
            logging.info("Task %s sincronizada com CSV", record_id)
        else:
            self.db.mark_task_error(record_id, error)
            logging.warning("Task %s permanece no SQLite - falha ao acessar CSV: %s", record_id, error)
            self.tray.showMessage(
                APP_NAME,
                "Um registro ficou pendente porque não foi possível gravá-lo no CSV. "
                "Use Registrar Tasks para tentar novamente.",
                QSystemTrayIcon.MessageIcon.Warning,
                6000,
            )
        self.update_pending_status()
        self.refresh_history()

    def save_manual_record(self) -> None:
        user_name = self.db.get_setting("user_name").strip()
        if not user_name:
            QMessageBox.warning(
                self,
                "Registro manual",
                "Configure o nome do usuário antes de criar um registro manual.",
            )
            self.tabs.setCurrentWidget(self.settings_tab)
            return

        if not self.ensure_catalog_entry(self.manual_project_combo) or not self.ensure_catalog_entry(self.manual_activity_combo):
            QMessageBox.warning(
                self,
                "Registro manual",
                "Cadastre e selecione um projeto e um tipo de atividade.",
            )
            return

        start_text = self.manual_start_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        end_text = self.manual_end_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        started = datetime.fromisoformat(start_text)
        finished = datetime.fromisoformat(end_text)
        if finished <= started:
            QMessageBox.warning(
                self,
                "Registro manual",
                "A data/hora de fim deve ser posterior à data/hora de início.",
            )
            return

        elapsed = int((finished - started).total_seconds())
        record = {
            "registro_id": str(uuid.uuid4()),
            "usuario": user_name,
            "origem_registro": "MANUAL",
            "projeto": self.manual_project_combo.currentText(),
            "tipo_atividade": self.manual_activity_combo.currentText(),
            "descricao": self.manual_description_edit.text().strip(),
            "inicio": started.isoformat(sep=" "),
            "fim": finished.isoformat(sep=" "),
            "duracao_segundos": elapsed,
            "duracao_formatada": format_duration(elapsed),
            "observacao": self.manual_observation_edit.toPlainText().strip(),
            "computador": socket.gethostname(),
            "data_registro": datetime.now().replace(microsecond=0).isoformat(sep=" "),
        }

        try:
            self._persist_completed_record(record)
        except Exception as exc:
            logging.exception("Falha ao salvar registro manual localmente")
            QMessageBox.critical(
                self,
                "Registro manual",
                "Não foi possível salvar o registro manual no banco local.\n\n"
                f"Detalhes: {exc}",
            )
            return

        self.manual_description_edit.clear()
        self.manual_observation_edit.clear()
        now = QDateTime.currentDateTime()
        self.manual_end_edit.setDateTime(now)
        self.manual_start_edit.setDateTime(now.addSecs(-3600))
        self.refresh_history()
        self.update_pending_status()

        QMessageBox.information(
            self,
            "Registro manual",
            "Registro manual salvo no banco local. A gravação no CSV compartilhado "
            "está sendo tentada em segundo plano; se falhar, use Registrar Tasks.",
        )

    def finish_timer(self) -> None:
        timer = self.db.get_active_timer()
        if not timer:
            QMessageBox.information(self, "Timer", "Não há atividade em andamento.")
            return

        started = datetime.fromisoformat(timer["started_at"])
        finished = datetime.now().replace(microsecond=0)
        elapsed = max(0, int((finished - started).total_seconds()))
        dialog = FinishDialog(elapsed, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        user_name = self.db.get_setting("user_name").strip()
        if not user_name:
            QMessageBox.warning(self, "Timer", "Configure o nome do usuário antes de finalizar.")
            self.tabs.setCurrentWidget(self.settings_tab)
            return

        record = {
            "registro_id": str(uuid.uuid4()),
            "usuario": user_name,
            "origem_registro": "TIMER",
            "projeto": timer["project_name"],
            "tipo_atividade": timer["activity_type_name"],
            "descricao": timer["description"],
            "inicio": started.isoformat(sep=" "),
            "fim": finished.isoformat(sep=" "),
            "duracao_segundos": elapsed,
            "duracao_formatada": format_duration(elapsed),
            "observacao": dialog.value(),
            "computador": socket.gethostname(),
            "data_registro": datetime.now().replace(microsecond=0).isoformat(sep=" "),
        }

        try:
            self._persist_completed_record(record)
        except Exception as exc:
            logging.exception("Falha ao salvar o registro localmente")
            QMessageBox.critical(
                self,
                "Timer",
                "Não foi possível salvar a atividade no banco local. "
                "O timer permanecerá aberto para uma nova tentativa.\n\n"
                f"Detalhes: {exc}",
            )
            return

        message = (
            "A atividade foi concluída e salva no banco local.\n\n"
            "A gravação no CSV compartilhado está sendo tentada em segundo plano. "
            "Se falhar, use Registrar Tasks."
        )

        self.db.clear_active_timer()
        self.description_edit.clear()
        self.refresh_timer_state()
        self.refresh_history()
        self.update_pending_status()
        QMessageBox.information(self, "Timer", message)

    def cancel_timer(self) -> None:
        if not self.db.get_active_timer():
            QMessageBox.information(self, "Timer", "Não há atividade em andamento.")
            return
        answer = QMessageBox.question(
            self,
            "Cancelar timer",
            "Cancelar o timer atual sem gerar registro?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.db.clear_active_timer()
            self.refresh_timer_state()

    def refresh_timer_state(self) -> None:
        timer = self.db.get_active_timer()
        if timer:
            started = datetime.fromisoformat(timer["started_at"])
            elapsed = int((datetime.now() - started).total_seconds())
            self.elapsed_label.setText(format_duration(elapsed))
            description = f" — {timer['description']}" if timer["description"] else ""
            self.timer_status_label.setText(
                f"{timer['project_name']} • {timer['activity_type_name']}{description}"
            )
            self.start_button.setEnabled(False)
            self.finish_button.setEnabled(True)
            self.cancel_timer_button.setEnabled(True)
            self.project_combo.setEnabled(False)
            self.activity_combo.setEnabled(False)
            self.description_edit.setEnabled(False)
            self.tray.setToolTip(f"{APP_NAME} — {self.elapsed_label.text()}")
        else:
            self.elapsed_label.setText("00:00:00")
            self.timer_status_label.setText("Nenhuma atividade em andamento")
            self.start_button.setEnabled(True)
            self.finish_button.setEnabled(False)
            self.cancel_timer_button.setEnabled(False)
            self.project_combo.setEnabled(True)
            self.activity_combo.setEnabled(True)
            self.description_edit.setEnabled(True)
            self.tray.setToolTip(APP_NAME)

        self.update_pending_status()

    def _refresh_today_on_timer_tab(self, index: int) -> None:
        if self.tabs.widget(index) != self.timer_tab:
            return
        today = QDate.currentDate()
        if self.history_date.date() != today:
            self.history_date.setDate(today)
        else:
            self.refresh_history()

    def refresh_history(self) -> None:
        user_name = self.db.get_setting("user_name").strip()
        qdate = self.history_date.date()
        selected_date = datetime(qdate.year(), qdate.month(), qdate.day())
        rows = [item["data"] for item in self.db.list_task_records(
            user_name=user_name, selected_date=selected_date
        )]
        local_actions = [item["data"] for item in self.db.list_audit_actions()]
        rows = apply_audit_actions(rows, local_actions)

        valid_total_seconds = 0
        for row in rows:
            if str(row.get("excluido", "0")) != "1":
                try:
                    valid_total_seconds += int(row.get("duracao_segundos", "0"))
                except (ValueError, TypeError):
                    pass

        selected_status = self.history_status_filter.currentText()
        if selected_status == "Ativos":
            visible_rows = [row for row in rows if str(row.get("excluido", "0")) != "1"]
        elif selected_status == "Excluídos":
            visible_rows = [row for row in rows if str(row.get("excluido", "0")) == "1"]
        else:
            visible_rows = rows

        self.history_rows = visible_rows
        self.history_table.setRowCount(len(visible_rows))
        red_background = QColor("#FEE4E2")
        red_text = QColor("#B42318")
        for row_index, row in enumerate(visible_rows):
            deleted = str(row.get("excluido", "0")) == "1"
            observation = str(row.get("observacao", ""))
            if deleted:
                audit_note = (
                    f"Excluído por {row.get('usuario_exclusao', '')} em "
                    f"{row.get('data_exclusao', '')}. Motivo: {row.get('motivo_exclusao', '')}"
                ).strip()
                observation = f"{observation} | {audit_note}" if observation else audit_note
            values = [
                self._time_part(str(row.get("inicio", ""))),
                self._time_part(str(row.get("fim", ""))),
                row.get("projeto", ""),
                row.get("tipo_atividade", ""),
                row.get("descricao", ""),
                row.get("duracao_formatada", ""),
                row.get("origem_registro", "") or "TIMER",
                "EXCLUÍDO" if deleted else "ATIVO",
                observation,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if deleted:
                    item.setBackground(red_background)
                    item.setForeground(red_text)
                self.history_table.setItem(row_index, column, item)

        self.history_total_label.setText(
            f"Total válido: {format_duration(valid_total_seconds)}"
        )
        if selected_date.date() == datetime.now().date():
            self.today_total_label.setText(
                f"Total registrado hoje: {format_duration(valid_total_seconds)}"
            )
        self.update_pending_status()

    def show_history_details(self, row_index: int, _column_index: int = 0) -> None:
        if row_index < 0 or row_index >= len(self.history_rows):
            return
        HistoryDetailsDialog(self.history_rows[row_index], self).exec()

    def delete_selected_history_record(self) -> None:
        row_index = self.history_table.currentRow()
        if row_index < 0 or row_index >= len(self.history_rows):
            QMessageBox.information(self, "Excluir registro", "Selecione um registro no histórico.")
            return

        row = self.history_rows[row_index]
        if str(row.get("excluido", "0")) == "1":
            QMessageBox.information(
                self,
                "Excluir registro",
                "Esse registro já está excluído e permanece visível para auditoria.",
            )
            return

        reason, accepted = QInputDialog.getMultiLineText(
            self,
            "Motivo da exclusão",
            "Informe por que este registro deve deixar de contabilizar horas:",
        )
        reason = reason.strip()
        if not accepted:
            return
        if not reason:
            QMessageBox.warning(self, "Excluir registro", "O motivo da exclusão é obrigatório.")
            return

        summary = (
            f"Projeto: {row.get('projeto', '')}\n"
            f"Tipo: {row.get('tipo_atividade', '')}\n"
            f"Início: {row.get('inicio', '')}\n"
            f"Fim: {row.get('fim', '')}\n"
            f"Duração: {row.get('duracao_formatada', '')}\n\n"
            "O registro original será preservado, mas deixará de contabilizar horas."
        )
        answer = QMessageBox.question(
            self,
            "Confirmar exclusão",
            summary,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        user_name = self.db.get_setting("user_name").strip()
        if not user_name:
            QMessageBox.warning(
                self,
                "Excluir registro",
                "Configure o nome do usuário antes de excluir um registro.",
            )
            return
        action = {
            "acao_id": str(uuid.uuid4()),
            "registro_id": str(row.get("registro_id", "")),
            "acao": "EXCLUIR",
            "data_hora_acao": datetime.now().replace(microsecond=0).isoformat(sep=" "),
            "usuario_acao": user_name,
            "usuario_registro": row.get("usuario", "") or user_name,
            "motivo": reason,
            "computador": socket.gethostname(),
            "projeto": row.get("projeto", ""),
            "tipo_atividade": row.get("tipo_atividade", ""),
            "descricao": row.get("descricao", ""),
            "inicio": row.get("inicio", ""),
            "fim": row.get("fim", ""),
            "duracao_segundos": row.get("duracao_segundos", "0"),
            "duracao_formatada": row.get("duracao_formatada", ""),
            "origem_registro": row.get("origem_registro", "") or "TIMER",
            "observacao": row.get("observacao", ""),
            "data_registro": row.get("data_registro", ""),
        }

        try:
            self.db.add_audit_action(action)
            base_folder = self.db.get_setting("base_folder").strip()
            try:
                append_audit_action(base_folder, action)
                self.db.mark_audit_synced(action["acao_id"])
                message = "Registro excluído da contabilização e gravado na auditoria."
            except Exception as exc:
                self.db.mark_audit_error(action["acao_id"], str(exc))
                logging.warning("Exclusão mantida localmente para sincronização: %s", exc)
                message = (
                    "O registro deixou de contabilizar neste computador, mas a ação de exclusão "
                    "ainda não foi gravada na pasta compartilhada. Use Registrar Tasks."
                )
        except Exception as exc:
            logging.exception("Falha ao registrar exclusão")
            QMessageBox.critical(self, "Excluir registro", f"Não foi possível registrar a exclusão:\n{exc}")
            return

        self.refresh_history()
        self.update_pending_status()
        QMessageBox.information(self, "Excluir registro", message)

    @staticmethod
    def _time_part(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%H:%M:%S")
        except (ValueError, TypeError):
            return value

    def register_pending_records(self, show_result: bool = False) -> None:
        """Sincroniza tasks e ações de auditoria pendentes de forma idempotente."""
        base_folder = self.db.get_setting("base_folder").strip()
        if not base_folder:
            self.update_pending_status()
            if show_result:
                QMessageBox.warning(
                    self,
                    "Registrar Tasks",
                    "Configure a pasta-base dos CSVs antes de registrar os itens pendentes.",
                )
            return

        pending_records = self.db.list_task_records(pending_only=True)
        pending_actions = self.db.list_audit_actions(pending_only=True)
        if not pending_records and not pending_actions:
            self.update_pending_status()
            if show_result:
                QMessageBox.information(
                    self,
                    "Registrar Tasks",
                    "Não há tasks ou ações de auditoria pendentes.",
                )
            return

        registered = 0
        failed = 0
        for pending in pending_records:
            try:
                append_record(base_folder, pending["data"])
                self.db.mark_task_synced(pending["record_id"])
                registered += 1
                logging.info("Task %s sincronizada com CSV", pending["record_id"])
            except Exception as exc:
                self.db.mark_task_error(pending["record_id"], str(exc))
                failed += 1
                logging.warning("Task %s permanece no SQLite - falha ao acessar CSV: %s", pending["record_id"], exc)

        for pending in pending_actions:
            try:
                append_audit_action(base_folder, pending["data"])
                self.db.mark_audit_synced(pending["action_id"])
                registered += 1
            except Exception as exc:
                self.db.mark_audit_error(pending["action_id"], str(exc))
                failed += 1
                logging.warning(
                    "Ação de auditoria %s não registrada no CSV: %s",
                    pending["action_id"],
                    exc,
                )

        self.update_pending_status()
        if registered:
            self.refresh_history()

        if show_result:
            if registered and not failed:
                QMessageBox.information(
                    self,
                    "Registrar Tasks",
                    f"{registered} item(ns) registrado(s) com sucesso.",
                )
            elif registered and failed:
                QMessageBox.warning(
                    self,
                    "Registrar Tasks",
                    f"{registered} item(ns) registrado(s) e {failed} permaneceram com falha.",
                )
            else:
                QMessageBox.warning(
                    self,
                    "Registrar Tasks",
                    "Nenhum item foi registrado. Os dados continuam seguros no SQLite com status Falha.",
                )

    def update_pending_status(self) -> None:
        pending_records = self.db.list_task_records(pending_only=True)
        pending_actions = self.db.list_audit_actions(pending_only=True)
        count = len(pending_records) + len(pending_actions)
        failed = sum(1 for item in pending_records if item.get("status") == "FALHA")
        failed += sum(1 for item in pending_actions if item.get("status") == "FALHA")

        self.pending_label.setText(
            f"Itens aguardando registro: {count} | Com falha: {failed}"
        )
        self.timer_pending_label.setText(f"Itens pendentes: {count}")
        self.register_tasks_button.setEnabled(count > 0)

        table_items: list[tuple[str, dict[str, object], dict[str, object]]] = []
        table_items.extend(("TASK", item, item["data"]) for item in pending_records)
        table_items.extend(("EXCLUSÃO", item, item["data"]) for item in pending_actions)
        self.pending_table.setRowCount(len(table_items))
        for row_index, (item_type, item, data) in enumerate(table_items):
            values = [
                item_type,
                data.get("projeto", ""),
                data.get("tipo_atividade", "") if item_type == "TASK" else data.get("acao", "EXCLUIR"),
                data.get("origem_registro", "") or "TIMER",
                data.get("inicio", ""),
                item.get("status", "PENDENTE"),
                str(item.get("attempts", 0)),
                item.get("last_error", ""),
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if item_type == "EXCLUSÃO":
                    cell.setBackground(QColor("#FEE4E2"))
                    cell.setForeground(QColor("#B42318"))
                self.pending_table.setItem(row_index, column, cell)

        if count:
            self.connection_label.setText(f"{count} item(ns) aguardando registro nos CSVs")
        elif not self.connection_label.text().startswith("Pasta compartilhada"):
            self.connection_label.setText("")

    def import_existing_csvs(self) -> None:
        user_name = self.db.get_setting("user_name").strip()
        base_folder = self.db.get_setting("base_folder").strip()
        if not user_name or not base_folder:
            QMessageBox.warning(self, "Importar CSVs", "Configure o usuário e a pasta-base antes de importar.")
            return
        try:
            imported = self.db.import_task_records(read_all_records(base_folder, user_name))
            logging.info("Importação de CSV concluída: %s registro(s) novo(s)", imported)
            self.refresh_history()
            QMessageBox.information(self, "Importar CSVs", f"{imported} registro(s) histórico(s) importado(s) para o SQLite.")
        except Exception as exc:
            logging.exception("Falha ao importar CSVs")
            QMessageBox.warning(self, "Importar CSVs", f"Não foi possível importar os CSVs:\n{exc}")

    def reconcile_csv_records(self) -> None:
        user_name = self.db.get_setting("user_name").strip()
        base_folder = self.db.get_setting("base_folder").strip()
        if not user_name or not base_folder:
            QMessageBox.warning(self, "Reconstruir CSVs", "Configure o usuário e a pasta-base antes de reconstruir.")
            return
        confirmed = 0
        failed = 0
        for item in self.db.list_task_records(user_name=user_name):
            try:
                append_record(base_folder, item["data"])
                self.db.mark_task_synced(item["record_id"])
                confirmed += 1
                logging.info("Task %s confirmada no CSV durante reconciliação", item["record_id"])
            except Exception as exc:
                self.db.mark_task_error(item["record_id"], str(exc))
                failed += 1
                logging.warning("Task %s permanece no SQLite - falha na reconciliação: %s", item["record_id"], exc)
        self.update_pending_status()
        if failed:
            QMessageBox.warning(self, "Reconstruir CSVs", f"{confirmed} task(s) confirmada(s); {failed} falharam.")
        else:
            QMessageBox.information(self, "Reconstruir CSVs", f"{confirmed} task(s) reconciliada(s) com os CSVs.")

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.show_from_tray()

    def show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def exit_application(self) -> None:
        self.force_quit = True
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.force_quit or not self.tray.isVisible():
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage(
            APP_NAME,
            "O Timer Task Master continua ativo na bandeja do Windows.",
            QSystemTrayIcon.MessageIcon.Information,
            2500,
        )


def exception_hook(exc_type, exc_value, exc_traceback) -> None:
    details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logging.critical("Erro não tratado:\n%s", details)
    try:
        QMessageBox.critical(
            None,
            "Erro no Timer Task Master",
            f"Ocorreu um erro inesperado. Consulte o log:\n{LOG_PATH}\n\n{exc_value}",
        )
    finally:
        sys.__excepthook__(exc_type, exc_value, exc_traceback)


def main() -> int:
    sys.excepthook = exception_hook
    application = QApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    application.setQuitOnLastWindowClosed(False)
    app_icon = load_app_icon()
    if not app_icon.isNull():
        application.setWindowIcon(app_icon)

    instance_lock = QLockFile(str(app_data_dir() / "timertask.lock"))
    instance_lock.setStaleLockTime(30_000)
    if not instance_lock.tryLock(100):
        QMessageBox.information(
            None,
            APP_NAME,
            "O Timer Task Master já está aberto. Verifique o ícone na bandeja do Windows.",
        )
        return 0

    db = Database(app_data_dir() / "timertask.db")
    window = MainWindow(db)
    window.instance_lock = instance_lock
    window.show()
    logging.info("Timer Task Master iniciado")
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
