"""금융위원회 기업기본정보(법인 개요) provider (공공데이터포털 15043184).

- GET apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2/getCorpOutline_V2
- 요청 파라미터가 crno(법인등록번호 13자리)/corpNm(법인명)뿐이라 사업자번호(10자리)
  단독 조회는 불가 — 법인명(corpNm) 기준 조회가 현실적.
- 사업자번호 교차검증: 응답 item에 사업자번호로 볼 수 있는 필드(bzno)가 있으면
  입력 번호와 대조하고, 없으면 "교차검증 불가" 사실을 그대로 표기한다 (단정 금지).
- 활용신청 안 된 키는 게이트웨이가 HTTP 403 "Forbidden"을 반환
  (2026-06-11 실측) → status="needs-key" 안내.
"""

from __future__ import annotations

import requests

from . import common

SOURCE = ("금융위원회 기업기본정보 getCorpOutline_V2 — 공공데이터포털 "
          "(data.go.kr 15043184, apis.data.go.kr/1160100/GetCorpBasicInfoService_V2)")
API_URL = ("https://apis.data.go.kr/1160100/service/"
           "GetCorpBasicInfoService_V2/getCorpOutline_V2")
APPLY_URL = "https://www.data.go.kr/data/15043184/openapi.do"
NEEDS_KEY_NOTE = (
    f"환경변수 {common.KEY_ENV_VAR} 에 공공데이터포털 인증키가 없습니다. "
    "data.go.kr 가입 후 '금융위원회_기업기본정보' 활용신청을 하고 발급 키를 "
    f"설정하세요: {APPLY_URL}"
)
NAME_REQUIRED_NOTE = (
    "이 API의 검색 파라미터는 crno(법인등록번호)/corpNm(법인명)뿐이라 "
    "사업자등록번호 단독 조회가 불가합니다. --name 으로 법인명을 지정하세요. "
    f"명세: {APPLY_URL}"
)


def _live_items(payload: dict) -> list[dict]:
    """응답에서 item 목록 추출 (0건이면 items가 ''인 변형 흡수)."""
    header = payload.get("response", {}).get("header", {})
    if header.get("resultCode") not in ("00", "0"):
        raise ValueError(f"resultCode={header.get('resultCode')} "
                         f"{header.get('resultMsg', '')}".strip())
    items = payload.get("response", {}).get("body", {}).get("items") or {}
    item = items.get("item") if isinstance(items, dict) else items
    if isinstance(item, dict):
        item = [item]
    return item or []


def lookup(b_no: str, name: str | None = None) -> dict:
    """법인 개요 조회 — 법인명 기준 + 가능하면 사업자번호 교차검증."""
    no = common.normalize_b_no(b_no)
    if not common.api_key():
        return common.envelope(SOURCE, common.STATUS_NEEDS_KEY, common.ORIGIN_NEEDS_KEY,
                               note=NEEDS_KEY_NOTE)
    if not (name or "").strip():
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note=NAME_REQUIRED_NOTE)
    name = name.strip()

    try:
        resp = requests.get(API_URL, params={
            "serviceKey": common.api_key(),
            "pageNo": 1,
            "numOfRows": 10,
            "resultType": "json",
            "corpNm": name,
        }, timeout=15)
    except requests.RequestException as err:
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note=f"네트워크 오류: {type(err).__name__}")
    if resp.status_code in (401, 403):
        return common.envelope(
            SOURCE, common.STATUS_NEEDS_KEY, common.ORIGIN_NEEDS_KEY,
            note=(f"upstream HTTP {resp.status_code} — 키가 이 API에 활용신청되지 "
                  f"않았을 수 있습니다. 활용신청: {APPLY_URL}"))
    if resp.status_code != 200:
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note=f"upstream HTTP {resp.status_code}")
    try:
        items = _live_items(resp.json())
    except ValueError as err:
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note=f"upstream 오류 응답: {err}")

    # 사업자번호 교차검증 — 응답에 bzno 계열 필드가 있을 때만 가능
    has_bzno = any("bzno" in item for item in items)
    matched = [item for item in items
               if common.digits(item.get("bzno", "")) == no] if has_bzno else []
    cross_check = {
        "checked": has_bzno,
        "input_b_no": no,
        "matched_candidates": matched,
    }
    note = None
    if items and not has_bzno:
        note = ("응답에 사업자등록번호 필드가 없어 입력 번호와의 교차검증 불가 — "
                "법인명 일치 후보의 사실만 나열 (crno는 법인등록번호로 별개 번호).")

    result = {
        "query_corp_nm": name,
        "candidate_count": len(items),
        "candidates": items,            # upstream 필드 원문 그대로
        "b_no_cross_check": cross_check,
    }
    return common.envelope(SOURCE, common.STATUS_OK, common.ORIGIN_LIVE,
                           result=result, note=note)
