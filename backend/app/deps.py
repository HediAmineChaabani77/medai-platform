from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings, Settings
from app.core.connectivity import ConnectivityProbe
from app.core.dispatcher import LLMDispatcher
from app.core.llm_provider import build_cloud_provider, build_local_provider
from app.core.phi_detector import PHIDetector
from app.core.rag import RAGIndex
from app.core.router import Router
from app.db import get_db
from app.models.model_registry import ModelVersion
from app.models.routing_policy import RoutingPolicy


class _PolicyLookup:
    """Reads admin overrides live from the DB."""

    def __init__(self, db_factory):
        self.db_factory = db_factory

    def override_for(self, use_case: str, department: str | None) -> str | None:
        with self.db_factory() as db:
            q = db.query(RoutingPolicy).filter(RoutingPolicy.use_case == use_case)
            row = q.filter(RoutingPolicy.department == department).first() if department else None
            if row:
                return row.override
            row = q.filter(RoutingPolicy.department.is_(None)).first()
            return row.override if row else None


class _LoadProbe:
    """Placeholder load probe. A real deployment would read from Ollama metrics or a queue."""

    def __init__(self):
        self._depth = 0

    def local_queue_depth(self) -> int:
        return self._depth


@lru_cache
def _phi() -> PHIDetector:
    return PHIDetector()


def _connectivity(request: Request) -> ConnectivityProbe:
    return request.app.state.connectivity


def get_router(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Router:
    from app.db import SessionLocal
    return Router(
        connectivity=_connectivity(request),
        phi=_phi(),
        policy=_PolicyLookup(SessionLocal),
        load=_LoadProbe(),
        text_len_threshold=settings.router_text_len_threshold,
        queue_threshold=settings.router_local_queue_threshold,
        force_local_only=settings.force_local_only,
    )


def get_local_provider(settings: Settings = Depends(get_settings)):
    from app.db import SessionLocal
    with SessionLocal() as db:
        row = db.query(ModelVersion).filter(ModelVersion.provider == "local", ModelVersion.active.is_(True)).first()
    if row:
        from app.core.llm_provider import OllamaProvider
        return OllamaProvider(host=settings.ollama_host, model=row.model_name, embed_model=settings.llm_embed_model)
    return build_local_provider(settings)


def get_cloud_provider(settings: Settings = Depends(get_settings)):
    from app.db import SessionLocal
    with SessionLocal() as db:
        row = db.query(ModelVersion).filter(ModelVersion.provider == "cloud", ModelVersion.active.is_(True)).first()
    if row:
        from app.core.llm_provider import CloudProvider
        return CloudProvider(
            base_url=settings.llm_cloud_base_url,
            api_key=settings.llm_cloud_api_key,
            model=row.model_name,
            provider_label=settings.llm_cloud_provider,
        )
    return build_cloud_provider(settings)


def get_rag(settings: Settings = Depends(get_settings)):
    provider = get_local_provider(settings)
    return RAGIndex(settings.qdrant_url, settings.qdrant_collection, embed_fn=provider.embed)


def get_dispatcher(
    router: Router = Depends(get_router),
    settings: Settings = Depends(get_settings),
    rag: RAGIndex = Depends(get_rag),
) -> LLMDispatcher:
    local = get_local_provider(settings)
    cloud = get_cloud_provider(settings)
    return LLMDispatcher(
        router=router,
        local_provider=local,
        cloud_provider=cloud,
        rag=rag,
        hmac_key=settings.audit_hmac_key,
    )
