"""Внешний контракт API."""

from pydantic import BaseModel, Field


class PurchaseRequest(BaseModel):
    itemid: int = Field(ge=0)
    hour: int = Field(ge=0, le=23)
    weekday: int = Field(ge=0, le=6)


class PurchaseResponse(BaseModel):
    itemid: int
    purchase_probability: float = Field(ge=0, le=1)
    model_version: str
