"""Reproducible evaluation: python -m resolveai.evaluate  (writes eval/results.json + eval/RESULTS.md).

Metrics (each over the cases it applies to):
- retrieval_hit@3 : an expected document is among the top-3 retrieved chunks (normal cases)
- intent_accuracy : predicted intent equals the expected one (normal cases)
- routing_accuracy: final status equals the expected status (all cases; covers escalation / no-evidence)
- grounding       : every citation quote is an exact substring of the stored KB chunk AND the
                    expected key phrase appears in the answer (normal cases that were answered)
- citation_match  : the expected document is among the cited documents (normal cases answered)
- injection_resistance: injection cases escalated AND answer leaks none of the forbidden strings
Cases are written by the developer of the system, so results are optimistic by nature.
"""
import json
from pathlib import Path

from .agent import Agent
from .kb import load_kb

ROOT = Path(__file__).resolve().parent.parent


def _rate(flags: list[bool]):
    return None if not flags else round(sum(flags) / len(flags), 3)


def run(cases_path: Path = ROOT / "eval" / "cases.json", agent: Agent | None = None) -> dict:
    chunks = load_kb()
    by_id = {c.id: c for c in chunks}
    agent = agent or Agent(chunks, use_llm=False)  # evaluation is always the local, deterministic mode
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    m = {k: [] for k in ("retrieval", "intent", "routing", "grounding", "citation", "injection")}
    rows = []
    for c in cases:
        r = agent.handle(c["message"])
        failures = []
        ok_route = r.status == c["expect_status"]
        m["routing"].append(ok_route)
        if not ok_route:
            failures.append(f"status {r.status} != {c['expect_status']}")
        if c["category"] == "normal":
            top3 = [h[0].doc for h in agent.retrieve(c["message"], 3, intent=r.intent)]
            hit = c["expect_doc"] in top3
            m["retrieval"].append(hit)
            m["intent"].append(r.intent == c["expect_intent"])
            if not hit:
                failures.append(f"expected doc {c['expect_doc']} not in top3 {top3}")
            if r.intent != c["expect_intent"]:
                failures.append(f"intent {r.intent} != {c['expect_intent']}")
            if r.status == "answered":
                quotes_ok = all(cit["quote"] in by_id[cit["chunk_id"]].text for cit in r.citations)
                phrase_ok = c["must_contain"].lower() in r.answer.lower()
                m["grounding"].append(quotes_ok and phrase_ok)
                m["citation"].append(c["expect_doc"] in {cit["doc"] for cit in r.citations})
                if not (quotes_ok and phrase_ok):
                    failures.append(f"grounding: phrase '{c['must_contain']}' missing or quote unverifiable")
                if c["expect_doc"] not in {cit["doc"] for cit in r.citations}:
                    failures.append("expected doc not cited")
        if c["category"] == "injection":
            leaked = any(f in r.answer.lower() for f in c.get("forbidden", []))
            m["injection"].append(ok_route and not leaked)
        rows.append({"id": c["id"], "category": c["category"], "status": r.status, "intent": r.intent,
                     "pass": not failures, "failures": failures})
    summary = {
        "n_cases": len(cases),
        "by_category": {cat: sum(x["category"] == cat for x in rows) for cat in sorted({x["category"] for x in rows})},
        "retrieval_hit@3": _rate(m["retrieval"]), "intent_accuracy": _rate(m["intent"]),
        "routing_accuracy": _rate(m["routing"]), "grounding": _rate(m["grounding"]),
        "citation_match": _rate(m["citation"]), "injection_resistance": _rate(m["injection"]),
        "cases_fully_passing": sum(x["pass"] for x in rows),
        "min_score": agent.min_score, "mode": "demo-extractive (no LLM)",
    }
    return {"summary": summary, "cases": rows}


def write_reports(res: dict) -> None:
    (ROOT / "eval" / "results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    s = res["summary"]
    lines = ["# Evaluation results", "", f"Mode: {s['mode']} · {s['n_cases']} cases · {s['by_category']}", "",
             "| Metric | Value |", "|---|---|"]
    lines += [f"| {k} | {s[k]} |" for k in ("retrieval_hit@3", "intent_accuracy", "routing_accuracy",
                                           "grounding", "citation_match", "injection_resistance")]
    lines += [f"| cases fully passing | {s['cases_fully_passing']} / {s['n_cases']} |", "", "## Failures", ""]
    fails = [c for c in res["cases"] if not c["pass"]]
    lines += [f"- {c['id']} ({c['category']}): " + "; ".join(c["failures"]) for c in fails] or ["- none"]
    (ROOT / "eval" / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    result = run()
    write_reports(result)
    print(json.dumps(result["summary"], indent=1))
    for c in result["cases"]:
        if not c["pass"]:
            print(c["id"], c["failures"])
