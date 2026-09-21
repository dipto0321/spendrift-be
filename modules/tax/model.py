"""Tax report models (Bangladesh IT-10BB)."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import ClassVar
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, UniqueConstraint
from sqlmodel import Column, Field, SQLModel


class TaxReport(SQLModel, table=True):
    """A persisted IT-10BB report for one tracker and one income year."""

    __tablename__: ClassVar[str] = "tax_reports"
    __table_args__ = (
        UniqueConstraint(
            "tracker_id", "fiscal_year", name="uq_tax_reports_tracker_fiscal_year"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tracker_id: UUID = Field(foreign_key="trackers.id", ondelete="CASCADE")
    fiscal_year: str = Field(max_length=9)  # e.g. "2025-26"
    start_date: date
    end_date: date
    currency: str = Field(max_length=10)
    total_amount: Decimal = Field(default=Decimal("0"), max_digits=14, decimal_places=2)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )


class TaxReportHead(SQLModel, table=True):
    """One of the 9 fixed IT-10BB heads within a report."""

    __tablename__: ClassVar[str] = "tax_report_heads"
    __table_args__ = (
        UniqueConstraint(
            "report_id", "head_code", name="uq_tax_report_heads_report_head"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    report_id: UUID = Field(foreign_key="tax_reports.id", ondelete="CASCADE")
    head_code: str = Field(max_length=50)
    amount: Decimal = Field(default=Decimal("0"), max_digits=14, decimal_places=2)
    # [{"category_name": str, "amount": str}] — amounts stored as decimal
    # strings to preserve precision (JSON has no Decimal type).
    category_allocations: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
