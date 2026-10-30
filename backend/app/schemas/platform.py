from pydantic import BaseModel


class PlatformInfo(BaseModel):
    name: str
    version: str
    focus: str
    providers: list[str]
    capabilities: list[str]
