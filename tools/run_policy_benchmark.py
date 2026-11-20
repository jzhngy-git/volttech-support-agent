from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app
from policy_search import MODEL_NAME


MIN_RECALL_AT_1 = 0.85


def load_cases() -> list[dict[str, Any]]:
    with (ROOT / "benchmarks" / "policy_retrieval.json").open(encoding="utf-8") as file:
        cases = json.load(file)
    if not isinstance(cases, list) or not cases:
        raise ValueError("The policy benchmark must contain a non-empty list of cases.")
    return cases


def evaluate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    supported = [case for case in cases if case["expected_title"] is not None]
    unsupported = [case for case in cases if case["expected_title"] is None]
    supported_correct = 0
    citations_correct = 0
    citation_count = 0
    unsupported_abstained = 0
    failures = []

    citations = {
        policy["title"]: f'{policy["section"]}, p. {policy["page"]}'
        for policy in app.POLICIES
    }

    for case in cases:
        results = app.retrieve_policies(case["question"])
        expected = case["expected_title"]
        actual = results[0]["title"] if results else None
        expected_titles = expected if isinstance(expected, list) else [expected]
        is_correct = actual in expected_titles

        if expected is not None and is_correct:
            supported_correct += 1
        if expected is None and actual is None:
            unsupported_abstained += 1
        for result in results:
            citation_count += 1
            if result["citation"] == citations.get(result["title"]):
                citations_correct += 1
        if not is_correct:
            failures.append(
                {
                    "question": case["question"],
                    "expected": expected,
                    "actual": actual,
                    "score": results[0]["score"] if results else None,
                }
            )

    return {
        "embedding_model": MODEL_NAME,
        "case_count": len(cases),
        "supported_case_count": len(supported),
        "unsupported_case_count": len(unsupported),
        "recall_at_1": supported_correct / len(supported) if supported else 0.0,
        "accuracy_at_1": (supported_correct + unsupported_abstained) / len(cases),
        "citation_accuracy": citations_correct / citation_count if citation_count else 1.0,
        "unsupported_abstention_accuracy": (
            unsupported_abstained / len(unsupported) if unsupported else 1.0
        ),
        "failures": failures,
    }


def main() -> int:
    report = evaluate(load_cases())
    print(json.dumps(report, indent=2))
    passed = (
        report["recall_at_1"] >= MIN_RECALL_AT_1
        and report["citation_accuracy"] == 1.0
        and report["unsupported_abstention_accuracy"] == 1.0
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
