from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CsvRecord:
    record_id: str
    user: str
    origin: str
    project: str
    activity_type: str
    description: str
    start: datetime
    end: datetime
    duration_seconds: int
    observation: str
    computer: str
    registered_at: str
    source_file: str
    deleted: bool = False
    deletion_reason: str = ""
    deleted_at: str = ""
    deleted_by: str = ""
    audit_action_id: str = ""


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _read_csv_rows(file_path: Path) -> Iterable[dict[str, str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            with file_path.open("r", newline="", encoding=encoding) as csv_file:
                reader = csv.DictReader(csv_file, delimiter=";")
                if not reader.fieldnames:
                    return []
                return [
                    {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
                    for row in reader
                ]
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return []


def _parse_datetime(value: str) -> datetime:
    cleaned = value.strip().replace("Z", "+00:00")
    if not cleaned:
        raise ValueError("Data/hora vazia")
    try:
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
            try:
                return datetime.strptime(cleaned, pattern)
            except ValueError:
                continue
    raise ValueError(f"Data/hora inválida: {value}")


def _is_audit_file(path: Path) -> bool:
    return any(part.casefold() == "auditoria" for part in path.parts)


def _candidate_csv_files(folder: str, selected_date: date | None = None) -> list[Path]:
    root = Path(folder)
    if not root.exists() or not root.is_dir():
        return []
    pattern = f"{selected_date:%Y-%m}.csv" if selected_date is not None else "*.csv"
    return sorted(
        path
        for path in root.rglob(pattern)
        if path.is_file() and not _is_audit_file(path)
    )


def _candidate_audit_files(folder: str, selected_date: date | None = None) -> list[Path]:
    root = Path(folder)
    if not root.exists() or not root.is_dir():
        return []
    pattern = f"{selected_date:%Y-%m}.csv" if selected_date is not None else "*.csv"
    return sorted(
        path
        for path in root.rglob(pattern)
        if path.is_file() and _is_audit_file(path)
    )


def discover_users(folder: str) -> list[str]:
    """Detecta os nomes gravados na coluna usuario dos CSVs de tasks."""
    names: dict[str, str] = {}
    files = _candidate_csv_files(folder)
    files = sorted(files, key=lambda item: item.stat().st_mtime, reverse=True)[:100]
    for file_path in files:
        try:
            for row in _read_csv_rows(file_path):
                name = row.get("usuario", "").strip()
                if name:
                    names.setdefault(name.casefold(), name)
        except (OSError, csv.Error, UnicodeError):
            continue
    return sorted(names.values(), key=str.casefold)


def count_csv_files(folder: str) -> int:
    return len(_candidate_csv_files(folder))


def _latest_audit_actions(folder: str, selected_date: date | None = None) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    seen_action_ids: set[str] = set()
    for file_path in _candidate_audit_files(folder, selected_date):
        for row in _read_csv_rows(file_path):
            action_id = row.get("acao_id", "").strip()
            if action_id and action_id in seen_action_ids:
                continue
            if action_id:
                seen_action_ids.add(action_id)
            record_id = row.get("registro_id", "").strip()
            if not record_id:
                continue
            current = latest.get(record_id)
            key = (row.get("data_hora_acao", ""), action_id)
            current_key = (
                current.get("data_hora_acao", "") if current else "",
                current.get("acao_id", "") if current else "",
            )
            if current is None or key >= current_key:
                latest[record_id] = row
    return latest



def apply_audit_actions_to_records(
    records: list[CsvRecord],
    actions: Iterable[dict[str, str]],
) -> list[CsvRecord]:
    """Aplica ações locais ainda não sincronizadas ao dashboard do próprio Master."""
    latest: dict[str, dict[str, str]] = {}
    for action in actions:
        record_id = str(action.get("registro_id", "")).strip()
        if not record_id:
            continue
        current = latest.get(record_id)
        key = (str(action.get("data_hora_acao", "")), str(action.get("acao_id", "")))
        current_key = (
            str(current.get("data_hora_acao", "")) if current else "",
            str(current.get("acao_id", "")) if current else "",
        )
        if current is None or key >= current_key:
            latest[record_id] = action

    updated: list[CsvRecord] = []
    for record in records:
        action = latest.get(record.record_id)
        if action is None:
            updated.append(record)
            continue
        deleted = str(action.get("acao", "")).upper() == "EXCLUIR"
        updated.append(
            replace(
                record,
                deleted=deleted,
                deletion_reason=str(action.get("motivo", "")) if deleted else "",
                deleted_at=str(action.get("data_hora_acao", "")) if deleted else "",
                deleted_by=str(action.get("usuario_acao", "")) if deleted else "",
                audit_action_id=str(action.get("acao_id", "")) if deleted else "",
            )
        )
    return updated

def read_records(folder: str, source_user: str, selected_date: date) -> list[CsvRecord]:
    target_user = source_user.strip().casefold()
    deduplicated: dict[str, CsvRecord] = {}
    date_prefix = selected_date.isoformat()
    # A exclusão pode ter sido registrada em um mês posterior ao registro original.
    # Por isso, leia toda a trilha de auditoria ao montar o estado atual.
    audit_actions = _latest_audit_actions(folder)

    for file_path in _candidate_csv_files(folder, selected_date):
        for row_number, row in enumerate(_read_csv_rows(file_path), start=2):
            user = row.get("usuario", "").strip()
            if target_user and user.casefold() != target_user:
                continue
            start_text = row.get("inicio", "").strip()
            if not start_text.startswith(date_prefix) and not start_text.startswith(
                selected_date.strftime("%d/%m/%Y")
            ):
                continue
            try:
                start = _parse_datetime(start_text)
                end = _parse_datetime(row.get("fim", ""))
            except ValueError:
                continue
            if start.date() != selected_date:
                continue

            try:
                duration_seconds = int(float(row.get("duracao_segundos", "0") or 0))
            except ValueError:
                duration_seconds = 0
            if duration_seconds <= 0:
                duration_seconds = max(0, int((end - start).total_seconds()))

            record_id = row.get("registro_id", "").strip()
            if not record_id:
                record_id = f"{file_path.resolve()}::{row_number}::{start.isoformat()}"

            audit = audit_actions.get(record_id, {})
            deleted = str(audit.get("acao", "")).upper() == "EXCLUIR"
            record = CsvRecord(
                record_id=record_id,
                user=user or source_user,
                origin=(row.get("origem_registro", "TIMER") or "TIMER").upper(),
                project=row.get("projeto", "Sem projeto") or "Sem projeto",
                activity_type=row.get("tipo_atividade", "Sem tipo") or "Sem tipo",
                description=row.get("descricao", ""),
                start=start,
                end=end,
                duration_seconds=duration_seconds,
                observation=row.get("observacao", ""),
                computer=row.get("computador", ""),
                registered_at=row.get("data_registro", ""),
                source_file=str(file_path),
                deleted=deleted,
                deletion_reason=audit.get("motivo", "") if deleted else "",
                deleted_at=audit.get("data_hora_acao", "") if deleted else "",
                deleted_by=audit.get("usuario_acao", "") if deleted else "",
                audit_action_id=audit.get("acao_id", "") if deleted else "",
            )
            deduplicated[record_id] = record

    return sorted(deduplicated.values(), key=lambda item: (item.start, item.end, item.record_id))



def read_records_for_months(
    folder: str,
    source_user: str,
    year: int,
    months: Iterable[int],
) -> list[CsvRecord]:
    """Lê uma vez cada CSV mensal selecionado e devolve os registros deduplicados."""
    selected_months = sorted({int(month) for month in months if 1 <= int(month) <= 12})
    if not selected_months:
        return []

    target_user = source_user.strip().casefold()
    deduplicated: dict[str, CsvRecord] = {}
    audit_actions = _latest_audit_actions(folder)
    files: set[Path] = set()
    for month in selected_months:
        files.update(_candidate_csv_files(folder, date(int(year), month, 1)))

    for file_path in sorted(files):
        for row_number, row in enumerate(_read_csv_rows(file_path), start=2):
            user = row.get("usuario", "").strip()
            if target_user and user.casefold() != target_user:
                continue
            try:
                start = _parse_datetime(row.get("inicio", ""))
                end = _parse_datetime(row.get("fim", ""))
            except ValueError:
                continue
            if start.year != int(year) or start.month not in selected_months:
                continue

            try:
                duration_seconds = int(float(row.get("duracao_segundos", "0") or 0))
            except ValueError:
                duration_seconds = 0
            if duration_seconds <= 0:
                duration_seconds = max(0, int((end - start).total_seconds()))

            record_id = row.get("registro_id", "").strip()
            if not record_id:
                record_id = f"{file_path.resolve()}::{row_number}::{start.isoformat()}"

            audit = audit_actions.get(record_id, {})
            deleted = str(audit.get("acao", "")).upper() == "EXCLUIR"
            deduplicated[record_id] = CsvRecord(
                record_id=record_id,
                user=user or source_user,
                origin=(row.get("origem_registro", "TIMER") or "TIMER").upper(),
                project=row.get("projeto", "Sem projeto") or "Sem projeto",
                activity_type=row.get("tipo_atividade", "Sem tipo") or "Sem tipo",
                description=row.get("descricao", ""),
                start=start,
                end=end,
                duration_seconds=duration_seconds,
                observation=row.get("observacao", ""),
                computer=row.get("computador", ""),
                registered_at=row.get("data_registro", ""),
                source_file=str(file_path),
                deleted=deleted,
                deletion_reason=audit.get("motivo", "") if deleted else "",
                deleted_at=audit.get("data_hora_acao", "") if deleted else "",
                deleted_by=audit.get("usuario_acao", "") if deleted else "",
                audit_action_id=audit.get("acao_id", "") if deleted else "",
            )

    return sorted(deduplicated.values(), key=lambda item: (item.start, item.end, item.record_id))
