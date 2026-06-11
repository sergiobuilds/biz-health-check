#!/usr/bin/env python3
"""biz-health-check — 사업자등록번호 1건 실사 사실 조회 리포트.

전부 결정론 python3. LLM 불개입. 점수·등급·해석 라벨 없음 —
조회된 사실 + 출처 + 조회시각만 병렬로 출력한다.

사용:
    python3 scripts/biz_health_check.py <사업자번호> [--name 상호] [--json]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from providers import (common, fsc_corp, localdata_license,  # noqa: E402
                       nps_pension, nts_delinquent, nts_status, pps_sanction)

PRINCIPLE = ("조회된 사실·출처·조회시각만 나열한다. "
             "점수·등급·해석 라벨은 산출하지 않는다 — 판단은 사용자 몫이다.")

PROVIDERS = (
    ("국세청 사업자등록 상태", nts_status),
    ("국민연금 가입 사업장 내역", nps_pension),
    ("국세청 고액·상습체납자 명단공개", nts_delinquent),
    ("금융위 기업기본정보(법인 개요)", fsc_corp),
    ("조달청 부정당업자 제재", pps_sanction),
    ("지방행정 인허가 영업상태(소규모 사업장)", localdata_license),
)


# 사업자번호 없이는 조회 자체가 불가능한 provider (체납·인허가는 상호 기반 가능)
B_NO_REQUIRED = (nts_status, nps_pension, fsc_corp, pps_sanction)


def run(b_no: str | None, name: str | None = None, region: str | None = None,
        industries: list[str] | None = None) -> dict:
    """provider 6종 순차 실행 → 리포트 구조 반환 (출력 형식과 분리)."""
    no = common.normalize_b_no(b_no) if b_no is not None else None
    if no is None and not (name or "").strip():
        raise ValueError("사업자등록번호 또는 --name 상호 중 하나는 필요합니다.")
    sections = []
    for title, module in PROVIDERS:
        try:
            if no is None and module in B_NO_REQUIRED:
                env = common.envelope(getattr(module, "SOURCE", title),
                                      common.STATUS_UNAVAILABLE, common.ORIGIN_PUBLIC,
                                      note="사업자등록번호가 없어 이 항목은 조회할 수 "
                                           "없습니다. 번호를 알면 함께 지정하세요.")
            elif module is localdata_license:
                env = module.lookup(no, name=name, region=region,
                                    industries=industries)
            else:
                env = module.lookup(no, name=name)
        except ValueError:
            raise
        except Exception as err:  # 단일 provider 장애가 리포트 전체를 막지 않게
            env = common.envelope(getattr(module, "SOURCE", title),
                                  common.STATUS_UNAVAILABLE, common.ORIGIN_LIVE,
                                  note=f"provider 내부 오류: {type(err).__name__}")
        sections.append({"section": title, **env})
    return {
        "input": {"b_no": no,
                  "b_no_formatted": common.format_b_no(no) if no else None,
                  "name": name},
        "generated_at": common.now_iso(),
        "principle": PRINCIPLE,
        "providers": sections,
    }


def _render_value(value, indent: int) -> list[str]:
    pad = "  " * indent
    if value is None:
        return [f"{pad}(없음)"]
    if isinstance(value, dict):
        if not value:
            return [f"{pad}(빈 객체)"]
        lines = []
        for key, sub in value.items():
            if isinstance(sub, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.extend(_render_value(sub, indent + 1))
            else:
                lines.append(f"{pad}{key}: {sub if sub not in (None, '') else '(없음)'}")
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{pad}(0건)"]
        lines = []
        for i, sub in enumerate(value, 1):
            lines.append(f"{pad}[{i}]")
            lines.extend(_render_value(sub, indent + 1))
        return lines
    return [f"{pad}{value}"]


def render_text(report: dict) -> str:
    bar = "=" * 70
    name = report["input"]["name"]
    lines = [
        bar,
        "사업자 실사 사실 조회 리포트 — biz-health-check",
        f"대상: {report['input']['b_no_formatted'] or '(사업자번호 미지정)'}"
        + (f" (상호: {name})" if name else " (상호 미지정)"),
        f"생성 시각: {report['generated_at']}",
        f"원칙: {report['principle']}",
        bar,
    ]
    for i, sec in enumerate(report["providers"], 1):
        lines += [
            "",
            f"[{i}] {sec['section']}",
            f"    상태: {sec['status']} / 경로: {sec['origin']}",
            f"    출처: {sec['source']}",
            f"    조회시각: {sec['looked_up_at']}",
        ]
        if sec.get("note"):
            lines.append(f"    안내: {sec['note']}")
        if sec["status"] == common.STATUS_OK:
            lines.append("    사실:")
            lines.extend(_render_value(sec["result"], 3))
    lines += ["", bar,
              "끝. 각 섹션은 해당 출처의 조회시각 기준 사실이며, 섹션 간 종합 판단은 "
              "이 도구가 수행하지 않는다.",
              bar]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="biz_health_check",
        description="사업자등록번호 실사 사실 조회 리포트 (사실·출처·시각만, 해석 없음)")
    parser.add_argument("b_no", nargs="?", default=None,
                        help="사업자등록번호 10자리 (하이픈 허용). 모르면 생략하고 "
                             "--name(+--region)으로 상호 기반 조회")
    parser.add_argument("--name", help="상호·법인명 — 국민연금/체납 명단/금융위 조회에 필요")
    parser.add_argument("--region", help="시군구 (인허가 조회용 — 예: 제주제주시, 서울종로구)")
    parser.add_argument("--industry", action="append", dest="industries",
                        help="인허가 업종 slug (반복 지정 가능 — 기본: 일반음식점·휴게음식점·숙박업)")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run(args.b_no, name=args.name, region=args.region,
                     industries=args.industries)
    except ValueError as err:
        print(json.dumps({"error": str(err)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
