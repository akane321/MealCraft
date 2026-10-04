from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.paths import repository_root
from app.data.catalog import import_catalog, load_catalog
from app.data.release_v2 import import_release_v2
from app.schemas.operation_jobs import CatalogImportArguments

Handler = Callable[[dict, str], None]


@dataclass(frozen=True)
class HandlerSpec:
    payload_model: type[BaseModel]
    handler: Handler


@dataclass(frozen=True)
class PreparedHandler:
    handler: Handler
    payload: dict


class UnknownJobTypeError(ValueError):
    """The queue row names no registered operation."""


class InvalidJobPayloadError(ValueError):
    """The queue row does not match its named handler's declared arguments."""


class JobHandlerRegistry:
    def __init__(self, handlers: Mapping[str, HandlerSpec]) -> None:
        self._handlers = dict(handlers)

    def prepare(self, run_type: str, payload: dict) -> PreparedHandler:
        spec = self._handlers.get(run_type)
        if spec is None:
            raise UnknownJobTypeError(run_type)
        try:
            normalized = spec.payload_model.model_validate(payload).model_dump(mode="json")
        except (TypeError, ValueError) as exc:
            raise InvalidJobPayloadError(run_type) from exc
        return PreparedHandler(handler=spec.handler, payload=normalized)


def import_catalog_handler(payload: dict, database_url: str) -> None:
    request = CatalogImportArguments.model_validate(payload)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine, expire_on_commit=False) as session:
            if request.source == "reference":
                root = repository_root()
                catalog = load_catalog(
                    root / "data" / "ingredients" / "ingredients.json",
                    root / "data" / "recipes" / "recipes.json",
                )
                import_catalog(session, catalog)
            else:
                import_release_v2(session)
    finally:
        engine.dispose()


def production_registry() -> JobHandlerRegistry:
    return JobHandlerRegistry(
        {
            "catalog_import": HandlerSpec(
                payload_model=CatalogImportArguments,
                handler=import_catalog_handler,
            )
        }
    )
