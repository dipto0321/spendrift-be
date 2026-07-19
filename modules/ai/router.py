"""AI routes (smart-paste expense parsing)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.core.database import get_session
from app.core.llm import get_llm
from app.core.llm.base import LLMClient
from app.core.security import get_current_user
from app.middleware.rate_limit import limiter
from modules.ai import service as ai_service
from modules.ai.schema import ParseExpensesRequest, ParseExpensesResponse
from modules.users.model import User

router = APIRouter(prefix="/trackers/{tracker_id}/ai", tags=["AI"])


@router.post("/parse-expenses", response_model=ParseExpensesResponse)
# Tighter than the global 60/min default: every call spends Gemini
# free-tier quota, and a paste session needs only a handful.
@limiter.limit("10/minute")
def parse_expenses(
    request: Request,  # required by slowapi's limiter
    tracker_id: UUID,
    payload: ParseExpensesRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    llm: Annotated[LLMClient, Depends(get_llm)],
):
    return ai_service.parse_expenses(session, llm, tracker_id, current_user.id, payload)
