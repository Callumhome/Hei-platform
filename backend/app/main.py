from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.routes import router as api_router
from app.api.auth import router as auth_router
from app.api.households import router as households_router
from app.api.energy import router as energy_router
from app.api.home_assistant import router as home_assistant_router
from app.api.properties import router as properties_router
from app.api.octopus import router as octopus_router

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
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "hei-api", "environment": settings.app_env}


app.include_router(api_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(households_router, prefix=settings.api_v1_prefix)
app.include_router(energy_router, prefix=settings.api_v1_prefix)
app.include_router(home_assistant_router, prefix=settings.api_v1_prefix)
app.include_router(properties_router, prefix=settings.api_v1_prefix)
app.include_router(octopus_router, prefix=settings.api_v1_prefix)
