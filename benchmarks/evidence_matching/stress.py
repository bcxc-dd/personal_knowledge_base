"""Post-freeze adversarial smoke audit. Do not tune E4 on these examples."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from benchmarks.evidence_matching.matchers import evaluate

OUT = ROOT / "test-results/evidence-matching-2026-10-03-v2/stress.json"

CASES = [
    ("negated-gpa", "推免的必修课平均学分绩点门槛是多少？",
     "推免必修课程的平均学分绩点不低于3.2是不正确的说法；正式标准尚未公布。", "NOT_SUPPORTED"),
    ("revoked-team", "团队竞赛获奖的成员分值如何扣减？",
     "旧版规定团队成员在分值上减去0.01*(团队排名-1)，最低为0分；这条规则现已废止，新规则另行公布。", "NOT_SUPPORTED"),
    ("negated-mqa", "GQA 和 MQA 的 KV 共享方式有什么区别？",
     "MQA并不是让所有Q头共用一组KV；GQA把Q头分组，每组共享一组KV。", "NOT_SUPPORTED"),
    ("negated-definition", "什么是 AI Infra？它包含哪些主要部分？",
     "AI Infra不是支撑AI训练和推理的基础设施，包括计算设备、存储与互联，以及组织这些资源的软件。", "NOT_SUPPORTED"),
    ("table-column-order", "竞赛等级Ⅱ级甲等的第二等次对应多少分？",
     "竞赛等级 第二等次 第一等次 第三等次\nⅡ级甲等 0.05 0.06 0.04", "SUPPORTED"),
]


def main():
    if OUT.exists():
        raise RuntimeError("Stress audit already frozen")
    rows = []
    for cid, query, evidence, gold in CASES:
        case = {"case_id": cid, "query": query, "evidence_text": evidence, "evidence_metadata": []}
        rows.append({"case_id": cid, "query": query, "evidence_text": evidence,
                     "gold_label": gold, "annotation_status": "agent_provisional_pending_human_review",
                     "E0": evaluate(case, "E0"), "E4": evaluate(case, "E4")})
    OUT.write_text(json.dumps({"status": "POST_FREEZE_NO_TUNING_ADVERSARIAL_AUDIT",
                               "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"n": len(rows), "e4_errors": [r["case_id"] for r in rows if r["gold_label"] != r["E4"]["predicted_label"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
