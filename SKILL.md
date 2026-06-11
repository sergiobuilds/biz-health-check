---
name: biz-health-check
description: 사업자등록번호 하나로 "이 사업자, 실제 문제 없나"를 확인한다 — 국세청 휴폐업·국민연금 가입 사업장·국세 체납 공개명단·금융위 법인개요·조달청 부정당제재·지방행정 인허가 영업상태(동네 사업장)를 무료 공공 데이터로 교차 조회해 사실만 병렬하는 실사 리포트.
license: MIT
metadata:
  category: business
  locale: ko-KR
  phase: v1
---

# 사업자 실사 사실 조회 (biz-health-check)

## What this skill does

사업자등록번호(+상호 선택)를 입력하면 무료 공공 데이터 6종을 교차 조회해 실사 리포트 한 장을 만든다.

1. 국세청 사업자등록 상태 — 계속/휴업/폐업, 과세유형, 폐업일 (data.go.kr 15081808)
2. 국민연금 가입 사업장 내역 — 가입자수·당월 고지금액·월별 취득/상실 (data.go.kr 3046071, V2). 직원 규모와 그 추이가 보인다
3. 국세청 고액·상습체납자 명단공개 대조 — 누리집 공개 검색 (무인증)
4. 금융위 기업기본정보 — 법인 개요: 대표자·설립일·업종 (data.go.kr 15043184)
5. 조달청 나라장터 부정당제재업체정보 — 조회시점 현재 유효한 제재의 기간·제재기관·근거법률 (data.go.kr 15129466, 사업자등록번호 정확 일치 조회). 만료·해제 건과 나라장터 미등록업체·개인 제재는 미제공
6. 지방행정 인허가 영업상태 — 동네 사업장(식당·카페·숙박·미용실·약국·학원 등 **인허가 업종 208종 전체**)의 영업/휴업/폐업, 인허가일자(업력), 폐업일자, 업태, 주소 (LOCALDATA file.localdata.go.kr, 무인증). `--region 시군구` 지정 필요, 업종은 한글명("약국", "숙박업")으로 지정 가능

공시 유무는 기존 `k-dart` 스킬을 함께 쓰면 된다.

## Design principles

- **점수·등급·"위험" 같은 해석 라벨을 산출하지 않는다.** 조회된 사실 + 출처 + 조회시각만 병렬한다. 판단은 사용자 몫이다.
- 모든 provider는 실패 시 크래시 대신 `unavailable`/`needs-key`로 강등하고 수동 확인 경로를 안내한다.
- 결정론 python3 — LLM 불개입.

## When to use

- "이 사업자(거래처/의뢰인) 실제 문제 없는지 확인해줘"
- "○○○-○○-○○○○○ 살아있는 회사야? 직원은 좀 있어?"
- "이 회사 체납이나 입찰 제재 이력 있어?"
- "제주시 ○○호텔(동네 가게) 지금 영업 중이야? 오래된 곳이야?" — 사업자번호를 몰라도 상호+시군구로 조회 가능

## Prerequisites

- `python3`, `requests`
- 인터넷 연결

## Credential requirements

- `DATA_GO_KR_KEY` — 공공데이터포털 일반 인증키 (BYO). 없으면 키 필요 항목은 `needs-key`로 표기되고 무인증 항목(체납 명단)만 동작한다.
- 키 계정에서 다음 활용신청이 돼 있어야 해당 항목이 live로 동작한다 (전부 자동승인·무료):
  - 국세청 사업자등록 상태조회: https://www.data.go.kr/data/15081808/openapi.do
  - 국민연금 가입 사업장 내역: https://www.data.go.kr/data/3046071/openapi.do
  - 금융위 기업기본정보: https://www.data.go.kr/data/15043184/openapi.do
  - 조달청 나라장터 사용자정보 서비스 (부정당제재업체정보조회 포함): https://www.data.go.kr/data/15129466/openapi.do
- 키를 코드·로그·리포트에 평문으로 남기지 않는다.

## Usage

```bash
DATA_GO_KR_KEY=<인증키> python3 scripts/biz_health_check.py 124-81-00998 --name 삼성전자
python3 scripts/biz_health_check.py 1248100998 --json   # JSON 출력
# 동네 사업장(인허가 업종 208종): 지역 지정 — 기본 검색 업종은 일반음식점·휴게음식점·숙박업
python3 scripts/biz_health_check.py 123-45-67890 --name 호텔샬롬 --region 제주제주시 --industry 숙박업
# 사업자번호를 모르면 생략 가능 — 상호 기반 항목(체납·인허가)만 조회된다
python3 scripts/biz_health_check.py --name 호텔샬롬 --region 제주제주시 --industry 숙박업
```

## Privacy boundary

- 입력한 사업자번호·상호는 공공데이터포털·국세청 누리집 upstream으로 전송된다.
- 국민연금 데이터는 사업자번호 앞 6자리만 공개되므로, 6자리 일치 + 상호 유사 후보를 나열할 뿐 사업장 동일성을 단정하지 않는다.
- 체납 명단공개 자료에는 사업자등록번호가 수록되지 않아 상호·법인명 문자열 일치의 공개 사실만 나열한다 (동명 상호 가능성은 사용자 판단).
- 인허가(LOCALDATA) 자료에도 사업자등록번호가 수록되지 않아 같은 방식의 상호 매칭이다. 자료는 매일 갱신, 2일 전 기준 현행화.

## Official surfaces

- 국세청 상태조회: `POST https://api.odcloud.kr/api/nts-businessman/v1/status`
- 국민연금 가입 사업장: `https://apis.data.go.kr/B552015/NpsBplcInfoInqireServiceV2` (요청 파라미터 camelCase)
- 체납 명단공개 검색: `https://www.nts.go.kr/nts/ad/openInfo/selectList.do`
- 금융위 기업기본정보: `https://apis.data.go.kr/1160100/GetCorpBasicInfoService_V2/getCorpOutline_V2`
- 부정당제재업체정보: `https://apis.data.go.kr/1230000/ao/UsrInfoService02/getUnptRsttCorpInfo02` (수동 대조: 나라장터 `https://www.g2b.go.kr`)
- 인허가 영업상태: `https://file.localdata.go.kr/file/download/<업종slug>/info?orgCode=<지자체코드>` (무인증, Referer 필요, CP949 CSV)
