"""Tax report repository - data access."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session, select

from modules.tax.model import TaxReport, TaxReportHead


def get_report_by_fiscal_year(
    session: Session, tracker_id: UUID, fiscal_year: str
) -> TaxReport | None:
    """Get a tax report by tracker and income year."""
    return session.exec(
        select(TaxReport)
        .where(TaxReport.tracker_id == tracker_id)
        .where(TaxReport.fiscal_year == fiscal_year)
    ).first()


def create_report(
    session: Session,
    *,
    tracker_id: UUID,
    fiscal_year: str,
    start_date: date,
    end_date: date,
    currency: str,
    total_amount: Decimal,
) -> TaxReport:
    """Persist a new tax report."""
    report = TaxReport(
        tracker_id=tracker_id,
        fiscal_year=fiscal_year,
        start_date=start_date,
        end_date=end_date,
        currency=currency,
        total_amount=total_amount,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def list_reports_by_tracker(session: Session, tracker_id: UUID) -> list[TaxReport]:
    """List saved tax reports for a tracker, newest income year first."""
    return list(
        session.exec(
            select(TaxReport)
            .where(TaxReport.tracker_id == tracker_id)
            .order_by(TaxReport.fiscal_year.desc())
        ).all()
    )


def list_heads_by_report(session: Session, report_id: UUID) -> list[TaxReportHead]:
    """Get all heads for a report."""
    return list(
        session.exec(
            select(TaxReportHead).where(TaxReportHead.report_id == report_id)
        ).all()
    )


def get_head_by_code(
    session: Session, report_id: UUID, head_code: str
) -> TaxReportHead | None:
    """Get one head for a report by its fixed head code."""
    return session.exec(
        select(TaxReportHead)
        .where(TaxReportHead.report_id == report_id)
        .where(TaxReportHead.head_code == head_code)
    ).first()


def add_heads(session: Session, heads: list[TaxReportHead]) -> None:
    """Persist a batch of tax report heads."""
    session.add_all(heads)
    session.commit()
    for head in heads:
        session.refresh(head)


def delete_heads_by_report(session: Session, report_id: UUID) -> None:
    """Delete every head row belonging to a report (used on regenerate)."""
    for head in list_heads_by_report(session, report_id):
        session.delete(head)
    session.commit()


def update_report_total(
    session: Session, report: TaxReport, total_amount: Decimal
) -> TaxReport:
    """Update the cached total amount of a report."""
    report.total_amount = total_amount
    session.add(report)
    session.commit()
    session.refresh(report)
    return report
