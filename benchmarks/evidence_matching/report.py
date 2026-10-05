"""Render the frozen diagnostic report from machine-readable benchmark artifacts."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "test-results/evidence-matching-2026-10-03-v2"


def percent(number):
    return f"{number * 100:.1f}%" if number is not None else "—"


def rank(number):
    return str(number) if number is not None else "—"


def main():
    data = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    stress = json.loads((OUT / "stress.json").read_text(encoding="utf-8"))
    dataset = json.loads((OUT / "dataset.json").read_text(encoding="utf-8"))
    by_case = {case["case_id"]: case for case in dataset["cases"]}
    rows = {(row["case_id"], row["variant"]): row for row in data["rows"]}
    out = ["# Evidence Matching Robustness Benchmark · 2026-10-03",
           "", "> **临时诊断，不是迁移验收。** 31 条主集标签由 agent 暂标，用户表示稍后复核；5 条所谓 holdout 已用于开发测试，不能当独立泛化集。E4 针对同批题型编写，另有冻结后未调参的压力样本暴露 4 条标签误判及 1 条表格取值错误。",
           "", "## 范围与冻结", "",
           "- 中文资料、中文 query；来源为 `AI-Infra-Book.pdf` 与 2027 届推免细则的既有中文 chunk，以及显式标记的 agent 编写受控反例。历史英文 PDF 未进入实验。",
           "- 生产 parser、400/60 chunk、embedding、substring lexical、RRF、CUDA BGE reranker、选证 S6/D1 未改。S8 仅使用既有冻结回放作诊断，未改变生产 evidence limit。",
           "- E0 直接调用当前生产 `assess_evidence`；E1 仅 NFKC 和空白规范化；E2 对绩点指标做核心子短语/阈值绑定并对一般问题增加弱关系词约束；E3 加小型显式表达变体；E4 增加数字、范围、比较、表格、定义、团队规则等不同意图约束。E2/E3 的一般问句仍不充分，实验不代表完整通用实现。",
           "- 规则只读取 query 和 evidence，不读取 gold_label/gold_facts；gold 仅用于评分。冻结 retrieval/rerank trace 未重跑。",
           "", "### 输入哈希", "", "| 输入 | SHA-256 |", "|---|---|",]
    for name, digest in data["input_hashes"].items():
        out.append(f"| {name} | `{digest}` |")
    out.extend(["", "## 规则级结果（agent 暂标，31 条）", "",
                "| 方案 | Support Recall | Precision | FPR | FNR | Partial 准确率 | F1 | 三分类正确 |",
                "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for v in ("E0", "E1", "E2", "E3", "E4"):
        m = data["metrics"][v]["all"]
        out.append(f"| {v} | {percent(m['support_recall'])} | {percent(m['support_precision'])} | {percent(m['false_positive_rate'])} | {percent(m['false_negative_rate'])} | {percent(m['partial_accuracy'])} | {percent(m['support_f1'])} | {percent(m['exact_label_accuracy'])} |")
    out.extend(["", "分母：SUPPORTED 11，NOT_SUPPORTED 14，PARTIAL 6。E0 漏掉 5/11 个完整支持；E1 净救回 1 个（GPA 换行），E2 净再多 1 个（两条 GPA 核心短语受益，但 CSP 公式因弱关系词约束退化），E3 救回全部 11 个正例，却将负例误放行从 6/14 增到 8/14。E4 在同批开发集 31/31，但这不是可靠的离线验收。",
                "", "### 按类别的 E0 → E4（Support TP/FP；样本数）", "",
                "| 类别 | n | E0 TP/FP | E4 TP/FP |", "|---|---:|---:|---:|"])
    for category in data["metrics"]["E0"]["categories"]:
        subset = [r for r in data["rows"] if r["category"] == category and r["variant"] == "E0"]
        def counts(v):
            target = [r for r in data["rows"] if r["category"] == category and r["variant"] == v]
            return (sum(r["gold_label"] == r["predicted_label"] == "SUPPORTED" for r in target),
                    sum(r["gold_label"] == "NOT_SUPPORTED" and r["predicted_label"] == "SUPPORTED" for r in target))
        a, b = counts("E0"), counts("E4")
        out.append(f"| {category} | {len(subset)} | {a[0]}/{a[1]} | {b[0]}/{b[1]} |")
    out.extend(["", "### 逐题标签与判定", "",
                "S=SUPPORTED，P=PARTIAL，N=NOT_SUPPORTED；末列为 E4 reason。完整 query、QueryPlan、原文、出处、gold facts 与各级 matched/constraints 见 `dataset.json` 和 `results.json`。",
                "", "| case_id | 来源 | gold | E0 | E1 | E2 | E3 | E4 | E4 reason |",
                "|---|---|:---:|:---:|:---:|:---:|:---:|:---:|---|"])
    letter = {"SUPPORTED": "S", "PARTIAL": "P", "NOT_SUPPORTED": "N"}
    for case in dataset["cases"]:
        cid = case["case_id"]
        source = ", ".join(f"{m['document_key']} p.{m['page']}" for m in case["evidence_metadata"]) or "受控"
        marks = [letter[rows[(cid, v)]["predicted_label"]] for v in ("E0", "E1", "E2", "E3", "E4")]
        out.append(f"| {cid} | {source} | {letter[case['gold_label']]} | {' | '.join(marks)} | {rows[(cid, 'E4')]['reason']} |")
    out.extend(["", "### 新放行与误放行审计", "",
                "| case | E0 → E3 → E4 | gold | E4 匹配/别名/数字约束 | 结论 |",
                "|---|---|---|---|---|"])
    for case in dataset["cases"]:
        cid = case["case_id"]
        old, e3, new = (rows[(cid, v)] for v in ("E0", "E3", "E4"))
        if old["predicted_label"] != "SUPPORTED" and (e3["predicted_label"] == "SUPPORTED" or new["predicted_label"] == "SUPPORTED"):
            combined = "; ".join([*new["matched"], *new["constraints"]]) or "无"
            failure = "FALSE_SUPPORT" if case["gold_label"] == "NOT_SUPPORTED" and new["predicted_label"] == "SUPPORTED" else ("E3 误放行，E4 阻止" if case["gold_label"] == "NOT_SUPPORTED" and e3["predicted_label"] == "SUPPORTED" else "暂标正确")
            out.append(f"| {cid} | {old['predicted_label']} → {e3['predicted_label']} → {new['predicted_label']} | {case['gold_label']} | {combined} | {failure} |")
    out.extend(["", "## 生产链路冻结回放", "",
                "E0/E4 对同一份 selected/assessment_input 判定。E4 对每条证据单独判定并保留 SUPPORTED 或 PARTIAL；这是新判定器原型的隔离回放，不等于实际接入生产后跨 chunk 合并的行为。13 道可回答题计分；`ai-batch-formula` 原始公式有 parser failure，另列不计。",
                "", "| 选证 | 判定 | Evidence@5 | MRR | 平均 gold coverage | 平均 final chunks | 平均 final tokens |",
                "|---|---|---:|---:|---:|---:|---:|"])
    for arm in ("S6", "S8"):
        for v in ("E0", "E4"):
            m = data["replay"][arm]["metrics"][v]
            out.append(f"| {arm} | {v} | {percent(m['evidence_at_5'])} | {m['mrr']:.3f} | {percent(m['average_gold_fact_coverage'])} | {m['average_answer_chunks']:.2f} | {m['average_answer_tokens']:.1f} |")
    out.extend(["", "### 逐题首次完整证据 rank", "",
                "| query_id | S6 E0→E4 | S8 E0→E4 | S6 final chunks E0→E4 | 诊断 |",
                "|---|---|---|---|---|"])
    ids = [r["query_id"] for r in data["replay"]["S6"]["rows"] if r["variant"] == "E0"]
    for q in ids:
        s6 = {r["variant"]: r for r in data["replay"]["S6"]["rows"] if r["query_id"] == q}
        s8 = {r["variant"]: r for r in data["replay"]["S8"]["rows"] if r["query_id"] == q}
        note = ("公式 parser failure，排除" if q == "ai-batch-formula" else
                "S8 完整证据救回" if q == "policy-gpa" else
                "S6 完整证据救回" if q == "policy-team" else
                "selected 无完整证据" if q == "ai-q20" else
                "rank 前移" if s6["E0"]["rank"] != s6["E4"]["rank"] else "无完整度变化")
        out.append(f"| {q} | {rank(s6['E0']['rank'])}→{rank(s6['E4']['rank'])} | {rank(s8['E0']['rank'])}→{rank(s8['E4']['rank'])} | {s6['E0']['answer_chunks']}→{s6['E4']['answer_chunks']} | {note} |")
    out.extend(["", "S6 由 10/13 → 11/13，MRR 0.615 → 0.769；S8 由 10/13 → 12/13，MRR 0.615 → 0.808。S8 是先前的诊断上限，不能与 S6 一起当单变量的生产改动。原 10 道成功题按 gold fact/rank 无退化；`policy-awards` 保留块 2→3，属于额外上下文成本。`ai-q20` 的正确事实没有进入 S6/S8 selected，本轮判定器无法补救。",
                "", "## 冻结后对抗审计：迁移阻断", "",
                "这 5 条是在 E4 规则写成后新增，未据此调参；仍由 agent 暂标，只作为暴露盲点的压力样本。",
                "", "| 样本 | gold | E4 | 问题 |", "|---|---|---|---|"])
    concern = {"negated-gpa": "原文否定门槛，却被局部比较式放行", "revoked-team": "已废止的旧条款被当现行规则",
               "negated-mqa": "‘并不是’未与共享关系绑定", "negated-definition": "定义被否定，仍判 PARTIAL",
               "table-column-order": "标签虽为 SUPPORTED，但列顺序变动时输出 value=0.06；实际第二等次是 0.05"}
    for row in stress["rows"]:
        out.append(f"| {row['case_id']} | {row['gold_label']} | {row['E4']['predicted_label']} | {concern[row['case_id']]} |")
    out.extend(["", "## 结论与下一步", "",
                "1. 当前主要误拒：连续指标短语与真实 PDF 中的换行/插词不一致，另有‘扣减’↔‘减去’。E0 5 个完整支持被拒；E1 只能净救回 1，E2 净再救回 1，E3 把 recall 提至 11/11 但 FPR 升到 8/14。数值、条件和适用范围需要独立绑定。",
                "2. `policy-team` 在 S6 获救；`policy-gpa` 只在冻结 S8 中有完整 selected，E4 救回。E4 的表面完美分数不可信：同批题型开发且标签待审，冻结后压力测试已发现严重误放行与错列取值。**暂不值得进入生产迁移**。",
                "3. 下一步先请用户复核 `dataset.json` 的 gold_label/reason；再补第二份政策文件、中文技术文档、中文论文的独立题，尤其否定、失效条款、表格列序和跨句范围。优先做 rule refinement 与独立验证；若规则仍无法稳健覆盖，再以 rule-first/model-fallback 的隔离实验研究 NLI，不直接上 LLM judge。",
                "4. 本实验只验证 evidence matching。没有回答生成评测、在线延迟实测或用户使用验证，不能据此宣称端到端中文回答质量提升。生产代码与索引未修改，无构建/重启要求。",
                "", "## 复现", "", "```powershell",
                ".\\.venv\\Scripts\\python.exe -m pytest benchmarks/evidence_matching/test_evidence_matching_rules.py -q",
                ".\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_evidence.py backend/tests/test_query_plan.py -q",
                "# dataset/e0-baseline/results/stress 已冻结；各生成脚本会拒绝覆盖。",
                "```", ""])
    (OUT / "report.md").write_text("\n".join(out), encoding="utf-8")
    print(OUT / "report.md")


if __name__ == "__main__":
    main()
