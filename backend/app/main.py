"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import structlog

from app.core.config import settings
from app.db.session import engine, init_db
from app.api.v1 import api_router
from app.api.v1.dependencies import limiter
from app.services.live_poller import live_poller


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
        if settings.environment == "production"
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    print("=== LIFESPAN: Starting application ===")

    # Initialize database
    await init_db()
    print("=== LIFESPAN: Database initialized ===")

    # Start live match poller
    await live_poller.start()
    print(f"=== LIFESPAN: Live poller started, is_live={live_poller.is_live()} ===")

    yield

    # Cleanup
    await live_poller.stop()
    print("=== LIFESPAN: Live poller stopped ===")
    await engine.dispose()
    print("=== LIFESPAN: Shutdown complete ===")


app = FastAPI(
    title=settings.app_name,
    description="API for tracking Polish footballers playing abroad",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# Connect limiter to app
app.state.limiter = limiter

# Rate limit exceeded handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs" if settings.debug else "disabled",
    }


@app.get("/health")
@app.get("/health-check")
async def health():
    """Health check for Render."""
    return {"status": "ok"}
