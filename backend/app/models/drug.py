from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DrugInteraction(Base):
    """Pairwise drug-drug interaction. Source-agnostic (DrugBank, DDInter, manual curation)."""

    __tablename__ = "drug_interactions"
    __table_args__ = (UniqueConstraint("drug_a", "drug_b", "source", name="uq_drug_pair_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drug_a: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    drug_b: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # minor | moderate | major
    mechanism: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual", index=True)


class Drug(Base):
    """One row per BDPM specialty (drug authorised in France). Joined on CIS code."""

    __tablename__ = "drugs"

    cis: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    form: Mapped[str] = mapped_column(String(256), nullable=True)
    routes: Mapped[str | None] = mapped_column(String(256), nullable=True)  # ';'-joined
    holders: Mapped[str | None] = mapped_column(String(512), nullable=True)  # ';'-joined
    amm_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amm_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    commercial_status: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reinforced_surveillance: Mapped[bool] = mapped_column(Boolean, default=False)

    compositions: Mapped[list["DrugComposition"]] = relationship(back_populates="drug", cascade="all, delete-orphan")


class DrugComposition(Base):
    """Active substances per drug (from CIS_COMPO_bdpm.txt, SA rows only)."""

    __tablename__ = "drug_compositions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cis: Mapped[str] = mapped_column(String(16), ForeignKey("drugs.cis", ondelete="CASCADE"), index=True)
    substance_code: Mapped[str] = mapped_column(String(32), nullable=True, index=True)
    substance_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    dosage: Mapped[str | None] = mapped_column(String(256), nullable=True)
    dosage_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)

    drug: Mapped[Drug] = relationship(back_populates="compositions")


class GenericGroupEntry(Base):
    """CIS_GENER_bdpm.txt membership. Drugs in the same group share the active ingredient."""

    __tablename__ = "generic_group_entries"
    __table_args__ = (Index("ix_gge_group_cis", "group_id", "cis", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(String(16), index=True)
    group_label: Mapped[str] = mapped_column(String(512))
    cis: Mapped[str] = mapped_column(String(16), index=True)
    type_code: Mapped[str] = mapped_column(String(2))  # 0 princeps / 1 générique / ...
