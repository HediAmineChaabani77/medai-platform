"""Unit tests for BDPM parser using small synthetic fixtures that mirror the real layout."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.bdpm_parser import (
    build_monographs, monograph_to_markdown,
    parse_compositions, parse_generic_groups, parse_prescription_conditions,
    parse_smr_opinions, parse_specialties,
)


@pytest.fixture
def bdpm_tmpdir(tmp_path: Path) -> Path:
    (tmp_path / "CIS_bdpm.txt").write_text(
        "12345678\tAPIRINE 500 mg, comprimé\tcomprimé\torale\tAutorisation active\tProcédure nationale\tCommercialisée\t01/01/2000\t\t\tACME\tNon\n"
        "87654321\tPLACEBO 10 mg, gélule\tgélule\torale;sublinguale\tAutorisation active\tProcédure nationale\tArrêt\t15/06/2010\t\t\tBIOCO\tOui\n",
        encoding="utf-8",
    )
    (tmp_path / "CIS_COMPO_bdpm.txt").write_text(
        "12345678\tcomprimé\t00001\tACIDE ACETYLSALICYLIQUE\t500 mg\tun comprimé\tSA\t1\n"
        "12345678\tcomprimé\t99999\tFRACTION X\ttrace\tun comprimé\tST\t1\n"
        "87654321\tgélule\t00002\tPLACEBO ACTIF\t10 mg\tune gélule\tSA\t1\n",
        encoding="utf-8",
    )
    (tmp_path / "CIS_GENER_bdpm.txt").write_text(
        "42\tACIDE ACETYLSALICYLIQUE 500 mg, comprimé\t12345678\t0\t1\n",
        encoding="utf-8",
    )
    (tmp_path / "CIS_CPD_bdpm.txt").write_text(
        "12345678\tListe I\n"
        "12345678\tSurveillance particulière pendant le traitement\n",
        encoding="utf-8",
    )
    (tmp_path / "CIS_HAS_SMR_bdpm.txt").write_text(
        "12345678\tDOSSIER-1\tRéévaluation\t20200115\tImportant\tSMR important dans l'indication X.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_parse_specialties(bdpm_tmpdir):
    rows = list(parse_specialties(bdpm_tmpdir / "CIS_bdpm.txt"))
    assert len(rows) == 2
    assert rows[0].cis == "12345678"
    assert rows[0].is_commercialised is True
    assert rows[0].routes == ["orale"]
    assert rows[1].reinforced_surveillance is True
    assert rows[1].routes == ["orale", "sublinguale"]


def test_parse_compositions(bdpm_tmpdir):
    rows = list(parse_compositions(bdpm_tmpdir / "CIS_COMPO_bdpm.txt"))
    assert len(rows) == 3
    natures = {r.nature for r in rows}
    assert natures == {"SA", "ST"}


def test_parse_generic_groups(bdpm_tmpdir):
    rows = list(parse_generic_groups(bdpm_tmpdir / "CIS_GENER_bdpm.txt"))
    assert len(rows) == 1 and rows[0].group_id == "42"


def test_parse_prescription_conditions(bdpm_tmpdir):
    rows = list(parse_prescription_conditions(bdpm_tmpdir / "CIS_CPD_bdpm.txt"))
    assert len(rows) == 2 and rows[0].condition == "Liste I"


def test_parse_smr_opinions(bdpm_tmpdir):
    rows = list(parse_smr_opinions(bdpm_tmpdir / "CIS_HAS_SMR_bdpm.txt"))
    assert len(rows) == 1 and rows[0].smr_value == "Important"


def test_build_monographs_filters_and_joins(bdpm_tmpdir):
    ms = list(build_monographs(
        bdpm_tmpdir / "CIS_bdpm.txt",
        bdpm_tmpdir / "CIS_COMPO_bdpm.txt",
        bdpm_tmpdir / "CIS_GENER_bdpm.txt",
        bdpm_tmpdir / "CIS_CPD_bdpm.txt",
        smr_path=bdpm_tmpdir / "CIS_HAS_SMR_bdpm.txt",
        commercialised_only=True,
    ))
    assert len(ms) == 1
    m = ms[0]
    assert m.cis == "12345678"
    # Only SA rows kept.
    assert [s.nature for s in m.substances] == ["SA"]
    assert m.generic_group == ("42", "ACIDE ACETYLSALICYLIQUE 500 mg, comprimé")
    assert len(m.prescription_conditions) == 2
    assert len(m.smr_opinions) == 1


def test_monograph_to_markdown(bdpm_tmpdir):
    ms = list(build_monographs(
        bdpm_tmpdir / "CIS_bdpm.txt",
        bdpm_tmpdir / "CIS_COMPO_bdpm.txt",
        bdpm_tmpdir / "CIS_GENER_bdpm.txt",
        bdpm_tmpdir / "CIS_CPD_bdpm.txt",
        smr_path=bdpm_tmpdir / "CIS_HAS_SMR_bdpm.txt",
    ))
    md = monograph_to_markdown(ms[0])
    assert "# APIRINE 500 mg, comprimé" in md
    assert "Source: BDPM (ANSM)" in md
    assert "CIS 12345678" in md
    assert "ACIDE ACETYLSALICYLIQUE" in md
    assert "Liste I" in md
    assert "SMR important" in md


def test_encoding_cp1252_fallback(tmp_path: Path):
    # Simulate the real BDPM case: some files are cp1252.
    p = tmp_path / "CIS_bdpm.txt"
    p.write_bytes("12345678\tMÉDICAMENT, comprimé\tcomprimé\torale\tAutorisation active\tProcédure nationale\tCommercialisée\t01/01/2000\t\t\tACME\tNon\n".encode("cp1252"))
    rows = list(parse_specialties(p))
    assert rows[0].name.startswith("MÉDICAMENT")
