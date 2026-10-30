from fastapi import APIRouter

from app.schemas.platform import PlatformInfo
from app.providers.registry import available_providers

router = APIRouter()


@router.get("/platform", response_model=PlatformInfo, tags=["platform"])
def platform_info() -> PlatformInfo:
    return PlatformInfo(
        name="Home Energy Intelligence",
        version="0.1.0",
        focus="UK household electricity",
        providers=available_providers(),
        capabilities=["platform_metadata"],
    )
