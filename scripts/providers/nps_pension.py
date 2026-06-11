"""국민연금 가입 사업장 내역 provider (공공데이터포털 3046071).

스펙 실확인 (2026-06-11, data.go.kr 게시 명세 — docs/BUILD-NOTES.md에 출처 기록):

- base: http://apis.data.go.kr/B552015/NpsBplcInfoInqireService
- getBassInfoSearch (기본): wkpl_nm **필수**, bzowr_rgst_no 옵션 — 사업자번호
  **앞 6자리만** 공개. 응답 bzowrRgstNo는 "124815****" 형태 마스킹.
  wkplJnngStcd 1:등록 2:탈퇴, wkplStylDvcd 1:법인 2:개인.
- getDetailInfoSearch (상세): seq 필수 (+ data_crt_ym) — jnngpCnt(가입자수),
  crrmmNtcAmt(당월고지금액), adptDt, scsnDt, nwAcqzrCnt, lssJnngpCnt.
- getPdAcctoSttusInfoSearch (기간별 현황): seq 기준 월 스냅샷 — 시계열로 반환.
- 공개 범위: 법인·근로자 3인 이상 사업장 위주(개인 사업장 미공개 주의).

라이브 검증 한계: 2026-06-11 현재 apis.data.go.kr의 B552015 namespace 전체가
키 유무와 무관하게 HTTP 500 "Unexpected errors"를 반환해(존재하지 않는 오퍼레이션
이름도 동일) 라이브 응답 검증 불가. 따라서 본 provider는 오류 강등 경로가 기본
동작이며, 상세·기간별 오퍼레이션의 요청 파라미터 표기(snake_case)는 기본 조회
오퍼레이션의 확인된 표기 관행을 따른 것으로 라이브 재검증 전까지 잠정이다.

사업자번호 매칭 원칙: 앞 6자리 prefix + 상호 문자열 비교만 가능. 후보가 여럿이면
후보 목록을 그대로 반환하고 특정하지 않는다 (임의 단정 금지).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

from . import common

SOURCE = ("국민연금공단 국민연금 가입 사업장 내역 — 공공데이터포털 "
          "(data.go.kr 3046071, apis.data.go.kr/B552015/NpsBplcInfoInqireService)")
BASE_URL = "http://apis.data.go.kr/B552015/NpsBplcInfoInqireService"
APPLY_URL = "https://www.data.go.kr/data/3046071/openapi.do"
NEEDS_KEY_NOTE = (
    f"환경변수 {common.KEY_ENV_VAR} 에 공공데이터포털 인증키가 없습니다. "
    "data.go.kr 가입 후 '국민연금공단_국민연금 가입 사업장 내역' "
    f"활용신청을 하고 발급 키를 설정하세요: {APPLY_URL}"
)
NAME_REQUIRED_NOTE = (
    "이 API는 사업장명(wkpl_nm)이 필수이고 사업자등록번호는 앞 6자리만 공개되어 "
    "번호 단독 특정이 불가합니다. --name 으로 상호를 지정해야 조회할 수 있습니다. "
    f"명세: {APPLY_URL}"
)
DISCLOSURE_NOTE = ("사업자등록번호는 앞 6자리만 공개(뒷자리 마스킹)되므로 입력 번호와의 "
                   "완전 일치 확인은 불가 — 앞 6자리 + 상호 일치 후보의 사실만 나열하며, "
                   "후보가 여럿이면 특정은 사용자 판단에 맡긴다.")

# 게이트웨이 인증 오류 reason code (OpenAPI_ServiceResponse) — 활용신청·키 문제 계열
_AUTH_REASON_CODES = {"20", "21", "30", "31", "32", "33"}


def _parse_xml(text: str) -> dict:
    """data.go.kr 표준 XML 응답 분류.

    반환: {"kind": "items"|"auth-error"|"error", ...}
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {"kind": "error", "reason": "XML 파싱 실패"}

    if root.tag == "OpenAPI_ServiceResponse":  # 게이트웨이 오류 응답
        reason_code = (root.findtext(".//returnReasonCode") or "").strip()
        auth_msg = (root.findtext(".//returnAuthMsg") or "").strip()
        kind = "auth-error" if reason_code in _AUTH_REASON_CODES else "error"
        return {"kind": kind, "reason": f"{auth_msg or 'SERVICE ERROR'} (code {reason_code})"}

    result_code = (root.findtext(".//header/resultCode") or "").strip()
    result_msg = (root.findtext(".//header/resultMsg") or "").strip()
    if result_code not in ("00", "0"):
        return {"kind": "error", "reason": f"resultCode={result_code} {result_msg}".strip()}
    items = [{child.tag: (child.text or "").strip() for child in item}
             for item in root.findall(".//body/items/item")]
    return {"kind": "items", "items": items,
            "total_count": (root.findtext(".//body/totalCount") or "").strip()}


def _call(op: str, params: dict) -> dict:
    """오퍼레이션 1회 호출 → 분류 결과. 키는 여기서만 주입하고 밖으로 내보내지 않는다."""
    try:
        resp = requests.get(f"{BASE_URL}/{op}",
                            params={"serviceKey": common.api_key(), **params},
                            timeout=15)
    except requests.RequestException as err:
        return {"kind": "error", "reason": f"네트워크 오류: {type(err).__name__}"}
    if resp.status_code in (401, 403):
        return {"kind": "auth-error", "reason": f"HTTP {resp.status_code}"}
    if resp.status_code != 200:
        # 2026-06-11 실측: B552015 전체가 HTTP 500 "Unexpected errors" (키 무관)
        body = (resp.text or "").strip()[:80]
        return {"kind": "error", "reason": f"upstream HTTP {resp.status_code} {body}".strip()}
    return _parse_xml(resp.text)


def lookup(b_no: str, name: str | None = None) -> dict:
    """가입 사업장 조회 — 상호 필수, 앞 6자리 prefix 보조."""
    no = common.normalize_b_no(b_no)
    if not common.api_key():
        return common.envelope(SOURCE, common.STATUS_NEEDS_KEY, common.ORIGIN_NEEDS_KEY,
                               note=NEEDS_KEY_NOTE)
    if not (name or "").strip():
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note=NAME_REQUIRED_NOTE)
    name = name.strip()
    prefix = no[:6]

    basic = _call("getBassInfoSearch",
                  {"wkpl_nm": name, "bzowr_rgst_no": prefix,
                   "pageNo": 1, "numOfRows": 100})
    if basic["kind"] == "auth-error":
        return common.envelope(
            SOURCE, common.STATUS_NEEDS_KEY, common.ORIGIN_NEEDS_KEY,
            note=(f"upstream 거부({basic['reason']}) — 키가 이 API에 활용신청되지 "
                  f"않았을 수 있습니다. 활용신청: {APPLY_URL}"))
    if basic["kind"] == "error":
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note=f"{basic['reason']} — 수동 확인: {APPLY_URL}")

    candidates = basic["items"]
    # prefix 재확인 (upstream 필터를 신뢰하되 방어적으로 한 번 더)
    candidates = [it for it in candidates
                  if common.digits(it.get("bzowrRgstNo", "")).startswith(prefix)
                  or not it.get("bzowrRgstNo")]
    exact = [it for it in candidates if (it.get("wkplNm") or "").strip() == name]
    chosen = candidates[0] if len(candidates) == 1 else (exact[0] if len(exact) == 1 else None)

    detail_items = None
    monthly = None
    partial_notes = []
    if chosen is not None and chosen.get("seq"):
        detail = _call("getDetailInfoSearch",
                       {"seq": chosen["seq"], "data_crt_ym": chosen.get("dataCrtYm", "")})
        if detail["kind"] == "items":
            detail_items = detail["items"] or None
        else:
            partial_notes.append(f"상세조회 실패({detail['reason']})")
        period = _call("getPdAcctoSttusInfoSearch", {"seq": chosen["seq"]})
        if period["kind"] == "items":
            monthly = sorted(period["items"],
                             key=lambda it: it.get("dataCrtYm", "")) or None
        else:
            partial_notes.append(f"기간별 현황 조회 실패({period['reason']})")

    result = {
        "query": {"wkpl_nm": name, "bzowr_rgst_no_prefix": prefix},
        "candidate_count": len(candidates),
        "candidates": candidates,           # upstream 필드 원문 그대로
        "selected_candidate": chosen,       # 단일 후보일 때만 — 아니면 None(특정 안 함)
        "detail": detail_items,             # jnngpCnt·crrmmNtcAmt 등 (단일 후보일 때만)
        "monthly_status": monthly,          # 월 스냅샷 시계열 (dataCrtYm 오름차순)
        "disclosure_note": DISCLOSURE_NOTE,
    }
    note = "; ".join(partial_notes) if partial_notes else None
    return common.envelope(SOURCE, common.STATUS_OK, common.ORIGIN_LIVE,
                           result=result, note=note)
