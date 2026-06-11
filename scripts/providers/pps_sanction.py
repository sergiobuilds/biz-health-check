"""조달청 나라장터 부정당제재업체정보 provider (data.go.kr 15129466 사용자정보 서비스).

스펙 실확인 (2026-06-11 3차 — swagger 명세 원문에서 확인):

- GET https://apis.data.go.kr/1230000/ao/UsrInfoService02/getUnptRsttCorpInfo02
- 파라미터: ServiceKey(대문자 S), numOfRows·pageNo(필수), type=json,
  inqryDiv(1=사업자번호 조회), bizno(inqryDiv=1일 때 필수, 숫자 10자리)
- 반환 항목: 사업자등록번호, 업체명, 법인등록번호, 제재시작/종료일자,
  제재기관명, 계약법구분, 제재근거법률, 조항호(코드·명), 시행규칙코드(명)
- upstream 명세에 명시된 한계(원문 요지):
  * 나라장터 미등록업체·개인에 대한 부정당제재는 미제공
  * [국가계약법] 조회시점에 제재만료·해제된 것은 제공되지 않음
  * [지방계약법] 조회시점에 정지·제재만료·해제된 것은 제공되지 않음
  → 즉 "조회시점 현재 유효한 제재"만 나온다. 과거 제재 이력 조회가 아니다.
- 같은 인증키로 https://www.data.go.kr/data/15129466/openapi.do 활용신청
  필요(자동승인). 미신청 시 HTTP 403.

이력: 1차 stub(명세 미특정) → 2차 fileData odcloud(15137996) 시도 —
해당 파일데이터는 '기관자체 다운로드' 제공형태로 포털 활용신청 플로우가
없어(odcloud 401 해소 불가) 폐기하고 이 정식 OpenAPI로 확정.
"""

from __future__ import annotations

import requests

from . import common

API_URL = ("https://apis.data.go.kr/1230000/ao/UsrInfoService02/"
           "getUnptRsttCorpInfo02")
APPLY_URL = "https://www.data.go.kr/data/15129466/openapi.do"
SOURCE = ("조달청 나라장터 부정당제재업체정보조회 — 공공데이터포털 "
          "나라장터 사용자정보 서비스 (data.go.kr 15129466, "
          "apis.data.go.kr/1230000/ao/UsrInfoService02/getUnptRsttCorpInfo02)")
MANUAL_NOTE = "수동 확인: 나라장터 https://www.g2b.go.kr 부정당업자 제재 검색"
COVERAGE_NOTE = ("이 API는 조회시점 현재 유효한 제재만 반환한다 — 제재만료·해제 건과 "
                 "나라장터 미등록업체·개인에 대한 제재는 나오지 않는다(만료 이력까지 "
                 f"보려면 수동 확인 필요). {MANUAL_NOTE}.")


def lookup(b_no: str, name: str | None = None) -> dict:
    """현재 유효한 부정당제재 조회 — 사업자등록번호 정확 일치(inqryDiv=1)."""
    no = common.normalize_b_no(b_no)
    key = common.api_key()
    if not key:
        return common.envelope(
            SOURCE, common.STATUS_NEEDS_KEY, common.ORIGIN_NEEDS_KEY,
            note=(f"{common.KEY_ENV_VAR} 환경변수가 없습니다. 공공데이터포털 키 발급 후 "
                  f"활용신청(자동승인)이 필요합니다: {APPLY_URL}. {MANUAL_NOTE}"))

    try:
        resp = requests.get(API_URL, params={
            "ServiceKey": key,
            "numOfRows": "100",
            "pageNo": "1",
            "type": "json",
            "inqryDiv": "1",
            "bizno": no,
        }, timeout=20)
        if resp.status_code in (401, 403):
            return common.envelope(
                SOURCE, common.STATUS_NEEDS_KEY, common.ORIGIN_NEEDS_KEY,
                note=(f"upstream HTTP {resp.status_code} — 키가 이 API에 활용신청되지 "
                      f"않았을 수 있습니다. 활용신청(자동승인): {APPLY_URL}. {MANUAL_NOTE}"))
        if resp.status_code != 200:
            return common.envelope(
                SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                note=f"upstream HTTP {resp.status_code}. {MANUAL_NOTE}")
        body = resp.json()
        response = body.get("response", {})
        header = response.get("header", {})
        result_code = str(header.get("resultCode", ""))
        if result_code not in ("00", "0"):
            return common.envelope(
                SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                note=(f"upstream resultCode={result_code} "
                      f"({header.get('resultMsg', '메시지 없음')}). {MANUAL_NOTE}"))
        body_part = response.get("body", {})
        items = body_part.get("items") or []
        if isinstance(items, dict):  # 1건일 때 dict로 오는 공공API 관례 방어
            items = items.get("item") or []
        if isinstance(items, dict):
            items = [items]
        total = body_part.get("totalCount", len(items))
    except requests.RequestException as err:
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note=f"네트워크 오류: {type(err).__name__}. {MANUAL_NOTE}")
    except Exception as err:  # lookup 경계 계약: 어떤 오류든 envelope로 강등, 크래시 금지
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note=f"예상 외 오류({type(err).__name__}). {MANUAL_NOTE}")

    result = {
        "bizno": no,
        "total_count": total,
        "active_sanctions": items,
        "match_basis": ("사업자등록번호 정확 일치 조회(inqryDiv=1) — 조회시점 "
                        "현재 유효한 제재 목록 (첫 100건)."),
    }
    return common.envelope(SOURCE, common.STATUS_OK, common.ORIGIN_LIVE,
                           result=result, note=COVERAGE_NOTE)
