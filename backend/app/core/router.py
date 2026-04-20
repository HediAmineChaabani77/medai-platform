from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class UseCase:
    UC1_DIAGNOSTIC = "UC1_DIAGNOSTIC"
    UC2_REPORT = "UC2_REPORT"
    UC3_PRESCRIPTION = "UC3_PRESCRIPTION"
    UC_QA = "UC_QA"


@dataclass
class RoutingRequest:
    use_case: str
    payload_text: str
    patient_context: dict | None = None
    metadata: dict | None = None


@dataclass
class RoutingDecision:
    provider: str  # "local" or "cloud"
    reason: str
    rule: str
    confidence_label: str  # "hard" | "soft"


class ConnectivityLike(Protocol):
    def is_online(self) -> bool: ...


class PHILike(Protocol):
    def contains_high_sensitivity(self, text: str) -> bool: ...


class PolicyLookup(Protocol):
    def override_for(self, use_case: str, department: str | None) -> str | None: ...


class LoadProbe(Protocol):
    def local_queue_depth(self) -> int: ...


class Router:
    """Rule-based router. NO learning, NO RL. Rules applied first-match-wins."""

    def __init__(
        self,
        connectivity: ConnectivityLike,
        phi: PHILike,
        policy: PolicyLookup,
        load: LoadProbe,
        text_len_threshold: int = 8000,
        queue_threshold: int = 5,
        force_local_only: bool = False,
    ):
        self.connectivity = connectivity
        self.phi = phi
        self.policy = policy
        self.load = load
        self.text_len_threshold = text_len_threshold
        self.queue_threshold = queue_threshold
        self.force_local_only = force_local_only

    def decide(self, req: RoutingRequest) -> RoutingDecision:
        department = (req.metadata or {}).get("department")
        report_type = (req.metadata or {}).get("report_type")

        # Rule 0 (operator override via env — supports the "just local" bring-up):
        if self.force_local_only:
            return RoutingDecision("local", "force_local_only flag set", "R0_FORCE_LOCAL", "hard")

        # Rule 1: offline → local
        if not self.connectivity.is_online():
            return RoutingDecision("local", "offline", "R1_OFFLINE", "hard")

        # Rule 2: high-sensitivity PHI → local
        if self.phi.contains_high_sensitivity(req.payload_text or ""):
            return RoutingDecision("local", "high_sensitivity_phi", "R2_HIGH_SENS_PHI", "hard")

        # Rule 3: prescription safety → always local
        if req.use_case == UseCase.UC3_PRESCRIPTION:
            return RoutingDecision("local", "prescription_safety_critical_local", "R3_PRESCRIPTION", "hard")

        # Rule 3b: QA on local indexed dataset should stay local for deterministic behavior.
        if req.use_case == UseCase.UC_QA:
            return RoutingDecision("local", "qa_dataset_local", "R3B_QA_LOCAL", "hard")

        # Rule 4: admin override
        override = self.policy.override_for(req.use_case, department)
        if override in ("local", "cloud"):
            return RoutingDecision(override, f"admin_override:{override}", "R4_ADMIN_OVERRIDE", "hard")

        # Rule 5: complexity → cloud
        if (
            len(req.payload_text or "") > self.text_len_threshold
            or (req.use_case == UseCase.UC2_REPORT and report_type in ("Hospitalisation", "Opératoire"))
        ):
            return RoutingDecision("cloud", "complexity_high", "R5_COMPLEXITY", "soft")

        # Rule 6: load shedding
        if self.load.local_queue_depth() > self.queue_threshold:
            return RoutingDecision("cloud", "local_load_shed", "R6_LOAD_SHED", "soft")

        # Rule 7: default → cloud
        return RoutingDecision("cloud", "default_cloud_quality", "R7_DEFAULT", "soft")
