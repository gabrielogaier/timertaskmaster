from __future__ import annotations

import csv
import os
import re
import shutil
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator


CSV_FIELDS = [
    "registro_id",
    "usuario",
    "origem_registro",
    "projeto",
    "tipo_atividade",
    "descricao",
    "inicio",
    "fim",
    "duracao_segundos",
    "duracao_formatada",
    "observacao",
    "computador",
    "data_registro",
]

AUDIT_FIELDS = [
    "acao_id",
    "registro_id",
    "acao",
    "data_hora_acao",
    "usuario_acao",
    "usuario_registro",
    "motivo",
    "computador",
    "projeto",
    "tipo_atividade",
    "descricao",
    "inicio",
    "fim",
    "duracao_segundos",
    "duracao_formatada",
    "origem_registro",
    "observacao",
    "data_registro",
]


def safe_folder_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9À-ÿ._-]+", "_", value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "usuario"


def monthly_csv_path(base_folder: str, user_name: str, reference: datetime) -> Path:
    return (
        Path(base_folder)
        / "registros"
        / safe_folder_name(user_name)
        / f"{reference:%Y-%m}.csv"
    )


def audit_csv_path(base_folder: str, user_name: str, reference: datetime) -> Path:
    """Mantém a auditoria no mesmo mês do registro original."""
    return (
        Path(base_folder)
        / "registros"
        / safe_folder_name(user_name)
        / "auditoria"
        / f"{reference:%Y-%m}.csv"
    )


def test_write_access(base_folder: str) -> None:
    base = Path(base_folder)
    base.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix="timertask_test_", suffix=".tmp", dir=base)
    os.close(fd)
    Path(temporary_name).unlink(missing_ok=True)


@contextmanager
def _csv_lock(file_path: Path, timeout_seconds: float = 8.0) -> Iterator[None]:
    """Evita duas gravações simultâneas no mesmo CSV, inclusive em pasta de rede."""
    lock_path = file_path.with_suffix(file_path.suffix + ".lock")
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None

    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"pid={os.getpid()}\ncreated={time.time()}\n".encode("ascii"))
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > 120:
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"O arquivo está em uso por outra gravação: {file_path.name}")
            time.sleep(0.15)

    try:
        yield
    finally:
        try:
            if descriptor is not None:
                os.close(descriptor)
        finally:
            lock_path.unlink(missing_ok=True)


def _row_exists(file_path: Path, key_field: str, key_value: str) -> bool:
    if not file_path.exists() or file_path.stat().st_size == 0:
        return False
    with file_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        return any(row.get(key_field) == key_value for row in reader)


def _ensure_csv_schema(file_path: Path) -> list[str]:
    """Acrescenta novas colunas ao cabeçalho de um CSV antigo sem perder linhas."""
    if not file_path.exists() or file_path.stat().st_size == 0:
        return list(CSV_FIELDS)

    with file_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        existing_fields = [field for field in (reader.fieldnames or []) if field]
        rows = list(reader)

    target_fields = list(CSV_FIELDS)
    target_fields.extend(field for field in existing_fields if field not in target_fields)
    if existing_fields == target_fields:
        return target_fields

    backup_path = file_path.with_suffix(file_path.suffix + ".pre-origem-registro.bak")
    if not backup_path.exists():
        shutil.copy2(file_path, backup_path)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{file_path.stem}_schema_",
        suffix=".tmp",
        dir=file_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)

    try:
        with temporary_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=target_fields,
                delimiter=";",
                quoting=csv.QUOTE_MINIMAL,
                extrasaction="ignore",
            )
            writer.writeheader()
            for row in rows:
                row["origem_registro"] = row.get("origem_registro") or "TIMER"
                writer.writerow(row)
            csv_file.flush()
            os.fsync(csv_file.fileno())
        os.replace(temporary_path, file_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return target_fields


def append_record(base_folder: str, record: dict[str, Any]) -> Path:
    """Acrescenta uma linha de task sem duplicar o UUID do registro."""
    if not base_folder.strip():
        raise ValueError("A pasta compartilhada não está configurada")

    reference = datetime.fromisoformat(str(record["inicio"]))
    file_path = monthly_csv_path(base_folder, str(record["usuario"]), reference)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    record_to_write = dict(record)
    record_to_write["origem_registro"] = (
        str(record_to_write.get("origem_registro") or "TIMER").strip().upper()
    )

    with _csv_lock(file_path):
        file_exists = file_path.exists() and file_path.stat().st_size > 0
        fieldnames = _ensure_csv_schema(file_path) if file_exists else list(CSV_FIELDS)

        if file_exists and _row_exists(file_path, "registro_id", str(record_to_write["registro_id"])):
            return file_path

        with file_path.open("a", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=fieldnames,
                delimiter=";",
                quoting=csv.QUOTE_MINIMAL,
                extrasaction="ignore",
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(record_to_write)
            csv_file.flush()
            os.fsync(csv_file.fileno())

    return file_path


def append_audit_action(base_folder: str, action: dict[str, Any]) -> Path:
    """Grava uma ação append-only de auditoria, sem alterar o CSV original."""
    if not base_folder.strip():
        raise ValueError("A pasta compartilhada não está configurada")
    required = ("acao_id", "registro_id", "acao", "usuario_acao", "inicio")
    missing = [field for field in required if not str(action.get(field, "")).strip()]
    if missing:
        raise ValueError(f"Ação de auditoria incompleta: {', '.join(missing)}")

    reference = datetime.fromisoformat(str(action["inicio"]))
    file_path = audit_csv_path(
        base_folder,
        str(action.get("usuario_registro") or action["usuario_acao"]),
        reference,
    )
    file_path.parent.mkdir(parents=True, exist_ok=True)

    action_to_write = dict(action)
    action_to_write["acao"] = str(action_to_write.get("acao") or "EXCLUIR").upper()
    action_to_write["origem_registro"] = str(
        action_to_write.get("origem_registro") or "TIMER"
    ).upper()

    with _csv_lock(file_path):
        file_exists = file_path.exists() and file_path.stat().st_size > 0
        if file_exists and _row_exists(file_path, "acao_id", str(action_to_write["acao_id"])):
            return file_path

        with file_path.open("a", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=AUDIT_FIELDS,
                delimiter=";",
                quoting=csv.QUOTE_MINIMAL,
                extrasaction="ignore",
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(action_to_write)
            csv_file.flush()
            os.fsync(csv_file.fileno())

    return file_path


def _read_dict_rows(file_path: Path) -> list[dict[str, str]]:
    if not file_path.exists() or file_path.stat().st_size == 0:
        return []
    with file_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        return [dict(row) for row in csv.DictReader(csv_file, delimiter=";")]


def read_audit_actions_for_month(
    base_folder: str,
    user_name: str,
    reference: datetime,
) -> list[dict[str, str]]:
    if not base_folder.strip():
        return []
    return _read_dict_rows(audit_csv_path(base_folder, user_name, reference))


def _action_sort_key(action: dict[str, Any]) -> tuple[str, str]:
    return (
        str(action.get("data_hora_acao", "")),
        str(action.get("acao_id", "")),
    )


def apply_audit_actions(
    rows: list[dict[str, Any]],
    actions: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aplica a última ação de cada registro sem remover o registro original."""
    latest: dict[str, dict[str, Any]] = {}
    seen_action_ids: set[str] = set()
    for raw_action in actions:
        action = dict(raw_action)
        action_id = str(action.get("acao_id", "")).strip()
        if action_id and action_id in seen_action_ids:
            continue
        if action_id:
            seen_action_ids.add(action_id)
        record_id = str(action.get("registro_id", "")).strip()
        if not record_id:
            continue
        current = latest.get(record_id)
        if current is None or _action_sort_key(action) >= _action_sort_key(current):
            latest[record_id] = action

    result: list[dict[str, Any]] = []
    for original in rows:
        row = dict(original)
        action = latest.get(str(row.get("registro_id", "")).strip())
        if action is None:
            row.setdefault("excluido", "0")
            row.setdefault(
                "status_registro",
                "EXCLUÍDO" if str(row.get("excluido", "0")) == "1" else "ATIVO",
            )
            row.setdefault("motivo_exclusao", "")
            row.setdefault("data_exclusao", "")
            row.setdefault("usuario_exclusao", "")
            row.setdefault("acao_id_exclusao", "")
            result.append(row)
            continue

        deleted = str(action.get("acao", "")).upper() == "EXCLUIR"
        row["excluido"] = "1" if deleted else "0"
        row["status_registro"] = "EXCLUÍDO" if deleted else "ATIVO"
        row["motivo_exclusao"] = str(action.get("motivo", "")) if deleted else ""
        row["data_exclusao"] = str(action.get("data_hora_acao", "")) if deleted else ""
        row["usuario_exclusao"] = str(action.get("usuario_acao", "")) if deleted else ""
        row["acao_id_exclusao"] = str(action.get("acao_id", "")) if deleted else ""
        result.append(row)
    return result


def read_records_for_date(
    base_folder: str,
    user_name: str,
    selected_date: datetime,
) -> list[dict[str, Any]]:
    if not base_folder.strip():
        return []
    file_path = monthly_csv_path(base_folder, user_name, selected_date)
    if not file_path.exists():
        return []

    selected_prefix = selected_date.strftime("%Y-%m-%d")
    with file_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        rows: list[dict[str, Any]] = [
            dict(row) for row in reader if row.get("inicio", "").startswith(selected_prefix)
        ]

    for row in rows:
        row["origem_registro"] = row.get("origem_registro") or "TIMER"
    rows.sort(key=lambda row: str(row.get("inicio", "")))
    actions = read_audit_actions_for_month(base_folder, user_name, selected_date)
    return apply_audit_actions(rows, actions)
