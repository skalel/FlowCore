from datetime import datetime, timezone

import sentry_sdk
import sqlalchemy as sa
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1.admin import router as admin_router
from app.api.v1.analysis import router as analysis_router
from app.api.v1.auth import router as auth_router
from app.api.v1.card_holders import router as card_holders_router
from app.api.v1.cards import router as cards_router
from app.api.v1.categories import router as categories_router
from app.api.v1.connections import router as connections_router
from app.api.v1.env_settings import router as env_settings_router
from app.api.v1.environments import router as env_router
from app.api.v1.feedbacks import router as feedbacks_router
from app.api.v1.fiscal import router as fiscal_router
from app.api.v1.imports import router as imports_router
from app.api.v1.installments import router as installments_router
from app.api.v1.invites import router as invites_router
from app.api.v1.ledger import router as ledger_router
from app.api.v1.reports import router as reports_router
from app.api.v1.users import router as users_router
from app.config.settings import settings

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    integrations=[FastApiIntegration()],
    traces_sample_rate=1.0,
    send_default_pii=True,
    environment="production",
)

app = FastAPI(title="FlowCore")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(env_router)
api_v1_router.include_router(env_settings_router)
api_v1_router.include_router(invites_router)
api_v1_router.include_router(imports_router)
api_v1_router.include_router(ledger_router)
api_v1_router.include_router(categories_router)
api_v1_router.include_router(cards_router)
api_v1_router.include_router(card_holders_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(fiscal_router)
api_v1_router.include_router(installments_router)
api_v1_router.include_router(analysis_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(feedbacks_router)
api_v1_router.include_router(connections_router)
api_v1_router.include_router(admin_router)


@api_v1_router.get("/health")
def health_check(db: Session = Depends(get_db)):
    start_time = datetime.now(timezone.utc)

    try:
        db.execute(sa.text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"

    latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

    return {
        "status": "online" if db_status == "healthy" else "degraded",
        "database": db_status,
        "latency_ms": round(latency_ms, 2),
        "version": settings.VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


app.include_router(api_v1_router)
