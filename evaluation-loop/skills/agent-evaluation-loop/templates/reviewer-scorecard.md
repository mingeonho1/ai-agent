# Reviewer scorecard

Have the reviewer fill in the structure below in a fresh, independent context that has not been shown previous scores or iteration records. Without evidence, do not estimate a score; use `null`.

```json
{
  "dimensions": {
    "intent": {"score": null, "evidence": []},
    "correctness": {"score": null, "evidence": []},
    "verification": {"score": null, "evidence": []},
    "clarity": {"score": null, "evidence": []},
    "efficiency": {"score": null, "evidence": []}
  },
  "mandatory_criteria": [
    {"id": "criterion-id", "passed": null, "evidence": []}
  ],
  "findings": [
    {"id": "finding-id", "status": "needs_evidence", "severity": "medium", "confidence": 0.5, "reproducible": false, "resolved": false, "evidence": ["observation that needs further checking"]}
  ]
}
```
