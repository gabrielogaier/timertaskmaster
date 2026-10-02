from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from csv_store import apply_audit_actions
from database import Database


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


def read_local_records(
    db: Database,
    selected_date: date | None = None,
    year: int | None = None,
    months: list[int] | None = None,
) -> list[CsvRecord]:
    """Consulta somente o usuário configurado, incluindo pendências e auditoria."""
    name = db.get_setting("user_name").strip()
    if not name:
        return []
    selected = datetime.combine(selected_date, datetime.min.time()) if selected_date else None
    rows = [item["data"] for item in db.list_task_records(user_name=name, selected_date=selected)]
    rows = apply_audit_actions(rows, [item["data"] for item in db.list_audit_actions()])
    records = []
    for row in rows:
        start = datetime.fromisoformat(str(row["inicio"]))
        if year is not None and (start.year != year or start.month not in (months or [])):
            continue
        records.append(CsvRecord(
            record_id=str(row["registro_id"]), user=name,
            origin=str(row.get("origem_registro") or "TIMER"),
            project=str(row.get("projeto", "")), activity_type=str(row.get("tipo_atividade", "")),
            description=str(row.get("descricao", "")), start=start,
            end=datetime.fromisoformat(str(row["fim"])),
            duration_seconds=max(0, int(row.get("duracao_segundos", 0))),
            observation=str(row.get("observacao", "")), computer=str(row.get("computador", "")),
            registered_at=str(row.get("data_registro", "")), source_file=str(db.db_path),
            deleted=str(row.get("excluido", "0")) == "1",
            deletion_reason=str(row.get("motivo_exclusao", "")),
            deleted_at=str(row.get("data_exclusao", "")), deleted_by=str(row.get("usuario_exclusao", "")),
            audit_action_id=str(row.get("acao_id_exclusao", "")),
        ))
    return sorted(records, key=lambda record: (record.start, record.record_id))
