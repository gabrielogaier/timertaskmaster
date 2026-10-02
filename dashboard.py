from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from dashboard_data import CsvRecord, format_duration, read_local_records


class DashboardMixin:
    """Tela comum às edições pessoal e de gestão."""

    def _dashboard_users(self) -> list[dict]:
        name = self.db.get_setting("user_name").strip()
        return [{"id": 0, "display_name": name, "source_user": name}] if name else []

    def refresh_local_dashboard(self) -> None:
        self.refresh_dashboard()

    def refresh_dashboard(self) -> None:
        selected = self.date_edit.date().toPython()
        self.loaded_records = {0: read_local_records(self.db, selected)}
        self.user_errors = {}
        records = self.loaded_records[0]
        self._replace_combo_items(self.project_filter, ["Todos", *sorted({r.project for r in records}, key=str.casefold)])
        self._replace_combo_items(self.activity_filter, ["Todos", *sorted({r.activity_type for r in records}, key=str.casefold)])
        self.populate_dashboard_tree()
        self.dashboard_status.setText(
            f"Banco local · Atualizado em {datetime.now():%d/%m/%Y %H:%M:%S}. "
            f"Data consultada: {selected:%d/%m/%Y}."
        )

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
        if hasattr(self, "export_dashboard"):
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
        if hasattr(self, "export_dashboard"):
            filters.addWidget(self.export_button)
        filters.addWidget(expand_button)
        filters.addWidget(collapse_button)
        layout.addLayout(filters)

        cards = QHBoxLayout()
        self.monitored_label = self._metric_card("Usuários no dashboard", "0")
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
        users = self._dashboard_users()
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
                QTreeWidgetItem(["Configure o nome do usuário na aba Configurações para visualizar seus registros."])
            )

    def expand_users(self) -> None:
        for index in range(self.dashboard_tree.topLevelItemCount()):
            self.dashboard_tree.topLevelItem(index).setExpanded(True)
