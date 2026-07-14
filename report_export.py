from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Sequence

try:
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.table import Table, TableStyleInfo
    from openpyxl.utils import get_column_letter
except ModuleNotFoundError:
    Workbook = None
    BarChart = Reference = None
    Alignment = Border = Font = PatternFill = Side = None
    Table = TableStyleInfo = None
    get_column_letter = None

from csv_reader import CsvRecord

APP_TITLE = "Timer Task Master"

NAVY = "13213A"
BLUE = "1D4ED8"
LIGHT_BLUE = "E8F0FF"
PALE = "F6F8FC"
WHITE = "FFFFFF"
TEXT = "172033"
MUTED = "667085"
RED = "B42318"
LIGHT_RED = "FEE4E2"
BORDER = "D7DEEA"

RecordEntry = tuple[str, CsvRecord]

EXCEL_DURATION_FORMAT = '[h]:mm "h"'
SECONDS_PER_DAY = 24 * 60 * 60


def format_report_duration(total_seconds: int) -> str:
    """Format a report duration rounded to the nearest minute."""
    total_minutes = round(max(0, int(total_seconds)) / 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d} h"


def _excel_duration_value(total_seconds: int) -> float:
    """Convert seconds to a real Excel duration value.

    Excel stores durations as fractions of a day. The [h]:mm number format
    displays the rounded minute while preserving the underlying seconds for
    sums, filtered totals and charts.
    """
    return max(0, int(total_seconds)) / SECONDS_PER_DAY


def _normalized_path(path: str | Path, suffix: str) -> Path:
    target = Path(path)
    if target.suffix.casefold() != suffix.casefold():
        target = target.with_suffix(suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _record_rows(entries: Iterable[RecordEntry]) -> list[list[object]]:
    rows: list[list[object]] = []
    for monitored_user, record in entries:
        rows.append(
            [
                monitored_user,
                record.user,
                record.project,
                record.activity_type,
                record.description,
                record.start,
                record.end,
                record.duration_seconds,
                format_report_duration(record.duration_seconds),
                record.origin,
                "EXCLUÍDO" if record.deleted else "ATIVO",
                record.observation,
                record.deletion_reason,
                record.deleted_by,
                record.deleted_at,
                record.computer,
                record.registered_at,
                record.record_id,
                record.source_file,
            ]
        )
    return rows


def _excel_record_rows(entries: Iterable[RecordEntry]) -> list[list[object]]:
    """Return report rows plus numeric helper columns used by SUBTOTAL.

    The helper columns remain hidden in Excel.  Because they contain numeric
    flags, SUBTOTAL can recalculate the management KPIs whenever the user
    filters the Registros table.
    """
    rows: list[list[object]] = []
    for row in _record_rows(entries):
        deleted = row[10] == "EXCLUÍDO"
        manual = row[9] == "MANUAL"
        duration_seconds = int(row[7] or 0)
        excel_row = list(row)
        # Column I is a real Excel duration instead of a preformatted string.
        excel_row[8] = _excel_duration_value(duration_seconds)
        rows.append(
            excel_row
            + [
                0 if deleted else _excel_duration_value(duration_seconds),
                0 if deleted else 1,
                1 if manual and not deleted else 0,
                1 if deleted else 0,
            ]
        )
    return rows


def export_csv(path: str | Path, entries: Sequence[RecordEntry]) -> Path:
    target = _normalized_path(path, ".csv")
    headers = [
        "usuario_monitorado",
        "usuario_registro",
        "projeto",
        "tipo_atividade",
        "descricao",
        "inicio",
        "fim",
        "duracao_segundos",
        "duracao_formatada",
        "origem_registro",
        "status",
        "observacao",
        "motivo_exclusao",
        "excluido_por",
        "excluido_em",
        "computador",
        "data_registro",
        "registro_id",
        "arquivo_origem",
    ]
    with target.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        for row in _record_rows(entries):
            serialized = list(row)
            serialized[5] = row[5].strftime("%Y-%m-%d %H:%M:%S")
            serialized[6] = row[6].strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow(serialized)
    return target


def _style_title(cell) -> None:
    cell.fill = PatternFill("solid", fgColor=NAVY)
    cell.font = Font(color=WHITE, bold=True, size=18)
    cell.alignment = Alignment(vertical="center")


def _style_header_row(sheet, row: int, start_col: int, end_col: int) -> None:
    thin = Side(style="thin", color=BORDER)
    for column in range(start_col, end_col + 1):
        cell = sheet.cell(row=row, column=column)
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(color=WHITE, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)


def _autosize(sheet, min_width: int = 11, max_width: int = 45) -> None:
    for column_cells in sheet.columns:
        letter = get_column_letter(column_cells[0].column)
        length = 0
        for cell in column_cells:
            value = cell.value
            if value is None:
                continue
            text = value.strftime("%d/%m/%Y %H:%M") if isinstance(value, datetime) else str(value)
            length = max(length, max((len(line) for line in text.splitlines()), default=0))
        sheet.column_dimensions[letter].width = max(min_width, min(max_width, length + 2))


def _add_table(sheet, start_row: int, end_row: int, end_col: int, name: str) -> None:
    if end_row <= start_row:
        return
    reference = f"A{start_row}:{get_column_letter(end_col)}{end_row}"
    table = Table(displayName=name, ref=reference)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    sheet.add_table(table)


def _write_detail_sheet(
    workbook: Workbook,
    title: str,
    entries: Sequence[RecordEntry],
    table_name: str,
    deleted_style: bool = False,
):
    sheet = workbook.create_sheet(title)
    headers = [
        "Usuário monitorado",
        "Usuário do registro",
        "Projeto",
        "Tipo de atividade",
        "Descrição",
        "Início",
        "Fim",
        "Duração (s)",
        "Duração",
        "Origem",
        "Status",
        "Observação",
        "Motivo da exclusão",
        "Excluído por",
        "Excluído em",
        "Computador",
        "Data de registro",
        "UUID",
        "Arquivo de origem",
        "Horas contabilizadas",
        "Registros contabilizados",
        "Registros manuais",
        "Registros excluídos",
    ]
    sheet.append(headers)
    _style_header_row(sheet, 1, 1, len(headers))

    excel_rows = _excel_record_rows(entries)
    for row_index, values in enumerate(excel_rows, start=2):
        sheet.append(values)
        sheet.cell(row_index, 6).number_format = "dd/mm/yyyy hh:mm"
        sheet.cell(row_index, 7).number_format = "dd/mm/yyyy hh:mm"
        sheet.cell(row_index, 9).number_format = EXCEL_DURATION_FORMAT
        sheet.cell(row_index, 20).number_format = EXCEL_DURATION_FORMAT
        if deleted_style or values[10] == "EXCLUÍDO":
            for column in range(1, 20):
                cell = sheet.cell(row_index, column)
                cell.fill = PatternFill("solid", fgColor=LIGHT_RED)
                cell.font = Font(color=RED)

    if not entries:
        sheet.cell(2, 1, "Nenhum registro para os filtros selecionados.")
        sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=19)
        sheet.cell(2, 1).font = Font(color=MUTED, italic=True)

    sheet.freeze_panes = "A2"
    # A tabela já fornece os filtros de coluna. Não configure também
    # worksheet.auto_filter no mesmo intervalo.
    _add_table(sheet, 1, len(entries) + 1, len(headers), table_name)
    _autosize(sheet)
    sheet.column_dimensions["E"].width = 34
    sheet.column_dimensions["L"].width = 34
    sheet.column_dimensions["M"].width = 30
    sheet.column_dimensions["S"].width = 48

    # Numeric helper columns power the dynamic KPIs but do not clutter the
    # exported report. They remain part of the table so filters hide the same
    # rows and SUBTOTAL reacts immediately.
    # Raw seconds remain available in the file for auditing, but the visible
    # duration is the real Excel time value in column I.
    sheet.column_dimensions["H"].hidden = True
    for column in ("T", "U", "V", "W"):
        sheet.column_dimensions[column].hidden = True
    return sheet


def export_excel(
    path: str | Path,
    entries: Sequence[RecordEntry],
    report_date: date,
    filters: dict[str, str],
    generated_at: datetime | None = None,
    period_label: str | None = None,
) -> Path:
    if Workbook is None:
        raise RuntimeError(
            "A dependência openpyxl não está instalada. Feche o aplicativo e execute "
            "run_timertaskmaster.bat ou run_debug.bat para instalar as dependências."
        )

    target = _normalized_path(path, ".xlsx")
    generated_at = generated_at or datetime.now()
    active_entries = [(user, record) for user, record in entries if not record.deleted]
    deleted_entries = [(user, record) for user, record in entries if record.deleted]

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Resumo"
    summary.sheet_view.showGridLines = False
    summary.merge_cells("A1:H2")
    summary["A1"] = f"{APP_TITLE} — Relatório de horas"
    _style_title(summary["A1"])
    summary.row_dimensions[1].height = 26
    summary.row_dimensions[2].height = 12

    if period_label:
        summary["A4"] = "Período consultado"
        summary["B4"] = period_label
    else:
        summary["A4"] = "Data consultada"
        summary["B4"] = report_date
        summary["B4"].number_format = "dd/mm/yyyy"
    summary["D4"] = "Gerado em"
    summary["E4"] = generated_at
    summary["E4"].number_format = "dd/mm/yyyy hh:mm"

    summary["A6"] = "Filtros aplicados"
    summary["A6"].font = Font(bold=True, color=NAVY)
    row = 7
    for label, value in (
        ("Projeto", filters.get("projeto", "Todos")),
        ("Tipo de atividade", filters.get("tipo", "Todos")),
        ("Origem", filters.get("origem", "Todos")),
        ("Status", filters.get("status", "Todos")),
        ("Escopo", filters.get("escopo", "Filtros atuais do Dashboard")),
    ):
        summary.cell(row=row, column=1, value=label)
        summary.cell(row=row, column=2, value=value)
        row += 1

    cards = [
        ("Horas válidas", None),
        ("Registros válidos", None),
        ("Registros manuais", None),
        ("Registros excluídos", None),
    ]
    card_columns = [1, 3, 5, 7]
    value_cells = []
    for column, (label, _value) in zip(card_columns, cards):
        label_cell = summary.cell(row=12, column=column, value=label)
        value_cell = summary.cell(row=13, column=column)
        value_cells.append(value_cell)
        summary.merge_cells(start_row=12, start_column=column, end_row=12, end_column=column + 1)
        summary.merge_cells(start_row=13, start_column=column, end_row=14, end_column=column + 1)
        label_cell.fill = PatternFill("solid", fgColor=LIGHT_BLUE)
        label_cell.font = Font(bold=True, color=NAVY)
        label_cell.alignment = Alignment(horizontal="center", vertical="center")
        value_cell.fill = PatternFill("solid", fgColor=WHITE)
        value_cell.font = Font(bold=True, color=TEXT, size=18)
        value_cell.alignment = Alignment(horizontal="center", vertical="center")

    user_summary: dict[str, dict[str, int]] = defaultdict(lambda: {"seconds": 0, "records": 0, "manual": 0, "deleted": 0})
    project_summary: dict[str, dict[str, int]] = defaultdict(lambda: {"seconds": 0, "records": 0, "manual": 0, "deleted": 0})
    for monitored_user, record in entries:
        user_metrics = user_summary[monitored_user]
        project_metrics = project_summary[record.project]
        if record.deleted:
            user_metrics["deleted"] += 1
            project_metrics["deleted"] += 1
            continue
        for metrics in (user_metrics, project_metrics):
            metrics["seconds"] += record.duration_seconds
            metrics["records"] += 1
            if record.origin == "MANUAL":
                metrics["manual"] += 1

    user_sheet = workbook.create_sheet("Usuários")
    user_headers = ["Usuário", "Horas válidas", "Registros", "Manuais", "Excluídos"]
    user_sheet.append(user_headers)
    _style_header_row(user_sheet, 1, 1, len(user_headers))
    for name in sorted(user_summary, key=str.casefold):
        metrics = user_summary[name]
        user_sheet.append([
            name,
            _excel_duration_value(metrics["seconds"]),
            metrics["records"],
            metrics["manual"],
            metrics["deleted"],
        ])
    for cell in user_sheet["B"][1:]:
        cell.number_format = EXCEL_DURATION_FORMAT
    user_sheet.freeze_panes = "A2"
    _add_table(user_sheet, 1, len(user_summary) + 1, len(user_headers), "tbUsuarios")
    _autosize(user_sheet)

    project_sheet = workbook.create_sheet("Projetos")
    project_headers = ["Projeto", "Horas válidas", "Registros", "Manuais", "Excluídos"]
    project_sheet.append(project_headers)
    _style_header_row(project_sheet, 1, 1, len(project_headers))
    for name in sorted(project_summary, key=str.casefold):
        metrics = project_summary[name]
        project_sheet.append([
            name,
            _excel_duration_value(metrics["seconds"]),
            metrics["records"],
            metrics["manual"],
            metrics["deleted"],
        ])
    for cell in project_sheet["B"][1:]:
        cell.number_format = EXCEL_DURATION_FORMAT
    project_sheet.freeze_panes = "A2"
    _add_table(project_sheet, 1, len(project_summary) + 1, len(project_headers), "tbProjetos")
    _autosize(project_sheet)

    _write_detail_sheet(workbook, "Registros", entries, "tbRegistros")
    _write_detail_sheet(workbook, "Auditoria", deleted_entries, "tbAuditoria", deleted_style=True)

    # Dynamic management summary. Filters applied directly in Registros,
    # Usuários or Projetos are detected through SUBTOTAL. The first filtered
    # source in the order Registros > Usuários > Projetos controls the cards.
    registros_end = max(2, len(entries) + 1)
    usuarios_end = max(2, len(user_summary) + 1)
    projetos_end = max(2, len(project_summary) + 1)

    registros_filtered = (
        f'SUBTOTAL(103,Registros!$R$2:$R${registros_end})'
        f'<COUNTA(Registros!$R$2:$R${registros_end})'
    )
    usuarios_filtered = (
        f'SUBTOTAL(103,Usuários!$A$2:$A${usuarios_end})'
        f'<COUNTA(Usuários!$A$2:$A${usuarios_end})'
    )
    projetos_filtered = (
        f'SUBTOTAL(103,Projetos!$A$2:$A${projetos_end})'
        f'<COUNTA(Projetos!$A$2:$A${projetos_end})'
    )

    source_formula = (
        f'=IF({registros_filtered},"Registros",'
        f'IF({usuarios_filtered},"Usuários",'
        f'IF({projetos_filtered},"Projetos","Todos os registros")))'
    )
    summary["A16"] = "Fonte ativa dos indicadores"
    summary["A16"].font = Font(bold=True, color=NAVY)
    summary["B16"] = source_formula
    summary["B16"].font = Font(bold=True, color=BLUE)
    summary.merge_cells("B16:D16")
    summary["E16"] = "Prioridade: Registros > Usuários > Projetos"
    summary["E16"].font = Font(color=MUTED, italic=True, size=9)
    summary.merge_cells("E16:H16")

    def dynamic_metric(reg_col: str, user_col: str, project_col: str) -> str:
        return (
            f'=IF({registros_filtered},SUBTOTAL(109,Registros!${reg_col}$2:${reg_col}${registros_end}),'
            f'IF({usuarios_filtered},SUBTOTAL(109,Usuários!${user_col}$2:${user_col}${usuarios_end}),'
            f'IF({projetos_filtered},SUBTOTAL(109,Projetos!${project_col}$2:${project_col}${projetos_end}),'
            f'SUM(Registros!${reg_col}$2:${reg_col}${registros_end}))))'
        )

    # Hidden helper columns in Registros: T hours, U active records,
    # V active manual records, W deleted records. Aggregate sheets expose the
    # equivalent metrics in B/C/D/E.
    value_cells[0].value = dynamic_metric("T", "B", "B")
    value_cells[0].number_format = EXCEL_DURATION_FORMAT
    value_cells[1].value = dynamic_metric("U", "C", "C")
    value_cells[1].number_format = "0"
    value_cells[2].value = dynamic_metric("V", "D", "D")
    value_cells[2].number_format = "0"
    value_cells[3].value = dynamic_metric("W", "E", "E")
    value_cells[3].number_format = "0"

    if user_summary:
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = "Horas por usuário"
        chart.y_axis.title = "Usuário"
        chart.x_axis.title = "Duração"
        chart.x_axis.numFmt = EXCEL_DURATION_FORMAT
        data = Reference(user_sheet, min_col=2, min_row=1, max_row=len(user_summary) + 1)
        categories = Reference(user_sheet, min_col=1, min_row=2, max_row=len(user_summary) + 1)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(categories)
        chart.height = 7
        chart.width = 12
        chart.visible_cells_only = True
        summary.add_chart(chart, "A18")

    if project_summary:
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = "Horas por projeto"
        chart.y_axis.title = "Projeto"
        chart.x_axis.title = "Duração"
        chart.x_axis.numFmt = EXCEL_DURATION_FORMAT
        data = Reference(project_sheet, min_col=2, min_row=1, max_row=len(project_summary) + 1)
        categories = Reference(project_sheet, min_col=1, min_row=2, max_row=len(project_summary) + 1)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(categories)
        chart.height = 7
        chart.width = 12
        chart.visible_cells_only = True
        summary.add_chart(chart, "I18")

    for column in range(1, 17):
        summary.column_dimensions[get_column_letter(column)].width = 13
    summary.column_dimensions["A"].width = 20
    summary.column_dimensions["B"].width = 18
    summary.freeze_panes = "A4"

    workbook.calculation.calcMode = "auto"
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.save(target)
    return target
