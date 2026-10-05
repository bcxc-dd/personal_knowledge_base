"""Re-score historical E0-E4 decisions under v2 gold without changing rules."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from benchmarks.evidence_annotation_v2.build import verify_v1_freeze
from benchmarks.evidence_annotation_v2.freeze import V1, V2, sha
from benchmarks.evidence_matching.matchers import evaluate

LABEL_MAP = {"SUPPORTED": "FULL", "PARTIAL": "PARTIAL", "NOT_SUPPORTED": "NONE"}
CLASSES = ("FULL", "PARTIAL", "NONE")
VARIANTS = ("E0", "E1", "E2", "E3", "E4")


def classification(gold_rows, predictions):
    return {
        variant: classification_one(gold_rows, predictions, variant)
        for variant in VARIANTS
    }


def classification_one(gold_rows, predictions, variant):
    pairs = [(r["answerability"], predictions[(r["case_id"], variant)]["predicted_answerability"])
             for r in gold_rows]
    confusion = {gold: {pred: sum(g == gold and p == pred for g, p in pairs) for pred in CLASSES}
                 for gold in CLASSES}
    by_class = {}
    for label in CLASSES:
        tp = confusion[label][label]
        gold_n = sum(g == label for g, _ in pairs)
        pred_n = sum(p == label for _, p in pairs)
        precision = tp / pred_n if pred_n else 0.0
        recall = tp / gold_n if gold_n else 0.0
        by_class[label] = {"gold_n": gold_n, "predicted_n": pred_n, "correct": tp,
                           "precision": precision, "recall": recall,
                           "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}
    return {"n": len(pairs), "accuracy": sum(g == p for g, p in pairs) / len(pairs) if pairs else 0,
            "macro_f1": sum(by_class[c]["f1"] for c in CLASSES) / 3,
            "by_class": by_class, "confusion": confusion}


def gold_fact_coverage(rows):
    required = sum(len(r["required_facts"]) for r in rows)
    covered = sum(len(r["covered_facts"]) for r in rows)
    return {"required_slots": required, "covered_slots": covered,
            "covered_over_required": covered / required if required else 0,
            "full_case_coverage_rate": sum(r["answerability"] == "FULL" for r in rows) / len(rows) if rows else 0,
            "note": "Gold evidence composition, not matcher fact recall. Historical outputs lack universal per-fact predictions."}


def structured_observations(record, decision):
    """Read only explicit diagnostic fields; never copy values from gold."""
    text = " | ".join([*decision.get("matched", []), *decision.get("constraints", [])])
    observations = {}
    ids = {f["fact_id"] for f in record["required_facts"]}
    if "team_formula" in ids:
        m = re.search(r"(0\.\d+)\s*[×*]", text)
        if m:
            observations["team_formula"] = {"factor": float(m.group(1))}
    if "team_floor" in ids:
        m = re.search(r"最低\s*(\d+(?:\.\d+)?)\s*分", text)
        if m:
            observations["team_floor"] = {"value": float(m.group(1))}
    if "gpa_threshold" in ids:
        m = re.search(r"(大于等于|不低于|至少|≥|>=|低于|<)\s*(\d+(?:\.\d+)?)", text)
        if m:
            op = ">=" if m.group(1) in {"大于等于", "不低于", "至少", "≥", ">="} else "<"
            observations["gpa_threshold"] = {"operator": op, "value": float(m.group(2))}
    if "table_cell" in ids:
        m = re.search(r"value=(\d+(?:\.\d+)?)", text)
        if m:
            observations["table_cell"] = {"value": float(m.group(1)),
                                           "row": "Ⅱ级甲等" if "Ⅱ级甲等" in text else None,
                                           "column": "第二等次" if "第二等次" in text else None}
    if "gqa_sharing" in ids and "GQA分组共享KV" in text:
        observations["gqa_sharing"] = {"object": "每组Q头共享一组KV"}
    if "mqa_sharing" in ids and "MQA所有Q共享一组KV" in text:
        observations["mqa_sharing"] = {"object": "所有Q头共享一组KV"}
    if "prefill_action" in ids and "预填充处理输入" in text:
        observations["prefill_action"] = {"relation": "处理输入"}
    if "decode_action" in ids and "解码逐步生成" in text:
        observations["decode_action"] = {"relation": "逐步生成新token"}
    return observations


def fact_comparison(record, decision):
    """Compare observable diagnostic facts; None means the old output is silent."""
    observed = structured_observations(record, decision)
    comparisons = []
    for expected in record["expected_facts"]:
        fid = expected["fact_id"]
        found = observed.get(fid)
        if found is None:
            verdict = None
        elif fid == "table_cell":
            verdict = (found.get("row"), found.get("column"), found.get("value")) == (
                expected["row"], expected["column"], expected["value"])
        elif fid == "gpa_threshold":
            # The old diagnostic never emits scope, so a full-fact verdict is unavailable.
            verdict = None
        elif fid == "team_formula":
            verdict = None  # Factor can be checked, but full formula/scope is not emitted.
        elif fid in {"gqa_sharing", "mqa_sharing"}:
            verdict = found.get("object") == expected.get("object")
        elif fid in {"prefill_action", "decode_action"}:
            verdict = found.get("relation") == expected.get("relation")
        elif fid in {"team_floor"}:
            verdict = found.get("value") == expected.get("value")
        else:
            verdict = None
        comparisons.append({"fact_id": fid, "expected": expected,
                            "observed": found, "correct": verdict})
    expected_ids = {item["fact_id"] for item in record["expected_facts"]}
    for fid, found in observed.items():
        if fid not in expected_ids:
            comparisons.append({"fact_id": fid, "expected": None,
                                "observed": found, "correct": False,
                                "reason": "UNSUPPORTED_EXTRACTION"})
    values = [item["correct"] for item in comparisons]
    overall = False if False in values else True if values and all(value is True for value in values) else None
    return {"fact_extraction_correct": overall, "fact_comparisons": comparisons}


def structured_score(rows, predictions, variant):
    numeric_slots, numeric_observed, numeric_correct = 0, 0, 0
    operator_slots, operator_observed, operator_correct = 0, 0, 0
    table_slots, table_observed, table_correct = 0, 0, 0
    relation_gold, relation_emitted, relation_correct = 0, 0, 0
    details = []
    for row in rows:
        result = predictions[(row["case_id"], variant)]
        observed = structured_observations(row, result["decision"])
        gold = {f["fact_id"]: f for f in row["expected_facts"]}
        for fid, fact in gold.items():
            if fid in {"team_formula", "team_floor", "gpa_threshold", "csp_output", "table_cell"}:
                numeric_slots += 1
                if (fid in observed and "value" in observed[fid]) or (fid == "team_formula" and fid in observed):
                    numeric_observed += 1
                    expected_value = fact.get("factor") if fid == "team_formula" else (fact["output"]["value"] if fid == "csp_output" else fact.get("value"))
                    found_value = observed[fid].get("factor") if fid == "team_formula" else observed[fid].get("value")
                    numeric_correct += expected_value == found_value
            if fid == "gpa_threshold":
                operator_slots += 1
                if fid in observed:
                    operator_observed += 1
                    operator_correct += observed[fid]["operator"] == fact["operator"]
            if fid == "table_cell":
                table_slots += 1
                if fid in observed:
                    table_observed += 1
                    table_correct += (observed[fid]["row"], observed[fid]["column"], observed[fid]["value"]) == (fact["row"], fact["column"], fact["value"])
            if fid in {"gqa_sharing", "mqa_sharing", "prefill_action", "decode_action"}:
                relation_gold += 1
                if fid in observed:
                    relation_correct += all(observed[fid].get(key) == fact[key] for key in observed[fid])
        relation_emitted += sum(fid in observed for fid in ("gqa_sharing", "mqa_sharing", "prefill_action", "decode_action"))
        if observed:
            details.append({"case_id": row["case_id"], "observed": observed})
    return {"numeric_value": {"gold_slots": numeric_slots, "observed": numeric_observed, "correct": numeric_correct,
                               "accuracy_when_observed": numeric_correct / numeric_observed if numeric_observed else None},
            "operator": {"gold_slots": operator_slots, "observed": operator_observed, "correct": operator_correct},
            "table_cell": {"gold_slots": table_slots, "observed": table_observed, "correct": table_correct},
            "relation": {"gold_slots": relation_gold, "emitted": relation_emitted, "correct_gold_slots": relation_correct,
                         "observable_precision": relation_correct / relation_emitted if relation_emitted else None,
                         "observable_recall": relation_correct / relation_gold if relation_gold else None},
            "observable_fact_coverage": {"covered_gold_slots_in_adapter": numeric_slots + relation_gold,
                                         "emitted_slots": numeric_observed + relation_emitted,
                                         "correct_slots": numeric_correct + relation_correct,
                                         "precision": (numeric_correct + relation_correct) / (numeric_observed + relation_emitted) if numeric_observed + relation_emitted else None,
                                         "recall": (numeric_correct + relation_correct) / (numeric_slots + relation_gold) if numeric_slots + relation_gold else None,
                                         "note": "Limited to numeric/relation diagnostics; not global required-fact recall or generated-answer precision."},
            "scope": {"gold_slots": sum(any(f["fact_type"] == "numeric_requirement" for f in r["expected_facts"]) for r in rows),
                      "observed_explicit_scope": 0, "note": "V1 diagnostics do not emit a normalized scope value."},
            "limitations": "This audit only inspects explicit matched/constraints diagnostics; it is not generated-answer correctness or complete fact precision.",
            "observations": details}


def main():
    verify_v1_freeze()
    output = V2 / "rescore-v2.json"
    if output.exists():
        raise RuntimeError("v2 rescore exists; refusing overwrite")
    dataset_path = V2 / "dataset-v2.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    rows = dataset["cases"]
    old = json.loads((V1 / "results.json").read_text(encoding="utf-8"))
    if sha(ROOT / "benchmarks/evidence_matching/matchers.py") != old["input_hashes"]["isolated_matcher"]:
        raise RuntimeError("Frozen matcher code changed; cannot posthoc score E1-E3 stress")
    frozen_main = {(r["case_id"], r["variant"]): r for r in old["rows"]}
    stress = json.loads((V1 / "stress.json").read_text(encoding="utf-8"))
    frozen_stress = {r["case_id"]: r for r in stress["rows"]}
    predictions = {}
    for row in rows:
        cid = row["case_id"]
        for variant in VARIANTS:
            if row["origin"] == "main":
                source = frozen_main[(cid, variant)]
                decision = {key: source[key] for key in ("predicted_label", "reason", "matched", "missing", "constraints")}
                provenance = "frozen_v1_result"
            elif variant in {"E0", "E4"}:
                decision = frozen_stress[cid][variant]
                provenance = "frozen_v1_stress"
            else:
                case = {"case_id": cid, "query": row["query"], "evidence_text": row["evidence_text"],
                        "evidence_metadata": row["evidence_metadata"]}
                decision = evaluate(case, variant)
                provenance = "posthoc_unchanged_v1_matcher"
            predictions[(cid, variant)] = {"case_id": cid, "variant": variant,
                                           "gold_answerability": row["answerability"],
                                           "predicted_answerability": LABEL_MAP[decision["predicted_label"]],
                                           "decision": decision, "prediction_provenance": provenance,
                                           **fact_comparison(row, decision)}
    subsets = {"all_dev_36": rows, "former_main_31": [r for r in rows if r["origin"] == "main"],
               "primary_dev_27": [r for r in rows if r["metric_group"] == "PRIMARY_DEV"],
               "stress_diagnostic_5": [r for r in rows if r["origin"] == "stress"]}
    metrics = {name: {"classification": classification(subset, predictions),
                      "gold_fact_coverage": gold_fact_coverage(subset),
                      "structured_diagnostic": {v: structured_score(subset, predictions, v) for v in VARIANTS}}
               for name, subset in subsets.items()}
    result = {"schema": "evidence-matching-v2-rescore", "review_state": dataset["review_state"],
              "dataset_sha256": sha(dataset_path), "v1_freeze_sha256": sha(V2 / "v1-freeze.json"),
              "matcher_sha256": sha(ROOT / "benchmarks/evidence_matching/matchers.py"),
              "prediction_provenance_note": "Main 31 E0-E4 and stress E0/E4 copied from frozen v1 output; stress E1-E3 computed with unchanged frozen matcher code.",
              "fact_metric_limit": "V1 decisions lack universal per-fact outputs; required-fact recall and covered-fact precision cannot be fully re-scored. Gold coverage and observable diagnostic fields are reported separately.",
              "predictions": list(predictions.values()), "metrics": metrics}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "main_relabelled": sum(r["label_changed_from_v1"] for r in subsets["former_main_31"]),
                      "primary_dev": len(subsets["primary_dev_27"]),
                      "accuracy_all": {v: metrics["all_dev_36"]["classification"][v]["accuracy"] for v in VARIANTS}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
