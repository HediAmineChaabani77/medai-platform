from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.config import Settings, get_settings


@lru_cache(maxsize=1)
def _load_dmp(path: str) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists() or p.is_dir():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def get_patient_from_dmp(patient_id: str | None, settings: Settings | None = None) -> dict:
    if not patient_id:
        return {}
    settings = settings or get_settings()
    rows = _load_dmp(settings.dmp_data_path)
    record = rows.get(patient_id)
    return record if isinstance(record, dict) else {}


def merge_uc1_context(patient_context: dict, dmp_record: dict) -> dict:
    out = dict(patient_context or {})
    if not dmp_record:
        return out
    for key in ("age", "sexe", "sex", "antecedents"):
        if key not in out or out.get(key) in (None, "", []):
            value = dmp_record.get(key)
            if value not in (None, "", []):
                out[key] = value
    if "antecedents" not in out and dmp_record.get("history"):
        out["antecedents"] = dmp_record["history"]
    return out


def merge_uc2_context(patient_context: dict, dmp_record: dict) -> dict:
    out = dict(patient_context or {})
    if not dmp_record:
        return out
    for key in ("age", "sexe", "sex", "allergies", "history", "current_medications", "dfg_ml_min"):
        if key not in out or out.get(key) in (None, "", []):
            value = dmp_record.get(key)
            if value not in (None, "", []):
                out[key] = value
    return out
