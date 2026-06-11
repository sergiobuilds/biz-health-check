"""오프라인 단위 테스트 — 네트워크 무호출(키 제거 + requests 차단)."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from providers import common  # noqa: E402
from providers import fsc_corp, nps_pension, nts_delinquent, nts_status, pps_sanction  # noqa: E402

ALL_PROVIDERS = [nts_status, nps_pension, nts_delinquent, fsc_corp, pps_sanction]
ENVELOPE_KEYS = {"source", "looked_up_at", "status", "result", "origin", "note"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """키 제거 + requests 호출 시 즉시 실패 — 모든 provider가 우아하게 강등돼야 함."""
    monkeypatch.delenv(common.KEY_ENV_VAR, raising=False)

    def _blocked(*_a, **_k):
        raise RuntimeError("network blocked in tests")

    import requests
    monkeypatch.setattr(requests, "get", _blocked)
    monkeypatch.setattr(requests, "post", _blocked)


def test_normalize_b_no():
    assert common.normalize_b_no("124-81-00998") == "1248100998"
    with pytest.raises(ValueError):
        common.normalize_b_no("123")


def test_envelope_guard():
    with pytest.raises(ValueError):
        common.envelope("s", "ok", "live", result=None)            # ok인데 result 없음
    with pytest.raises(ValueError):
        common.envelope("s", "unavailable", "live", result={})     # 비ok인데 result 존재
    with pytest.raises(ValueError):
        common.envelope("s", "unavailable", "live", note=None)     # 비ok인데 note 없음


@pytest.mark.parametrize("provider", ALL_PROVIDERS,
                         ids=[p.__name__.split(".")[-1] for p in ALL_PROVIDERS])
def test_provider_degrades_offline(provider):
    """키 없음 + 네트워크 차단에서도 예외 없이 envelope 스키마로 강등."""
    env = provider.lookup("124-81-00998", name="테스트상사")
    assert set(env) == ENVELOPE_KEYS
    assert env["status"] in common.VALID_STATUSES
    assert env["origin"] in common.VALID_ORIGINS
    assert env["status"] != common.STATUS_OK            # 오프라인이므로 ok 불가
    assert env["result"] is None and env["note"]


def test_no_judgment_labels():
    """해석 라벨 금지 — 강등 note에 점수·등급·위험 어휘가 없어야 함."""
    for provider in ALL_PROVIDERS:
        env = provider.lookup("124-81-00998", name="테스트상사")
        for word in ("위험", "점수", "등급"):
            assert word not in (env["note"] or ""), (provider.__name__, word)
