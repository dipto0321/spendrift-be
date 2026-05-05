from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.api import api_router as v1_router
from app.core.database import create_db_tables
from app.core.logging_config import setup_logging
from app.middleware.rate_limit import limiter

# Setup logging
setup_logging()

# Create FastAPI app
app = FastAPI(
    title="FastAPI Scaffold with Auth",
    description="Production-ready FastAPI template with authentication, migrations, rate limiting, and logging",
    version="1.0.0",
)

# Setup rate limiting
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Include routers
app.include_router(v1_router)


@app.on_event("startup")
def startup():
    """Initialize database on startup."""
    create_db_tables()


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
