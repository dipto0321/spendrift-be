from pydantic import BaseModel


class SignOutRequest(BaseModel):
    """Sign out request schema."""

    refresh_token: str
    model_config = {"extra": "forbid"}
