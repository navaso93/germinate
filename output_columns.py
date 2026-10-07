"""Configurable presentation of opportunity records; keep raw facts separate."""
import csv
from dataclasses import asdict
from datetime import date
from pathlib import Path

from config_io import load_json

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config" / "output-columns.json"
DERIVED_FIELDS = {"blank", "budget_eur", "status"}


def validate_columns(config, fields):
    columns = config.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("output columns must be a nonempty list")
    labels = set()
    for column in columns:
        label = column.get("label")
        if not isinstance(label, str) or not label.strip() or label in labels:
            raise ValueError("output column labels must be nonempty and unique")
        labels.add(label)
        if column.get("field") not in set(fields) | DERIVED_FIELDS:
            raise ValueError(f"Unknown output field: {column.get('field')}")
    return columns


def output_value(record, field):
    if field == "blank":
        return ""
    if field == "budget_eur":
        # Do not relabel another currency or a programme budget as an EUR award.
        return record.get("amount_max", "") if str(record.get("currency", "")).upper() == "EUR" else ""
    if field == "status":
        if record.get("application_status") != "open":
            return "Pendiente"
        try:
            checked = date.fromisoformat(record["checked_at"][:10])
            deadline = record.get("deadline")
            if deadline and date.fromisoformat(deadline) < checked:
                return "Pendiente"
        except (KeyError, ValueError, TypeError):
            return "Pendiente"
        return "En curso"
    value = record.get(field, "")
    return "" if value is None else value


def write_output(results, output_path, fields, config=None):
    config = load_json(DEFAULT_CONFIG) if config is None else config
    columns = validate_columns(config, fields)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([column["label"] for column in columns])
        for result in results:
            record = asdict(result)
            writer.writerow([output_value(record, column["field"]) for column in columns])


def write_audit(results, output_path, fields):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)
