"""Record immutable v1 inputs before the annotation redesign."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "test-results/evidence-matching-2026-10-03-v2"
V2 = ROOT / "test-results/evidence-matching-v2-2026-10-03"
FILES = ("dataset.json", "results.json", "stress.json", "report.md", "e0-baseline.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    V2.mkdir(parents=True, exist_ok=True)
    path = V2 / "v1-freeze.json"
    if path.exists():
        raise RuntimeError("v1 freeze already exists; refusing overwrite")
    files = {name: {"path": str(V1 / name), "size": (V1 / name).stat().st_size,
                    "sha256": sha(V1 / name)} for name in FILES}
    path.write_text(json.dumps({"schema": "evidence-matching-v1-freeze",
                                "source_status": "historical_diagnostic_agent_labels_not_human_verified",
                                "files": files}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
