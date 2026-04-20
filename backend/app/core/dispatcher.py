from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.llm_provider import LLMProvider, LLMResponse
from app.core.rag import RAGIndex, Retrieval, build_rag_prompt
from app.core.router import Router, RoutingRequest


@dataclass
class LLMCallResult:
    response: LLMResponse
    provider_used: str
    model_used: str
    rule: str
    reason: str
    citations: list[dict]
    retrievals: list[Retrieval]
    latency_ms: int
    audit_id: int


class LLMDispatcher:
    """Glue layer: router -> provider, auto RAG retrieval, auto audit logging."""

    def __init__(
        self,
        router: Router,
        local_provider: LLMProvider,
        cloud_provider: LLMProvider,
        rag: RAGIndex,
        hmac_key: str,
    ):
        self.router = router
        self.local_provider = local_provider
        self.cloud_provider = cloud_provider
        self.rag = rag
        self.hmac_key = hmac_key

    async def run(
        self,
        db: Session,
        *,
        use_case: str,
        query: str,
        payload_for_routing: str | None = None,
        system: str | None = None,
        user_id: str | None = None,
        patient_id: str | None = None,
        metadata: dict | None = None,
        patient_context: dict | None = None,
        use_rag: bool = True,
        max_tokens: int = 512,
        temperature: float = 0.2,
        format: str | None = None,
        extra_audit: dict | None = None,
    ) -> LLMCallResult:
        # 1. Router decision
        req = RoutingRequest(
            use_case=use_case,
            payload_text=payload_for_routing if payload_for_routing is not None else query,
            patient_context=patient_context,
            metadata=metadata or {},
        )
        decision = self.router.decide(req)

        # 2. RAG retrieval (ALWAYS local, works offline)
        retrievals: list[Retrieval] = []
        citations: list[dict] = []
        prompt = query
        if use_rag:
            retrievals = await self.rag.retrieve(query, top_k=5)
            prompt, citations = build_rag_prompt(query, retrievals)

        # 3. Provider dispatch
        provider = self.local_provider if decision.provider == "local" else self.cloud_provider
        t0 = time.perf_counter()
        try:
            response = await provider.generate(prompt, system=system, max_tokens=max_tokens, temperature=temperature, format=format)
        except Exception as e:
            # Offline-safe fallback: if cloud fails, retry local.
            if decision.provider == "cloud":
                decision_rule = decision.rule + "+FALLBACK_LOCAL"
                response = await self.local_provider.generate(prompt, system=system, max_tokens=max_tokens, temperature=temperature)
                decision = type(decision)(provider="local", reason=f"cloud_failed:{type(e).__name__}", rule=decision_rule, confidence_label="hard")
            else:
                raise
        latency_ms = int((time.perf_counter() - t0) * 1000)

        # 4. Audit
        audit_payload: dict[str, Any] = {
            "query_len": len(query),
            "retrieved_chunks": [c["chunk_id"] for c in citations],
            "reason": decision.reason,
            "metadata": metadata or {},
        }
        if extra_audit:
            audit_payload.update(extra_audit)
        row = append_audit(
            db,
            self.hmac_key,
            event_type="llm_call",
            user_id=user_id,
            patient_id=patient_id,
            use_case=use_case,
            provider=response.provider,
            model=response.model,
            rule=decision.rule,
            latency_ms=latency_ms,
            payload=audit_payload,
        )

        return LLMCallResult(
            response=response,
            provider_used=response.provider,
            model_used=response.model,
            rule=decision.rule,
            reason=decision.reason,
            citations=citations,
            retrievals=retrievals,
            latency_ms=latency_ms,
            audit_id=row.id,
        )
