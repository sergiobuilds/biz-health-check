"""국세청 사업자등록 상태조회 provider (공공데이터포털 odcloud).

- 스펙: https://www.data.go.kr/data/15081808/openapi.do
  (POST https://api.odcloud.kr/api/nts-businessman/v1/status, b_no 배치 최대 100건)
- 라이브 검증: 2026-06-11 본 스킬 빌드 중 124-81-00998(삼성전자, 공개 정보)로
  "계속사업자" 응답 확인 (docs/BUILD-NOTES.md).
- DATA_GO_KR_KEY 없으면 status="needs-key" + 발급 안내. 키는 env 동적 참조,
  코드·로그·note에 키 문자열을 넣지 않는다.
- 해석 라벨 없음 — b_stt·tax_type 등 upstream 필드 원문 그대로 반환.
"""

from __future__ import annotations

import requests

from . import common

SOURCE = ("국세청 사업자등록 상태조회 — 공공데이터포털 odcloud "
          "(data.go.kr 15081808, api.odcloud.kr/api/nts-businessman/v1/status)")
API_URL = "https://api.odcloud.kr/api/nts-businessman/v1/status"
APPLY_URL = "https://www.data.go.kr/data/15081808/openapi.do"
NEEDS_KEY_NOTE = (
    f"환경변수 {common.KEY_ENV_VAR} 에 공공데이터포털 인증키가 없습니다. "
    "data.go.kr 가입 후 '국세청_사업자등록정보 진위확인 및 상태조회 서비스' "
    f"활용신청을 하고 발급 키를 설정하세요: {APPLY_URL}"
)


def lookup(b_no: str, name: str | None = None) -> dict:
    """사업자등록 상태 단건 조회. name은 이 API에서 사용하지 않는다."""
    no = common.normalize_b_no(b_no)
    key = common.api_key()
    if not key:
        return common.envelope(SOURCE, common.STATUS_NEEDS_KEY, common.ORIGIN_NEEDS_KEY,
                               note=NEEDS_KEY_NOTE)
    try:
        resp = requests.post(API_URL, params={"serviceKey": key},
                             json={"b_no": [no]}, timeout=15)
    except requests.RequestException as err:
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note=f"네트워크 오류: {type(err).__name__}")
    if resp.status_code in (401, 403):
        return common.envelope(
            SOURCE, common.STATUS_NEEDS_KEY, common.ORIGIN_NEEDS_KEY,
            note=(f"HTTP {resp.status_code} — 키가 이 서비스에 활용신청되지 않았거나 "
                  f"거부되었습니다. 활용신청: {APPLY_URL}"))
    if resp.status_code != 200:
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note=f"upstream HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError:
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note="응답 JSON 파싱 실패")

    data = payload.get("data") or []
    record = next((item for item in data
                   if common.digits(item.get("b_no")) == no), None)
    found = bool(record and record.get("b_stt"))
    result = {
        "b_no": no,
        "request_cnt": payload.get("request_cnt"),
        "match_cnt": payload.get("match_cnt"),
        "found": found,
        # upstream 필드 원문 그대로 (b_stt, b_stt_cd, tax_type, tax_type_cd,
        # end_dt, utcc_yn, tax_type_change_dt, invoice_apply_dt, rbf_tax_type 등)
        "record": record,
    }
    note = None
    if record is not None and not record.get("b_stt"):
        note = "국세청 응답에 b_stt가 비어 있음 — '국세청에 등록되지 않은 사업자등록번호' 케이스(원문 그대로)."
    return common.envelope(SOURCE, common.STATUS_OK, common.ORIGIN_LIVE,
                           result=result, note=note)
