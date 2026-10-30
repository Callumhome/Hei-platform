from pydantic import BaseModel, ConfigDict, Field


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
