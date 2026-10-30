from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PropertyCreate(BaseModel):
    address_line_1: str = Field(min_length=2, max_length=160)
    address_line_2: str | None = Field(default=None, max_length=160)
    town: str = Field(min_length=2, max_length=120)
    county: str | None = Field(default=None, max_length=120)
    postcode: str = Field(min_length=5, max_length=12, pattern=r"^[A-Za-z0-9 ]+$")
    country_code: str = Field(default="GB", min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    address_source: str | None = Field(default=None, max_length=40)
    address_source_ref: str | None = Field(default=None, max_length=200)

    @field_validator("postcode")
    @classmethod
    def normalise_postcode(cls, value: str) -> str:
        return " ".join(value.upper().split())


class PropertyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    property_ref: str
    household_id: str
    address_line_1: str
    address_line_2: str | None
    town: str
    county: str | None
    postcode: str
    country_code: str
    address_source: str | None
    created_at: datetime


class SupplyPointCreate(BaseModel):
    fuel: Literal["electricity", "gas"]
    identifier: str = Field(min_length=6, max_length=21, pattern=r"^[0-9 ]+$")
    supplier_name: str | None = Field(default=None, max_length=120)


class SupplyPointResponse(BaseModel):
    id: str
    property_id: str
    fuel: str
    identifier_masked: str
    supplier_name: str | None
    status: str
    created_at: datetime


class ConsentCreate(BaseModel):
    property_id: str | None = None
    provider: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9_-]+$")
    purpose: str = Field(min_length=5, max_length=200)
    scopes: list[str] = Field(min_length=1, max_length=20)

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, values: list[str]) -> list[str]:
        cleaned = sorted(set(value.strip().lower() for value in values if value.strip()))
        if not cleaned or any(len(value) > 60 for value in cleaned):
            raise ValueError("Provide one or more valid consent scopes")
        return cleaned


class ConsentResponse(BaseModel):
    id: str
    household_id: str
    property_id: str | None
    provider: str
    purpose: str
    scopes: list[str]
    status: str
    granted_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
