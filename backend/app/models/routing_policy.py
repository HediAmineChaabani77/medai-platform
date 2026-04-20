from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RoutingPolicy(Base):
    """Admin-configured overrides to force local/cloud per (use_case, department)."""

    __tablename__ = "routing_policies"
    __table_args__ = (UniqueConstraint("use_case", "department", name="uq_policy_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    use_case: Mapped[str] = mapped_column(String(32), nullable=False)
    department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    override: Mapped[str] = mapped_column(String(16), nullable=False)  # local | cloud
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
