"""Behavior checks for isolated assessors; labels are not read by the matcher."""
import json
from pathlib import Path

from benchmarks.evidence_matching.matchers import evaluate


DATA = json.loads((Path(__file__).resolve().parents[2] / "test-results/evidence-matching-2026-10-03-v2/dataset.json").read_text(encoding="utf-8"))
CASES = {case["case_id"]: case for case in DATA["cases"]}


def test_e1_normalization_recovers_line_split_metric():
    assert evaluate(CASES["gpa-newline"], "E1")["predicted_label"] == "SUPPORTED"


def test_e3_explicit_alias_recovers_team_rule():
    assert evaluate(CASES["team-real"], "E3")["predicted_label"] == "SUPPORTED"


def test_e4_numeric_and_table_hard_negatives():
    for cid in ("gpa-other-metric", "gpa-exception-scope", "gpa-operator-negative",
                "csp-wrong-input", "table-header", "table-wrong-row", "team-wrong-factor"):
        assert evaluate(CASES[cid], "E4")["predicted_label"] == "NOT_SUPPORTED", cid


def test_e4_comparison_partial_and_swapped():
    assert evaluate(CASES["gqa-mqa-real"], "E4")["predicted_label"] == "SUPPORTED"
    assert evaluate(CASES["gqa-mqa-partial"], "E4")["predicted_label"] == "PARTIAL"
    assert evaluate(CASES["gqa-mqa-swapped"], "E4")["predicted_label"] == "NOT_SUPPORTED"


def test_e4_definition_and_partial():
    assert evaluate(CASES["ai-infra-real"], "E4")["predicted_label"] == "SUPPORTED"
    assert evaluate(CASES["ai-infra-parts-only"], "E4")["predicted_label"] == "PARTIAL"
