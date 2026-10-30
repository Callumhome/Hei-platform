from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


HouseholdRole = Literal["owner", "admin", "member", "viewer"]


class HouseholdCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    country_code: str = Field(default="GB", min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    timezone: str = Field(default="Europe/London", min_length=1, max_length=64)


class HouseholdResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    country_code: str
    timezone: str
    role: str


class HouseholdMemberResponse(BaseModel):
    user_id: str
    email: str
    display_name: str | None
    role: HouseholdRole


class HouseholdMemberRoleUpdate(BaseModel):
    role: Literal["admin", "member", "viewer"]


class HouseholdMemberAddRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal["admin", "member", "viewer"] = "member"
