"""국세청 고액·상습체납자 명단공개 검색 provider (nts.go.kr 무인증 공개 검색).

실확인 (2026-06-11, requests로 브라우저 없이 재현 — docs/BUILD-NOTES.md):

- POST https://www.nts.go.kr/nts/ad/openInfo/selectList.do (무인증)
- tcd=1 법인 명단: searchType 1=법인명 2=대표자 3=법인 소재지 4=대표자 주소
  컬럼: No, 공개년도, 법인명, 대표자, 업종, 법인소재지, 대표자 주소,
        총 체납액, 세목, 납기, 체납건수, 체납요지
- tcd=2 개인 명단: searchType 1=성명 2=주소 3=상호 4=직업
  컬럼: No, 공개년도, 성명, 연령, 상호, 직업(업종), 체납자 주소,
        총 체납액, 세목, 납기, 체납건수, 체납요지
- 0건이면 단일 셀 "조회된 데이터가 없습니다." 렌더.
- 명단에는 **사업자등록번호가 수록되지 않는다** → 상호·법인명 문자열 기준
  후보 사실만 나열 가능, 입력 사업자번호와의 동일성 단정 불가.

차단·구조 변경에 취약한 HTML 스크래핑이므로 마커가 어긋나면 즉시
status="unavailable" + 수동 확인 URL로 강등한다. 호출은 명단(법인/개인)당
1회씩, 첫 페이지만 — 페이지네이션 루프 없음.
"""

from __future__ import annotations

import re

import requests

from . import common

SOURCE = ("국세청 고액·상습체납자 명단공개 검색 — nts.go.kr 누리집 공개 검색 "
          "(무인증, www.nts.go.kr/nts/ad/openInfo/selectList.do)")
URL = "https://www.nts.go.kr/nts/ad/openInfo/selectList.do"
MANUAL_NOTE = f"수동 확인: 브라우저에서 {URL} 접속 후 명단공개 검색"
HEADERS = {
    # 실측: 일반 브라우저 UA로 정상 응답 확인 (2026-06-11)
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
}

CORP_COLUMNS = ("no", "공개년도", "법인명", "대표자", "업종", "법인소재지",
                "대표자주소", "총체납액", "세목", "납기", "체납건수", "체납요지")
INDIV_COLUMNS = ("no", "공개년도", "성명", "연령", "상호", "직업(업종)", "체납자주소",
                 "총체납액", "세목", "납기", "체납건수", "체납요지")

IDENTITY_NOTE = ("명단공개 자료에는 사업자등록번호가 수록되지 않아 입력 사업자번호와의 "
                 "동일성은 확인할 수 없다 — 상호·법인명 문자열 일치 후보의 공개 사실만 "
                 "나열하며, 동명 상호일 가능성은 사용자가 판단한다.")

_HEADING_MARKER = "고액상습체납자"
_ZERO_MARKER = "조회된 데이터가 없습니다"


class StructureChanged(RuntimeError):
    """페이지 구조가 기대 마커와 다름 — 우아한 강등 트리거."""


def _strip_tags(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def _parse_rows(html: str, columns: tuple) -> list[dict]:
    if _HEADING_MARKER not in html.replace(" ", ""):
        raise StructureChanged("명단공개 페이지 마커(고액상습체납자) 미발견")
    if _ZERO_MARKER in html:
        return []
    cells = [_strip_tags(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", html, re.S)]
    if not cells or len(cells) % len(columns) != 0:
        raise StructureChanged(f"표 셀 수({len(cells)})가 컬럼 수({len(columns)})의 배수가 아님")
    return [dict(zip(columns, cells[i:i + len(columns)]))
            for i in range(0, len(cells), len(columns))]


def _search(tcd: str, search_type: str, value: str, columns: tuple) -> list[dict]:
    """명단 1종 검색 1회 (첫 페이지, 최대 100행)."""
    resp = requests.post(URL, data={
        "tcd": tcd,
        "searchType": search_type,
        "searchValue": value,
        "searchYear": "",
        "currPage": "1",
        "pageIndex": "100",
        "search_order": "1",
    }, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        raise StructureChanged(f"HTTP {resp.status_code}")
    return _parse_rows(resp.text, columns)


def lookup(b_no: str, name: str | None = None) -> dict:
    """고액·상습체납자 명단공개 대조 — 법인 명단(법인명)·개인 명단(상호) 각 1회."""
    common.normalize_b_no(b_no)  # 입력 검증만 — 명단에는 사업자번호가 없다
    if not (name or "").strip():
        return common.envelope(
            SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_PUBLIC,
            note=("명단공개 자료에 사업자등록번호가 수록되지 않아 상호·법인명 없이 "
                  f"검색할 수 없습니다. --name 으로 상호를 지정하세요. {MANUAL_NOTE}"))
    name = name.strip()

    try:
        corp_rows = _search("1", "1", name, CORP_COLUMNS)      # 법인 명단 / 법인명
        indiv_rows = _search("2", "3", name, INDIV_COLUMNS)    # 개인 명단 / 상호
    except requests.RequestException as err:
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_PUBLIC,
                               note=f"네트워크 오류: {type(err).__name__}. {MANUAL_NOTE}")
    except StructureChanged as err:
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_PUBLIC,
                               note=f"페이지 구조 변경 추정({err}). {MANUAL_NOTE}")
    except Exception as err:  # lookup 경계 계약: 어떤 오류든 envelope로 강등, 크래시 금지
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_PUBLIC,
                               note=f"예상 외 오류({type(err).__name__}). {MANUAL_NOTE}")

    result = {
        "query_name": name,
        "list_basis": "국세청 고액·상습체납자 명단공개 (국세기본법 제85조의5)",
        "corporate_list": {"searched_by": "법인명",
                           "match_count": len(corp_rows), "matches": corp_rows},
        "individual_list": {"searched_by": "상호",
                            "match_count": len(indiv_rows), "matches": indiv_rows},
        "identity_note": IDENTITY_NOTE,
    }
    return common.envelope(SOURCE, common.STATUS_OK, common.ORIGIN_PUBLIC, result=result)
