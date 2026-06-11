"""조달청 나라장터 부정당제재 내역 provider (data.go.kr 15137996 odcloud fileData API).

스펙 실확인 (2026-06-11 2차 — 1차 stub에서 live로 승격):

- 파일데이터 '조달청_나라장터 부정당제재 내역'(data.go.kr 15137996)은
  odcloud fileData API로도 제공된다:
  GET https://api.odcloud.kr/api/15137996/v1/uddi:475c63ef-b675-4450-9735-907783288fb8
- 컬럼(페이지 게시 메타데이터에서 확인): 계약법구분, 기관, 법인등록번호,
  **사업자등록번호**, 소관구분, 시행규칙76조별표2(명), 업체, 제재근거법률,
  제재기간월수/일수, 제재시작일자, 제재입력일시, 제재종료일자, 조달업무영역,
  조문명, 조항호, 처분상태.
- 사업자등록번호가 직접 수록되므로 (체납 명단과 달리) 입력 사업자번호와의
  동일성을 자료 기준으로 확인할 수 있다.
- odcloud cond 필터: ``cond[컬럼명::EQ]=값``. 수록 값의 하이픈 포함 여부가
  문서화돼 있지 않아 숫자 10자리 → XXX-XX-XXXXX 순서로 최대 2회 질의한다.
- 같은 인증키라도 이 fileData의 오픈API에 대한 활용신청이 따로 필요하다
  (미신청 시 odcloud가 401 "유효하지 않은 인증키" 반환 — 실측 확인).
- 자료는 스냅샷 게시본(수시 갱신)이므로 게시 기준일이 최신이 아닐 수 있다.
"""

from __future__ import annotations

import requests

from . import common

UDDI = "uddi:475c63ef-b675-4450-9735-907783288fb8"
API_URL = f"https://api.odcloud.kr/api/15137996/v1/{UDDI}"
APPLY_URL = "https://www.data.go.kr/data/15137996/fileData.do"
SOURCE = ("조달청 나라장터 부정당제재 내역 — 공공데이터포털 fileData odcloud API "
          f"(data.go.kr 15137996, api.odcloud.kr/api/15137996/v1/{UDDI})")
MANUAL_NOTE = ("수동 확인: 나라장터 https://www.g2b.go.kr 부정당업자 제재 검색 또는 "
               f"파일데이터 {APPLY_URL}")
SNAPSHOT_NOTE = ("자료는 수시 갱신되는 스냅샷 게시본이므로 게시 기준일 이후 "
                 "제재 변동은 반영되지 않았을 수 있다. 제재기간(시작·종료일자)과 "
                 "처분상태의 현재 유효성 판단은 사용자 몫이다.")
PER_PAGE = 100


def _query(key: str, cond_col: str, cond_op: str, value: str) -> list[dict]:
    """odcloud cond 1회 질의 — 첫 페이지(최대 100행)만."""
    resp = requests.get(API_URL, params={
        "serviceKey": key,
        "page": "1",
        "perPage": str(PER_PAGE),
        "returnType": "JSON",
        f"cond[{cond_col}::{cond_op}]": value,
    }, timeout=20)
    if resp.status_code == 401:
        raise PermissionError("HTTP 401")
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    body = resp.json()
    if "data" not in body:
        raise RuntimeError(f"예상 외 응답 구조 (keys={sorted(body)[:5]})")
    return body["data"]


def lookup(b_no: str, name: str | None = None) -> dict:
    """부정당제재 내역 조회 — 사업자등록번호 EQ 질의 (숫자/하이픈 표기 순)."""
    no = common.normalize_b_no(b_no)
    key = common.api_key()
    if not key:
        return common.envelope(
            SOURCE, common.STATUS_NEEDS_KEY, common.ORIGIN_NEEDS_KEY,
            note=(f"{common.KEY_ENV_VAR} 환경변수가 없습니다. 공공데이터포털 키 발급 후 "
                  f"이 파일데이터의 오픈API 활용신청이 필요합니다: {APPLY_URL}. "
                  f"{MANUAL_NOTE}"))

    try:
        queried_as = no
        rows = _query(key, "사업자등록번호", "EQ", no)
        if not rows:
            queried_as = common.format_b_no(no)
            rows = _query(key, "사업자등록번호", "EQ", queried_as)
    except PermissionError:
        return common.envelope(
            SOURCE, common.STATUS_NEEDS_KEY, common.ORIGIN_NEEDS_KEY,
            note=("upstream HTTP 401 — 키가 이 파일데이터의 오픈API에 활용신청되지 "
                  f"않았을 수 있습니다. 활용신청: {APPLY_URL}. {MANUAL_NOTE}"))
    except requests.RequestException as err:
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note=f"네트워크 오류: {type(err).__name__}. {MANUAL_NOTE}")
    except Exception as err:  # lookup 경계 계약: 어떤 오류든 envelope로 강등, 크래시 금지
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                               note=f"예상 외 오류({type(err).__name__}). {MANUAL_NOTE}")

    result = {
        "b_no": no,
        "queried_as": queried_as,
        "match_count": len(rows),
        "matches": rows,
        "match_basis": ("자료에 사업자등록번호가 수록돼 있어 입력 사업자번호 기준 "
                        "정확 일치 조회 결과다 (첫 100건)."),
    }
    return common.envelope(SOURCE, common.STATUS_OK, common.ORIGIN_LIVE,
                           result=result, note=SNAPSHOT_NOTE)
