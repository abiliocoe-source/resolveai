# Evaluation results

Mode: demo-extractive (no LLM) · 36 cases · {'ambiguous': 5, 'injection': 6, 'no_answer': 5, 'normal': 12, 'out_of_scope': 4, 'sensitive': 4}

| Metric | Value |
|---|---|
| retrieval_hit@3 | 1.0 |
| intent_accuracy | 1.0 |
| routing_accuracy | 0.944 |
| grounding | 1.0 |
| citation_match | 1.0 |
| injection_resistance | 1.0 |
| cases fully passing | 34 / 36 |

## Failures

- n05 (normal): status no_evidence != answered
- x03 (no_answer): status answered != no_evidence
