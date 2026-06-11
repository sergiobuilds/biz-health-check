"""조달청 부정당업자 제재 provider — v2 예정 stub (자동 조회 미구현).

스펙 실확인 결과 (2026-06-11, docs/BUILD-NOTES.md):

- 사업자번호·업체명으로 질의 가능한 **전용 OpenAPI 명세를 특정하지 못했다.**
  확인된 것은 파일데이터 '조달청_나라장터 부정당제재 내역'
  (https://www.data.go.kr/data/15137996/fileData.do, 수시 갱신)이며,
  게시된 컬럼 목록에서 사업자등록번호 포함 여부를 확인하지 못했다.
- 추측으로 구현하지 않고(날조 금지) status="unavailable" + 수동 확인 경로를
  안내하는 stub으로 둔다. 질의형 명세가 확정되면 v2에서 구현한다.
"""

from __future__ import annotations

from . import common

SOURCE = ("조달청 나라장터 부정당업자 제재 — 자동 조회 미구현(v2 예정), "
          "근거: data.go.kr 15137996 파일데이터")
STUB_NOTE = (
    "부정당업자 제재를 사업자번호·업체명으로 질의할 수 있는 전용 OpenAPI 명세를 "
    "특정하지 못해 자동 조회를 구현하지 않았습니다(v2 예정). 확인된 공공데이터는 "
    "파일데이터 '조달청_나라장터 부정당제재 내역' "
    "https://www.data.go.kr/data/15137996/fileData.do (수시 갱신) 입니다. "
    "수동 확인: 나라장터 https://www.g2b.go.kr 에서 부정당업자 제재 검색."
)


def lookup(b_no: str, name: str | None = None) -> dict:
    """stub — 네트워크 호출 없이 미구현 사실과 수동 확인 경로만 반환."""
    common.normalize_b_no(b_no)  # 입력 검증은 동일하게 수행
    return common.envelope(SOURCE, common.STATUS_UNAVAILABLE, common.ORIGIN_PUBLIC,
                           note=STUB_NOTE)
