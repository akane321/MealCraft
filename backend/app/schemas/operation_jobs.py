from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CatalogImportArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["reference", "release_v2"]


class OperationJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["catalog_import"]
    arguments: CatalogImportArguments
    confirm: Literal[True]


class OperationJobView(BaseModel):
    id: int
    trace_id: str
    name: Literal["catalog_import"]
    arguments: CatalogImportArguments
    status: Literal["queued", "running", "succeeded", "failed", "cancelled", "degraded"]
    attempt_count: int = Field(ge=0)
    created: bool
    created_at: datetime


class OperationJobCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: Literal[True]


class OperationJobCancellationView(BaseModel):
    id: int
    trace_id: str
    target_run_id: int
    previous_status: Literal["queued", "running"]
    target_status: Literal["cancelled"]
    created_at: datetime
