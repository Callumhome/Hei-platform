from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.routes import router as api_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="A supplier-neutral foundation for UK household electricity intelligence.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "hei-api", "environment": settings.app_env}

app.include_router(api_router, prefix=settings.api_v1_prefix)
