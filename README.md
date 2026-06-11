# biz-health-check

사업자등록번호 하나로 "이 사업자, 실제 문제 없나"를 확인하는 실사 사실 조회 스킬.
k-skill(NomaDamas/k-skill) 기여용으로 개발 중 — 스킬 본체는 `SKILL.md`, 구현은 `scripts/`.

## 핵심 원칙

점수·등급·해석 라벨 없음. 조회된 사실 + 출처 + 조회시각만 병렬. 실패는 크래시 대신 `unavailable`/`needs-key` 강등.

## 빠른 실행

```bash
DATA_GO_KR_KEY=<공공데이터포털 키> python3 scripts/biz_health_check.py 124-81-00998 --name 삼성전자
python3 -m pytest tests/ -q   # 오프라인 단위 테스트 (네트워크 차단)
```

## provider 현황 (2026-06-11 실측)

| provider | 상태 |
|---|---|
| 국세청 상태조회 | **live 검증 완료** (계속사업자 응답 확인) |
| 체납 명단공개 검색 | **live 검증 완료** (무인증, 법인·개인 명단 0건 매치 정상) |
| 국민연금 가입 사업장 | 구현 완료 — 키 활용신청 후 live 검증 필요 (현재 upstream 500) |
| 금융위 기업기본정보 | 구현 완료 — 키 활용신청 대기 (403 → needs-key 강등 정상) |
| 조달청 부정당제재 내역 | 구현 완료 — fileData odcloud API(15137996, 사업자번호 수록·정확 일치). 키 활용신청 대기 (401 → needs-key 강등 정상) |

## k-skill 기여 메모

- 1차 PR은 BYO 키(`DATA_GO_KR_KEY`)로만. proxy route(연금·금융위)는 운영자 협의 후 후속 분리.
- 합본 vs 단품 분리, 네이밍은 운영자 회신 반영 예정.
