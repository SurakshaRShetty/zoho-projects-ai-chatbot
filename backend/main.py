import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database import init_db

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup and once at shutdown."""
    logger.info("Starting up — initialising database")
    await init_db()
    logger.info("Database ready")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Zoho Project Chatbot",
    description="AI-powered chatbot for Zoho Projects using LangGraph multi-agent system",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,  # hide docs in production
)

# ── CORS ──────────────────────────────────────────────────────
# Allows the React frontend (localhost:3000) to call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────
# Imported here to avoid circular imports; registered after app is created
from backend.auth.router import router as auth_router      # noqa: E402
from backend.chat.router import router as chat_router      # noqa: E402

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(chat_router, prefix="", tags=["Chat"])


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple liveness check — returns 200 if the server is running."""
    return {"status": "ok", "env": settings.app_env}
