"""Tax report router (Bangladesh IT-10BB)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.core.database import get_session
from app.core.llm import get_llm
from app.core.llm.base import LLMClient
from app.core.security import get_current_user
from app.middleware.rate_limit import limiter
from modules.tax import service as tax_service
from modules.tax.schema import (
    TaxReportCreateRequest,
    TaxReportResponse,
    TaxReportSummaryResponse,
    TaxReportUpdateRequest,
)
from modules.users.model import User

router = APIRouter(prefix="/trackers/{tracker_id}/tax-reports", tags=["Tax"])


@router.post("", response_model=TaxReportResponse)
@limiter.limit("10/minute")
def create_or_get_tax_report(
    request: Request,  # required by slowapi
    tracker_id: UUID,
    payload: TaxReportCreateRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    llm: Annotated[LLMClient, Depends(get_llm)],
):
    """Get or create a persisted IT-10BB report for a fiscal year."""
    return tax_service.get_or_create(session, llm, tracker_id, current_user.id, payload)


@router.get("", response_model=list[TaxReportSummaryResponse])
def list_tax_reports(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """List saved IT-10BB reports for the tracker."""
    return tax_service.list_reports(session, tracker_id, current_user.id)


@router.get("/{fiscal_year}", response_model=TaxReportResponse)
def get_tax_report(
    tracker_id: UUID,
    fiscal_year: str,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Fetch an existing IT-10BB report by fiscal year."""
    return tax_service.get_report(session, tracker_id, current_user.id, fiscal_year)


@router.patch("/{fiscal_year}", response_model=TaxReportResponse)
def update_tax_report_heads(
    tracker_id: UUID,
    fiscal_year: str,
    payload: TaxReportUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Manually override one or more IT-10BB head amounts."""
    return tax_service.update_heads(
        session, tracker_id, current_user.id, fiscal_year, payload
    )


@router.post("/{fiscal_year}/regenerate", response_model=TaxReportResponse)
@limiter.limit("10/minute")
def regenerate_tax_report(
    request: Request,  # required by slowapi
    tracker_id: UUID,
    fiscal_year: str,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    llm: Annotated[LLMClient, Depends(get_llm)],
):
    """Re-aggregate and re-classify an existing IT-10BB report."""
    return tax_service.regenerate(
        session, llm, tracker_id, current_user.id, fiscal_year
    )
