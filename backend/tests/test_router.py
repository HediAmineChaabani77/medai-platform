import pytest

from app.core.router import Router, RoutingRequest, UseCase


class FakeConn:
    def __init__(self, online=True):
        self.online = online

    def is_online(self):
        return self.online


class FakePHI:
    def __init__(self, high=False):
        self.high = high

    def contains_high_sensitivity(self, text):
        return self.high


class FakePolicy:
    def __init__(self, override=None):
        self.override = override

    def override_for(self, use_case, department):
        return self.override


class FakeLoad:
    def __init__(self, depth=0):
        self.depth = depth

    def local_queue_depth(self):
        return self.depth


def make_router(**kw):
    defaults = {
        "connectivity": FakeConn(online=True),
        "phi": FakePHI(),
        "policy": FakePolicy(),
        "load": FakeLoad(),
        "text_len_threshold": 8000,
        "queue_threshold": 5,
        "force_local_only": False,
    }
    defaults.update(kw)
    return Router(**defaults)


def _req(uc=UseCase.UC1_DIAGNOSTIC, text="hello", meta=None):
    return RoutingRequest(use_case=uc, payload_text=text, metadata=meta or {})


def test_r0_force_local():
    r = make_router(force_local_only=True)
    d = r.decide(_req())
    assert d.provider == "local" and d.rule == "R0_FORCE_LOCAL"


def test_r1_offline():
    r = make_router(connectivity=FakeConn(online=False))
    d = r.decide(_req())
    assert d.provider == "local" and d.rule == "R1_OFFLINE"


def test_r2_high_sens_phi():
    r = make_router(phi=FakePHI(high=True))
    d = r.decide(_req(text="patient VIH+"))
    assert d.provider == "local" and d.rule == "R2_HIGH_SENS_PHI"


def test_r3_prescription_always_local():
    r = make_router()
    d = r.decide(_req(uc=UseCase.UC3_PRESCRIPTION))
    assert d.provider == "local" and d.rule == "R3_PRESCRIPTION"


def test_r4_admin_override_to_local():
    r = make_router(policy=FakePolicy(override="local"))
    d = r.decide(_req(uc=UseCase.UC2_REPORT))
    assert d.provider == "local" and d.rule == "R4_ADMIN_OVERRIDE"


def test_r4_admin_override_to_cloud():
    r = make_router(policy=FakePolicy(override="cloud"))
    d = r.decide(_req(uc=UseCase.UC2_REPORT))
    assert d.provider == "cloud" and d.rule == "R4_ADMIN_OVERRIDE"


def test_r5_text_too_long():
    r = make_router()
    d = r.decide(_req(text="a" * 9000))
    assert d.provider == "cloud" and d.rule == "R5_COMPLEXITY"


def test_r5_report_hospitalisation_to_cloud():
    r = make_router()
    d = r.decide(_req(uc=UseCase.UC2_REPORT, meta={"report_type": "Hospitalisation"}))
    assert d.provider == "cloud" and d.rule == "R5_COMPLEXITY"


def test_r6_load_shed():
    r = make_router(load=FakeLoad(depth=10))
    d = r.decide(_req())
    assert d.provider == "cloud" and d.rule == "R6_LOAD_SHED"


def test_r7_default_cloud():
    r = make_router()
    d = r.decide(_req())
    assert d.provider == "cloud" and d.rule == "R7_DEFAULT"


def test_rule_order_offline_beats_prescription():
    # Offline local must win even though prescription would also route local.
    r = make_router(connectivity=FakeConn(online=False))
    d = r.decide(_req(uc=UseCase.UC3_PRESCRIPTION))
    assert d.rule == "R1_OFFLINE"


def test_phi_regex_nir():
    from app.core.phi_detector import PHIDetector
    det = PHIDetector(nlp=False)
    rep = det.scan("Numéro 1 85 02 75 123 456 78")
    assert any(m.type == "nir" for m in rep.matches)


def test_phi_high_sens_hiv():
    from app.core.phi_detector import PHIDetector
    det = PHIDetector(nlp=False)
    assert det.contains_high_sensitivity("Patient VIH positif") is True


def test_phi_email_detected_but_not_high_sens():
    from app.core.phi_detector import PHIDetector
    det = PHIDetector(nlp=False)
    rep = det.scan("Contact: docteur@hopital.fr")
    assert rep.has_phi is True
    assert rep.high_sensitivity is False


def test_phi_rare_icd10():
    from app.core.phi_detector import PHIDetector
    det = PHIDetector(nlp=False)
    assert det.contains_high_sensitivity("Dx: E84 mucoviscidose confirmée") is True
