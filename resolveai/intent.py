"""Rule-based intent classifier: count keyword hits per intent. Simple and explainable."""
import re

from .retrieval import stem

INTENTS = ["delay", "cancellation", "refund", "incomplete_order", "general"]

_WORDS = {
    "delay": ["late", "delay", "wait", "slow", "eta", "later"],
    "cancellation": ["cancel", "cancellation"],
    "refund": ["refund", "reimburse", "overcharge", "charge", "reembolso"],
    "incomplete_order": ["missing", "wrong", "incomplete", "forgot", "absent"],
}
_PHRASES = {
    "delay": ["not arrived", "never arrived", "hasn't arrived", "where is my order", "taking too long"],
    "refund": ["money back", "get my money"],
    "incomplete_order": ["not included", "left out", "not delivered", "different item"],
}
_STEMS = {i: {stem(w) for w in ws} for i, ws in _WORDS.items()}


def classify(message: str) -> tuple[str, bool, dict]:
    """Return (intent, ambiguous, scores). Ambiguous = two intents tie for the top score.
    No keyword at all -> 'general'."""
    low = message.lower()
    words = {stem(w) for w in re.findall(r"[a-z0-9']+", low)}
    scores = {i: len(_STEMS[i] & words) + sum(p in low for p in _PHRASES.get(i, [])) for i in _WORDS}
    ranked = sorted(scores.values(), reverse=True)
    if ranked[0] == 0:
        return "general", False, scores
    ambiguous = ranked[1] == ranked[0]
    return max(scores, key=scores.get), ambiguous, scores
