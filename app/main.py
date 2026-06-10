from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.api import api_router as v1_router
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.middleware.rate_limit import limiter

# Setup logging
setup_logging()

# Create FastAPI app
app = FastAPI(
    title="Financial tracker API",
    description="An app which helps you to track your expenses and income, manage budgets, and gain insights into your financial habits.",
    version="1.0.0",
)

# CORS - explicit origin allowlist (required for the browser frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup rate limiting
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Include routers
app.include_router(v1_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Health check endpoint - liveness probe."""
    return {"status": "healthy"}


@app.get("/ready", tags=["health"])
async def readiness_check() -> dict:
    """Readiness check endpoint - readiness probe."""
    return {"status": "ready"}


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    """Custom 404 handler."""
    return JSONResponse(
        status_code=404,
        content={"detail": f"Path {request.url.path} not found"},
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Custom 500 handler."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )
