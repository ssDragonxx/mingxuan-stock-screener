"""Pydantic request models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ParseRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    universe: str = "all_a_share"


class ScreenRequest(BaseModel):
    dsl: dict


class DiagnoseRequest(BaseModel):
    query: str = Field(min_length=1, max_length=100)
    dsl: dict


class ExplainRequest(BaseModel):
    query: str = Field(min_length=1, max_length=100)
    dsl: dict


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    query: str | None = None
    dsl: dict
    monitor_enabled: bool = False


class StrategyRunRequest(BaseModel):
    pass
