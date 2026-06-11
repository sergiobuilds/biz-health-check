"""지방행정 인허가(LOCALDATA) 영업상태 provider — file.localdata.go.kr 지역별 CSV.

스펙 실확인 (2026-06-11, 전부 무인증 직호출로 재현):

- 다운로드: GET https://file.localdata.go.kr/file/download/<업종slug>/info?orgCode=<지자체코드>
  (Referer 헤더 필요 — 없으면 302 → /error.html. 응답은 CSV(CP949).)
- 업종 slug ↔ 한글명은 각 업종 landing 페이지(/file/<slug>/info)에서 검증한
  16종만 등록 (전체 208종 존재 — 필요 시 같은 패턴으로 추가).
- 지자체 orgCode 245종은 landing 페이지 select 옵션에서 추출
  (localdata_orgcodes.json). "서울종로구", "제주제주시" 같은 표기.
- 컬럼(실측): 개방자치단체코드, 관리번호, 인허가일자, 영업상태명, 폐업일자,
  소재지면적, 사업장명, 업태구분명, 도로명주소, 지번주소, 상세영업상태명,
  데이터갱신시점, 남/여종사자수 등.
- **사업자등록번호는 수록되지 않는다** → 상호(사업장명) 문자열 매칭만 가능,
  입력 사업자번호와의 동일성은 단정 불가 (체납 명단과 같은 identity_note 방식).
- 자료는 "매일 갱신, 2일 전 기준 현행화" (landing 페이지 고지).
- 본체(www.localdata.go.kr)가 죽어 있어도 파일 서버는 별도로 살아 있음을 실측.

지역(region)이 필요한 이유: 전국 통파일은 업종당 수백 MB(일반음식점 692MB)라
단건 조회에 부적합 — 시군구 단위 파일(수백 KB~수 MB)을 받아 로컬 캐시한다.
"""

from __future__ import annotations

import csv
import io
import json
import pathlib
import time

import requests

from . import common

BASE = "https://file.localdata.go.kr"
LANDING = f"{BASE}/file/general_restaurants/info"
SOURCE = ("지방행정 인허가데이터(LOCALDATA) 업종별 영업상태 — 행정안전부 "
          "(file.localdata.go.kr 지역별 CSV, 매일 갱신·2일 전 기준 현행화)")
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "Chrome/126.0 Safari/537.36",
           "Referer": LANDING}

# 업종 slug ↔ 한글명 208종 전수 — 2026-06-11 각 업종 landing 페이지에서
# 실측 수집(208/208, 실패 0)해 동결 (localdata_industries.json)
_INDUSTRIES_PATH = pathlib.Path(__file__).with_name("localdata_industries.json")
INDUSTRIES: dict = json.loads(_INDUSTRIES_PATH.read_text(encoding="utf-8"))
DEFAULT_INDUSTRIES = ("general_restaurants", "rest_cafes", "lodgings")


def resolve_industry(token: str) -> tuple[str | None, list[str]]:
    """업종 지정 해석 — slug 정확 일치 또는 한글명 부분 일치.

    반환: (slug, 후보 한글명들). 다중/0건 매치면 slug는 None.
    """
    token = token.strip()
    if token in INDUSTRIES:
        return token, [INDUSTRIES[token]]
    squeezed = token.replace(" ", "")
    # 1순위: 한글명 정확 일치 — 카테고리 접두("식품_" 등) 제거형 포함
    exact = [(slug, nm) for slug, nm in INDUSTRIES.items()
             if nm.replace(" ", "") == squeezed
             or nm.split("_", 1)[-1].replace(" ", "") == squeezed]
    if len(exact) == 1:
        return exact[0][0], [exact[0][1]]
    # 2순위: 부분 일치 단일
    hits = exact or [(slug, nm) for slug, nm in INDUSTRIES.items()
                     if squeezed in nm.replace(" ", "")]
    if len(hits) == 1:
        return hits[0][0], [hits[0][1]]
    return None, [nm for _, nm in hits]

# 결과에 담을 핵심 컬럼 (CSV 원문 컬럼명 그대로)
RESULT_COLUMNS = ("사업장명", "영업상태명", "상세영업상태명", "인허가일자", "폐업일자",
                  "업태구분명", "도로명주소", "지번주소", "데이터갱신시점")

CACHE_DIR = pathlib.Path.home() / ".cache" / "biz-health-check" / "localdata"
CACHE_TTL_SECONDS = 24 * 3600  # 원천이 일 단위 갱신이므로 1일 캐시

IDENTITY_NOTE = ("인허가 자료에는 사업자등록번호가 수록되지 않아 입력 사업자번호와의 "
                 "동일성은 확인할 수 없다 — 상호(사업장명) 문자열 일치 후보의 사실만 "
                 "나열하며, 동명 상호 가능성은 사용자가 판단한다. 자료는 매일 갱신되며 "
                 "2일 전 기준으로 현행화된다.")

_ORG_CODES_PATH = pathlib.Path(__file__).with_name("localdata_orgcodes.json")


def org_codes() -> dict:
    """지자체명 → orgCode 245종 (landing 페이지 select에서 추출·동결)."""
    return json.loads(_ORG_CODES_PATH.read_text(encoding="utf-8"))


def _resolve_region(region: str) -> tuple[str | None, list[str]]:
    """지역 표기 → orgCode. (코드, 후보명들) — 다중/0건 매치면 코드는 None."""
    table = org_codes()
    region = region.strip()
    if region in table:
        return table[region], [region]
    squeezed = region.replace(" ", "")
    hits = [nm for nm in table if squeezed in nm.replace(" ", "")]
    if len(hits) == 1:
        return table[hits[0]], hits
    return None, hits


def _fetch_csv(slug: str, org_code: str) -> str:
    """업종×지역 CSV를 받아 캐시(1일 TTL) 후 텍스트 반환."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{slug}_{org_code}.csv"
    if cache.exists() and time.time() - cache.stat().st_mtime < CACHE_TTL_SECONDS:
        return cache.read_text(encoding="utf-8")
    resp = requests.get(f"{BASE}/file/download/{slug}/info",
                        params={"orgCode": org_code}, headers=HEADERS, timeout=120)
    if resp.status_code != 200 or "csv" not in (resp.headers.get("Content-Type") or ""):
        raise RuntimeError(f"HTTP {resp.status_code} "
                           f"({resp.headers.get('Content-Type', '?')})")
    text = resp.content.decode("cp949", errors="replace")
    cache.write_text(text, encoding="utf-8")
    return text


def _search_rows(csv_text: str, name: str) -> list[dict]:
    """사업장명 부분 일치(공백 무시) 행을 핵심 컬럼만 추려 반환."""
    needle = name.replace(" ", "")
    out = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        biz_name = (row.get("사업장명") or "").strip()
        if needle and needle in biz_name.replace(" ", ""):
            out.append({col: (row.get(col) or "").strip() for col in RESULT_COLUMNS})
    return out


def lookup(b_no: str, name: str | None = None, region: str | None = None,
           industries: list[str] | None = None) -> dict:
    """인허가 영업상태 조회 — 상호+지역 필수 (자료에 사업자번호 없음, b_no 생략 가능)."""
    if b_no is not None:
        common.normalize_b_no(b_no)  # 입력 검증만
    if not (name or "").strip():
        return common.envelope(
            SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_PUBLIC,
            note="인허가 자료에 사업자등록번호가 수록되지 않아 상호 없이 검색할 수 "
                 "없습니다. --name 으로 상호를 지정하세요.")
    if not (region or "").strip():
        return common.envelope(
            SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_PUBLIC,
            note="전국 통파일이 업종당 수백 MB라 시군구 지역 지정이 필요합니다. "
                 "--region 으로 지정하세요 (예: 제주제주시, 서울종로구, 경기수원시).")
    name = name.strip()

    code, hits = _resolve_region(region)
    if code is None:
        return common.envelope(
            SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_PUBLIC,
            note=(f"지역 '{region}' 특정 실패 — "
                  + (f"후보 {len(hits)}곳: {', '.join(hits[:8])}. 하나로 지정하세요."
                     if hits else "등록 지자체명과 일치하지 않습니다 (예: 서울종로구).")))

    selected, bad = [], []
    for token in (industries or DEFAULT_INDUSTRIES):
        slug, cand = resolve_industry(token)
        if slug:
            selected.append(slug)
        else:
            bad.append(f"'{token}'"
                       + (f" (후보 {len(cand)}종: {', '.join(cand[:6])})" if cand
                          else " (일치 업종 없음)"))
    if bad:
        return common.envelope(
            SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_PUBLIC,
            note=(f"업종 특정 실패: {'; '.join(bad)}. slug 또는 한글명(예: 약국, "
                  "일반음식점, 숙박업)으로 하나씩 지정하세요. 총 208종 지원."))

    searched, failures = {}, []
    try:
        for slug in selected:
            try:
                rows = _search_rows(_fetch_csv(slug, code), name)
                searched[slug] = {"industry": INDUSTRIES[slug],
                                  "match_count": len(rows), "matches": rows}
            except (requests.RequestException, RuntimeError) as err:
                failures.append(f"{INDUSTRIES[slug]}({type(err).__name__})")
    except Exception as err:  # lookup 경계 계약: 어떤 오류든 envelope로 강등
        return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_PUBLIC,
                               note=f"예상 외 오류({type(err).__name__}).")

    if not searched:
        return common.envelope(
            SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_PUBLIC,
            note=f"전 업종 다운로드 실패: {', '.join(failures)}. "
                 f"수동 확인: https://www.localdata.go.kr")

    result = {
        "query": {"name": name, "region": hits[0], "org_code": code},
        "industries_searched": searched,
        "total_match_count": sum(v["match_count"] for v in searched.values()),
        "identity_note": IDENTITY_NOTE,
    }
    note = (f"일부 업종 다운로드 실패: {', '.join(failures)}" if failures else None)
    return common.envelope(SOURCE, common.STATUS_OK, common.ORIGIN_PUBLIC,
                           result=result, note=note)
