"""biz-health-check provider 공통 계약.

모든 provider는 `lookup(b_no, name=None) -> dict(envelope)` 하나만 노출한다.

envelope 스키마(고정):

    {
      "source": str,            # 사람이 읽는 upstream 출처 표기 (기관·서비스·근거 URL)
      "looked_up_at": str,      # ISO8601(+09:00) 조회 시각
      "status": "ok" | "unavailable" | "needs-key",
      "result": dict | None,    # status=="ok"일 때만 dict, 그 외 None
      "origin": "live" | "unauthenticated-public" | "needs-key",
      "note": str | None,       # 안내·강등 사유·공개 범위 주의 (없으면 None)
    }

원칙:
- 점수·등급·해석 라벨 금지 — upstream이 돌려준 사실만 담는다.
- 인증키는 환경변수 ``DATA_GO_KR_KEY``에서 호출 시점에 동적으로 읽는다.
- 키 문자열을 코드·로그·note 어디에도 넣지 않는다. requests의 응답 URL에는
  serviceKey가 포함되므로 note에 응답 URL을 그대로 적지 않는다.
"""

from __future__ import annotations

import datetime as _dt
import os
import re

KEY_ENV_VAR = "DATA_GO_KR_KEY"

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NEEDS_KEY = "needs-key"
VALID_STATUSES = (STATUS_OK, STATUS_UNAVAILABLE, STATUS_NEEDS_KEY)

ORIGIN_LIVE = "live"
ORIGIN_PUBLIC = "unauthenticated-public"
ORIGIN_NEEDS_KEY = "needs-key"
VALID_ORIGINS = (ORIGIN_LIVE, ORIGIN_PUBLIC, ORIGIN_NEEDS_KEY)

KST = _dt.timezone(_dt.timedelta(hours=9))


def now_iso() -> str:
    """조회 시각 — KST ISO8601 초 단위."""
    return _dt.datetime.now(KST).isoformat(timespec="seconds")


def digits(value) -> str:
    """문자열에서 숫자만 추출 (하이픈 등 제거)."""
    return re.sub(r"\D", "", str(value or ""))


def normalize_b_no(value) -> str:
    """사업자등록번호 정규화 — 숫자 10자리만 허용."""
    normalized = digits(value)
    if not re.fullmatch(r"\d{10}", normalized):
        raise ValueError("사업자등록번호는 숫자 10자리여야 합니다 (하이픈 허용).")
    return normalized


def format_b_no(b_no: str) -> str:
    """10자리 사업자번호를 XXX-XX-XXXXX로 표기."""
    no = normalize_b_no(b_no)
    return f"{no[:3]}-{no[3:5]}-{no[5:]}"


def api_key() -> str:
    """공공데이터포털 인증키 — 호출 시점 동적 참조. 빈 문자열이면 키 없음."""
    return os.environ.get(KEY_ENV_VAR, "").strip()


def envelope(source: str, status: str, origin: str, result: dict | None = None,
             note: str | None = None) -> dict:
    """공통 envelope 생성 — 스키마 위반은 여기서 즉시 실패시킨다."""
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    if origin not in VALID_ORIGINS:
        raise ValueError(f"invalid origin: {origin!r}")
    if status == STATUS_OK and not isinstance(result, dict):
        raise ValueError("status=ok 인데 result가 dict가 아닙니다.")
    if status != STATUS_OK:
        if result is not None:
            raise ValueError("status!=ok 이면 result는 None이어야 합니다.")
        if not note:
            raise ValueError("status!=ok 이면 note(사유·안내)가 필요합니다.")
    return {
        "source": source,
        "looked_up_at": now_iso(),
        "status": status,
        "result": result,
        "origin": origin,
        "note": note,
    }
