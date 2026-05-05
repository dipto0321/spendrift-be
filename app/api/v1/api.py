"""API v1 router module."""
from fastapi import APIRouter
from modules.auth.router import router as auth_router
from modules.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")

# Include sub-routers
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
