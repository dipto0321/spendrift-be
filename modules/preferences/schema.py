"""User preferences schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PreferencesUpdate(BaseModel):
    """Partial update — any subset of the three toggles."""

    budget_alerts_enabled: bool | None = None
    weekly_summary_enabled: bool | None = None
    round_amounts_enabled: bool | None = None


class PreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    budget_alerts_enabled: bool
    weekly_summary_enabled: bool
    round_amounts_enabled: bool
    created_at: datetime
    updated_at: datetime
