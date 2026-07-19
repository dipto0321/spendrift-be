"""API v1 router module."""

from fastapi import APIRouter

from modules.ai.router import router as ai_router
from modules.auth.router import router as auth_router
from modules.budget_alerts.router import router as budget_alerts_router
from modules.budgets.router import router as budgets_router
from modules.categories.router import router as categories_router
from modules.category_budgets.router import router as category_budgets_router
from modules.dashboard.router import router as dashboard_router
from modules.expenses.router import router as expenses_router
from modules.preferences.router import router as preferences_router
from modules.reports.router import router as reports_router
from modules.trackers.router import router as trackers_router
from modules.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")

# Include sub-routers
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(trackers_router, prefix="/trackers", tags=["trackers"])
api_router.include_router(categories_router)
api_router.include_router(expenses_router)
api_router.include_router(budgets_router)
api_router.include_router(category_budgets_router)
api_router.include_router(budget_alerts_router)
api_router.include_router(dashboard_router)
api_router.include_router(reports_router)
api_router.include_router(
    preferences_router, prefix="/preferences", tags=["Preferences"]
)
api_router.include_router(ai_router)
