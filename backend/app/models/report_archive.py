from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ReportArchive(Base):
    """Archived structured reports (DPI integration stub)."""

    __tablename__ = "report_archive"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    patient_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    signed_by: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    destination: Mapped[str] = mapped_column(String(64), nullable=False, default="DPI")
    archive_path: Mapped[str] = mapped_column(String(512), nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)

