import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "evaluate.py"
SPEC = importlib.util.spec_from_file_location("evaluate", SCRIPT)
evaluate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(evaluate)


def baseline():
    return {
        "schema_version": "1.0",
        "evaluation_id": "eval-v1",
        "task_id": "task",
        "task_fingerprint": "task-fp",
        "attempt": 1,
        "candidate_fingerprint": "candidate-1",
        "evidence_fingerprint": "evidence-1",
        "rubric_version": "1.0.0",
        "routing": {
            "required_reviewer_model": "gpt-6-astra",
            "required_reviewer_effort": "xhigh",
            "actual_reviewer_model": "gpt-6-astra",
            "actual_reviewer_effort": "xhigh",
            "isolation_confirmed": True,
        },
        "loop": {"model": "gpt-6-sol", "effort": "medium"},
        "progress_kind": "baseline",
        "dimensions": {
            name: {"score": 4, "evidence": [f"evidence for {name}"]}
            for name in evaluate.DIMENSIONS
        },
        "mandatory_criteria": [{"id": "required", "passed": True, "evidence": ["passed"]}],
        "findings": [],
        "fix_targets": [],
        "runtime": {
            "duration_seconds": None,
            "cost_usd": None,
            "input_tokens": None,
            "output_tokens": None,
        },
    }


class EvaluateTests(unittest.TestCase):
    def test_missing_evidence_is_needs_evidence_and_total_is_null(self):
        doc = baseline()
        doc["dimensions"]["verification"] = {"score": None, "evidence": []}
        doc["fix_targets"] = ["collect verification evidence"]
        result = evaluate.evaluate_round(doc, [])
        self.assertEqual(result["decision"], "NEEDS_EVIDENCE")
        self.assertIsNone(result["weighted_total"])

    def test_unresolved_high_finding_blocks_high_total(self):
        doc = baseline()
        doc["findings"] = [{
            "id": "bug",
            "status": "confirmed",
            "severity": "high",
            "confidence": 0.9,
            "reproducible": True,
            "resolved": False,
            "evidence": ["reproduction"],
        }]
        doc["fix_targets"] = ["fix bug"]
        result = evaluate.evaluate_round(doc, [])
        self.assertEqual(result["weighted_total"], 100.0)
        self.assertEqual(result["decision"], "IMPROVE")

    def test_score_bounds_are_enforced(self):
        doc = baseline()
        doc["dimensions"]["intent"]["score"] = 5
        with self.assertRaises(evaluate.EvaluationError):
            evaluate.evaluate_round(doc, [])

    def test_duplicate_attempt_is_rejected_without_overwrite(self):
        doc = baseline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "round.json"
            history = root / "history.jsonl"
            source.write_text(json.dumps(doc), encoding="utf-8")
            evaluate.append_round(source, history)
            with self.assertRaises(evaluate.EvaluationError):
                evaluate.append_round(source, history)
            self.assertEqual(len(history.read_text(encoding="utf-8").splitlines()), 1)

    def test_reviewer_model_mismatch_is_rejected(self):
        doc = baseline()
        doc["routing"]["actual_reviewer_model"] = "lighter-model"
        with self.assertRaises(evaluate.EvaluationError):
            evaluate.evaluate_round(doc, [])

    def test_cheaper_required_reviewer_is_rejected(self):
        doc = baseline()
        doc["routing"]["required_reviewer_model"] = "lighter-model"
        doc["routing"]["actual_reviewer_model"] = "lighter-model"
        with self.assertRaises(evaluate.EvaluationError):
            evaluate.evaluate_round(doc, [])

    def test_frozen_criteria_cannot_be_replaced(self):
        first_doc = baseline()
        first_doc["dimensions"]["intent"]["score"] = 2
        first_doc["fix_targets"] = ["fix intent"]
        first = evaluate.evaluate_round(first_doc, [])
        second = copy.deepcopy(first_doc)
        second.update(attempt=2, progress_kind="resolved_defect", candidate_fingerprint="candidate-2")
        second["mandatory_criteria"][0]["id"] = "easier-check"
        with self.assertRaises(evaluate.EvaluationError):
            evaluate.evaluate_round(second, [first])

    def test_terminal_round_cannot_be_extended(self):
        first = evaluate.evaluate_round(baseline(), [])
        second = baseline()
        second.update(attempt=2, progress_kind="added_evidence", evidence_fingerprint="evidence-2")
        with self.assertRaises(evaluate.EvaluationError):
            evaluate.evaluate_round(second, [first])

    def test_required_reviewer_routing_is_frozen(self):
        first_doc = baseline()
        first_doc["dimensions"]["intent"]["score"] = 2
        first_doc["fix_targets"] = ["fix intent"]
        first = evaluate.evaluate_round(first_doc, [])
        second = copy.deepcopy(first_doc)
        second.update(attempt=2, progress_kind="resolved_defect", candidate_fingerprint="candidate-2")
        second["routing"]["required_reviewer_model"] = "claude-fable-5-1"
        second["routing"]["actual_reviewer_model"] = "claude-fable-5-1"
        with self.assertRaises(evaluate.EvaluationError):
            evaluate.evaluate_round(second, [first])

    def test_nonfinite_runtime_is_rejected(self):
        doc = baseline()
        doc["runtime"]["cost_usd"] = float("nan")
        with self.assertRaises(evaluate.EvaluationError):
            evaluate.evaluate_round(doc, [])

    def test_unconfirmed_finding_requests_evidence_without_becoming_blocker(self):
        doc = baseline()
        doc["findings"] = [{
            "id": "hypothesis",
            "status": "needs_evidence",
            "severity": "high",
            "confidence": 0.4,
            "reproducible": False,
            "resolved": False,
            "evidence": ["suspicious observation"],
        }]
        doc["fix_targets"] = ["reproduce or refute hypothesis"]
        result = evaluate.evaluate_round(doc, [])
        self.assertEqual(result["evaluation_status"], "NEEDS_EVIDENCE")
        self.assertEqual(result["decision"], "NEEDS_EVIDENCE")
        self.assertTrue(result["gates"]["no_unresolved_high_or_medium"])

        followup = copy.deepcopy(doc)
        followup.update(attempt=2, progress_kind="added_evidence", evidence_fingerprint="evidence-2")
        followup["findings"][0].update(
            status="refuted",
            confidence=0.95,
            reproducible=True,
            resolved=True,
            evidence=["targeted check did not reproduce the hypothesis"],
        )
        followup["fix_targets"] = []
        second = evaluate.evaluate_round(followup, [result])
        self.assertEqual(second["evaluation_status"], "PASS")
        self.assertEqual(second["decision"], "PASS")

    def test_score_only_retry_is_rejected(self):
        first = evaluate.evaluate_round(baseline(), [])
        second = baseline()
        second["attempt"] = 2
        second["progress_kind"] = "none"
        with self.assertRaises(evaluate.EvaluationError):
            evaluate.evaluate_round(second, [first])

    def test_two_stalls_stop_not_complete(self):
        first_doc = baseline()
        first_doc["dimensions"]["intent"]["score"] = 2
        first_doc["fix_targets"] = ["resolve intent gap"]
        first = evaluate.evaluate_round(first_doc, [])

        second_doc = copy.deepcopy(first_doc)
        second_doc.update(attempt=2, progress_kind="none", candidate_fingerprint="candidate-2")
        second = evaluate.evaluate_round(second_doc, [first])

        third_doc = copy.deepcopy(second_doc)
        third_doc.update(attempt=3, progress_kind="none", candidate_fingerprint="candidate-3")
        third = evaluate.evaluate_round(third_doc, [first, second])
        self.assertEqual(third["decision"], "STOP_NOT_COMPLETE")
        self.assertEqual(third["stall_count"], 2)


if __name__ == "__main__":
    unittest.main()
