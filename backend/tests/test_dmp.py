import json

from app.config import Settings
from app.services.dmp_service import get_patient_from_dmp, merge_uc1_context


def test_get_patient_from_dmp_with_explicit_file(tmp_path):
    dmp_file = tmp_path / "patients.json"
    dmp_file.write_text(
        json.dumps({"P-001": {"age": 62, "sexe": "M", "antecedents": ["HTA"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    settings = Settings(dmp_data_path=str(dmp_file))
    rec = get_patient_from_dmp("P-001", settings=settings)
    assert isinstance(rec, dict)
    assert rec.get("age") == 62


def test_merge_uc1_context_prefers_explicit_request_fields():
    merged = merge_uc1_context({"age": 40, "sexe": "F"}, {"age": 62, "sexe": "M", "antecedents": ["HTA"]})
    assert merged["age"] == 40
    assert merged["sexe"] == "F"
    assert merged["antecedents"] == ["HTA"]
