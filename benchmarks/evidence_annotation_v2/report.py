"""Render migration-blocking audit from frozen v2 annotation and rescoring JSON."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.evidence_annotation_v2.freeze import V2


def pct(value):
    return f"{value * 100:.1f}%"


def main():
    dataset = json.loads((V2 / "dataset-v2.json").read_text(encoding="utf-8"))
    rescored = json.loads((V2 / "rescore-v2.json").read_text(encoding="utf-8"))
    rows = dataset["cases"]
    predictions = {(p["case_id"], p["variant"]): p for p in rescored["predictions"]}
    main_rows = [r for r in rows if r["origin"] == "main"]
    stress_rows = [r for r in rows if r["origin"] == "stress"]
    changed = [r for r in main_rows if r["label_changed_from_v1"]]
    removed = [r for r in main_rows if r["review_status"] == "REMOVE_FROM_MAIN_SET"]
    out = ["# Evidence Benchmark Annotation v2：迁移阻断报告", "",
           "> **待人工确认。** 本次 36 条 v2 标注由 agent 依照用户明确的语义建议逐条提出，`human_review_state=PENDING`。这里的 `CONFIRMED` 只表示建议保持原判，绝不代表用户已复核。全部样本仍是 DEV/诊断；没有独立 `TEST_FROZEN`。本报告不能授权生产 matcher 迁移。",
           "", "## 1. v1 冻结与新口径", "",
           "v1 `dataset.json`、`results.json`、`stress.json`、`report.md`、`e0-baseline.json` 的 SHA-256 和大小保存在 `v1-freeze.json`，原文件没有被改写。旧目录名 `evidence-matching-2026-10-03-v2` 中的末尾 v2 是当时运行目录版本；其 `dataset.json` 的内部 schema 仍是 `evidence-matching-v1`。新目录的内部 schema 才是 `evidence-matching-v2`。旧 E0–E4 指标统一标为 **v1 annotation schema 下的历史诊断**。",
           "", "v1 最大的问题是把两件事压进一个 SUPPORTED/PARTIAL/NOT_SUPPORTED 标签：证据能否回答用户的信息需求，以及证据是否支持 query 中的命题或与已核原文一致。YES/NO 题有依据地回答‘否’也是 FULL；WH 题只排除错误值却不给真值仍是 NONE。结构化取值另评分，不能靠 FULL 标签掩盖错值。详见 `docs/evaluations/evidence-annotation-v2-schema.md`。",
           "", "## 2. 逐题复核结果", "",
           f"- 主集 31 条中 **{len(changed)} 条需改变三分类结论**：{', '.join(r['case_id'] for r in changed)}。",
           f"- 其中 **{len(removed)} 条从普通充分度主指标移出**：{', '.join(r['case_id'] for r in removed)}。它们的受控证据与已核原文冲突，适合来源风险诊断。主指标剩 27 条。",
           "- 其余 25 条主集的粗标签可保留，但 v1 无法表达 YES/NO 极性、指标/范围绑定、缺失事实或表格单元格取值；这些属于 schema 表达能力不足，不等于 25 条都已获独立人工确认。",
           "- 5 条 stress 中 `negated-mqa`、`negated-definition` 从旧 NONE 改为 PARTIAL；`table-column-order` 保持 FULL，但要求值 0.05。",
           "", "| case_id | 旧 gold → v2 | relation / risk | required:covered | review_status | E4 v2 判定 | 值核验 |",
           "|---|---|---|---:|---|---|---|"]
    for row in rows:
        p = predictions[(row["case_id"], "E4")]
        relation = row["relation_status"] + (" + " + ",".join(row["risk_flags"]) if row["risk_flags"] else "")
        value = "正确" if p["fact_extraction_correct"] is True else "错误" if p["fact_extraction_correct"] is False else "不可判"
        out.append(f"| {row['case_id']} | {row['old_gold_label']} → {row['answerability']} | {relation} | {len(row['required_facts'])}:{len(row['covered_facts'])} | {row['review_status']} | {p['predicted_answerability']} | {value} |")
    out.extend(["", "`dataset-v2.json` 对每条保留 query、全文 evidence、旧 gold、query_type、required/covered/missing facts、结构化 expected_facts、expected_answer、relation、review_reason 与来源。所有 `review_status` 均为 agent 建议，需用户最终确认。",
                "", "## 3. E0–E4 按 v2 重算", "",
                "旧 status 仅作 `SUPPORTED→FULL`、`PARTIAL→PARTIAL`、`NOT_SUPPORTED→NONE` 的历史输出映射；没有改 matcher。主集 E0–E4 和 stress E0/E4 用 v1 冻结输出；stress E1–E3 用同一哈希的未修改 matcher 事后计算，单列 provenance。",
                "", "| 数据口径 | E0 accuracy / macro F1 | E1 | E2 | E3 | E4 |",
                "|---|---:|---:|---:|---:|---:|"])
    for subset in ("former_main_31", "primary_dev_27", "stress_diagnostic_5", "all_dev_36"):
        c = rescored["metrics"][subset]["classification"]
        cells = [f"{pct(c[v]['accuracy'])} / {c[v]['macro_f1']:.3f}" for v in ("E0", "E1", "E2", "E3", "E4")]
        out.append(f"| {subset} | {' | '.join(cells)} |")
    out.extend(["", "v1 主集 E4 为 31/31；v2 主集 E4 为 **25/31**，只计普通主指标为 **25/27**，stress 为 **2/5**，全部 DEV 为 **27/36**。E4 在 v2 下仍高于 E0 的分类分数，但这一优势只来自同源开发资料，不代表泛化。E4 的原‘100%’不再成立。",
                "", "### 主集每类召回与混淆矩阵", "",
                "| 方案 | FULL | PARTIAL | NONE | macro F1 |",
                "|---|---:|---:|---:|---:|"])
    for v in ("E0", "E1", "E2", "E3", "E4"):
        m = rescored["metrics"]["former_main_31"]["classification"][v]
        cells = [f"{m['by_class'][c]['correct']}/{m['by_class'][c]['gold_n']}" for c in ("FULL", "PARTIAL", "NONE")]
        out.append(f"| {v} | {' | '.join(cells)} | {m['macro_f1']:.3f} |")
    out.extend(["", "E4 主集混淆矩阵（行 gold，列预测）：", "",
                "| gold \\ pred | FULL | PARTIAL | NONE |", "|---|---:|---:|---:|"])
    confusion = rescored["metrics"]["former_main_31"]["classification"]["E4"]["confusion"]
    for gold in ("FULL", "PARTIAL", "NONE"):
        out.append(f"| {gold} | {confusion[gold]['FULL']} | {confusion[gold]['PARTIAL']} | {confusion[gold]['NONE']} |")
    gold_cov = rescored["metrics"]["all_dev_36"]["gold_fact_coverage"]
    full_count = sum(r["answerability"] == "FULL" for r in rows)
    out.extend(["", "## 4. Fact coverage 与结构化正确性", "",
                f"v2 gold 把 required/covered/missing 完整分开；36 条共 {gold_cov['required_slots']} 个所需槽位，证据覆盖 {gold_cov['covered_slots']} 个，gold 层面的 full case {full_count}/36。**这描述题集，不是 matcher 的事实召回率。** v1 判定结果没有普遍的逐事实预测或最终回答，无法诚实计算全量 required fact recall、covered fact precision、full fact coverage rate；相应字段在机器结果中标为不可识别。",
                "", "只能审计旧 `matched/constraints` 中明确暴露的诊断值；未暴露的字段不从 gold 反填。全部 36 条 E4：",
                "", "| 可观察子项 | 结果 | 限制 |", "|---|---:|---|"])
    sd = rescored["metrics"]["all_dev_36"]["structured_diagnostic"]["E4"]
    num, op, table, rel, scope, factcov = (sd[k] for k in ("numeric_value", "operator", "table_cell", "relation", "scope", "observable_fact_coverage"))
    out.extend([f"| 数字值 | {num['correct']}/{num['observed']} 已输出；输出覆盖 {num['observed']}/{num['gold_slots']} 槽位 | 不含未输出的 CSP g_i 值 |",
                f"| 比较符 | {op['correct']}/{op['observed']} 已输出；输出覆盖 {op['observed']}/{op['gold_slots']} | 只核对 GPA 数值门槛诊断，YES/NO 否定回答另评 |",
                f"| 表格单元格 | {table['correct']}/{table['observed']} | `table-column-order`：E4 值 0.06，gold 为 0.05；FULL 标签无法遮掩 |",
                f"| 关系事实 | 正确 {rel['correct_gold_slots']}/{rel['emitted']} 已输出；gold 覆盖 {rel['correct_gold_slots']}/{rel['gold_slots']} | `negated-mqa` 多报一侧，swapped 源关系未通过 |",
                f"| 范围 | 明确规范化输出 {scope['observed_explicit_scope']}/{scope['gold_slots']} | 不能据分类命中宣称范围值正确 |",
                f"| 可观察事实 precision / recall | {pct(factcov['precision'])} / {pct(factcov['recall'])} | 只覆盖数字与关系诊断，非全量事实指标 |"])
    out.extend(["", "`rescore-v2.json` 对每个预测保存 `fact_extraction_correct` 与逐 fact 的 expected/observed/correct；`null` 表示历史输出不足以判断。表格错值明确为 `false`。",
                "", "## 5. Stress 复标与失败层", "",
                "| case | v2 answerability | E4 分类 | 失败归因 |",
                "|---|---|---|---|"])
    stress_notes = {
        "negated-gpa": "NEGATED：只排除3.2，没有真实门槛；E4 将否定句当正向门槛。",
        "revoked-team": "STALE_OR_REVOKED：旧规则废止且新规则未公布；E4 放行旧条款。",
        "negated-mqa": "NEGATED + SOURCE_CONTRADICTS_CANONICAL：GQA一侧可答，MQA真实关系缺失；E4 判 FULL。",
        "negated-definition": "NEGATED：组成部分可答，定义被否定；E4 PARTIAL 分类正确。",
        "table-column-order": "STRUCTURED_EXTRACTION：FULL 分类正确，但把第一等次0.06误当第二等次，正确值0.05。",
    }
    for row in stress_rows:
        p = predictions[(row["case_id"], "E4")]
        out.append(f"| {row['case_id']} | {row['answerability']} | {p['predicted_answerability']} | {stress_notes[row['case_id']]} |")
    negation = [r for r in rows if r["relation_status"] in {"NEGATED", "CONTRADICTS_QUERY_PROPOSITION"}]
    neg_ok = sum(predictions[(r["case_id"], "E4")]["predicted_answerability"] == r["answerability"] for r in negation)
    out.extend(["", f"否定/命题冲突相关 7 条，E4 分类仅 **{neg_ok}/7**；失效规则 0/1；错范围负例 1/1 分类正确，但 E4 没有显式输出范围值。条件值类中 `csp-no-output` 应为 NONE，E4 仍给 PARTIAL。来源与标准原文冲突的 4 条主集不再混入普通充分度主指标。",
                "", "## 6. 结论与下一步", "",
                "1. **不迁移生产 matcher。** v2 解释了旧‘false positive/false negative’中有 6 条主集属于标签语义变更；E4 的满分消失，且否定、旧规则和错列仍是实质失败。没有用户完成的人工签核或独立测试集。",
                "2. **当前数据足以继续诊断，不足以作为 matcher 开发的最终验收。** 用户需先复核 `dataset-v2.json` 的 answerability、expected_facts、review_reason 与移出主指标的 4 条；必要时修订为 v2.1 新文件，并记录变更历史。",
                "3. **可以开始收集真正 TEST_FROZEN，但现在没有 TEST_FROZEN 分数。** 优先第二份政策/规范、中文技术文档、中文论文和表格资料；先独立人工定 gold、冻结来源与规则哈希，再运行 E0–E4。若根据结果调规则，该批样本转 DEV。",
                "4. 后续如需比较 value-level correctness，matcher 或回答链路必须显式输出数值、操作符、范围、行列、关系和 YES/NO 极性。本轮只重构标注与重算旧输出，不添加 E5、修规则、改生产或重建索引。",
                "", "## 复现与边界", "",
                "`benchmarks/evidence_annotation_v2/` 的 freeze/build/score/report 按顺序生成产物，并拒绝覆盖已有 v2 数据。`v1-freeze.json` 保存原五份 SHA-256；`rescore-v2.json` 保存每条历史输出及 provenance。所有标注来自现有两份中文 PDF 或 agent 编写反例；历史英文论文未参与。未评估生成答案或真人使用，不需构建、重启或重建索引。", ""])
    (V2 / "report.md").write_text("\n".join(out), encoding="utf-8")
    print(V2 / "report.md")


if __name__ == "__main__":
    main()
