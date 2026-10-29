"""Safety helpers. Customer messages AND knowledge-base documents are untrusted input."""
import re

_INJECTION = [
    r"ignore\b.{0,30}\b(instruction|rule|prompt|polic)",
    r"disregard\b.{0,30}\b(instruction|rule|prompt|above|polic)",
    r"forget\b.{0,20}\b(instruction|rule|prompt)",
    r"(reveal|show|print|repeat|leak)\b.{0,30}\b(system|hidden|initial)\b.{0,10}\b(prompt|instruction|rule)",
    r"\bsystem prompt\b",
    r"\bhidden rules?\b",
    r"you are now\b",
    r"\bdeveloper mode\b",
    r"\bjailbreak\b",
    r"\bact as (the |a |an )?(manager|admin|developer|system)",
    r"\boverride\b.{0,20}\b(rule|polic|instruction)",
]
_SENSITIVE = {
    "legal threat": r"\b(sue|suing|lawyer|attorney|lawsuit|legal action|court)\b",
    "chargeback": r"\bcharge ?back\b",
    "health or safety": r"\b(allerg\w*|food poisoning|hospital|poisoned|sick|injur\w*)\b",
    "possible fraud": r"\b(fraud\w*|unauthori[sz]ed|stolen|scam)\b",
    "personal data request": r"\b(delete|erase|export)\b.{0,25}\b(my )?(personal )?(data|account information)\b",
}
_REDACT = [
    ("[EMAIL]", r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    ("[CARD]", r"\b(?:\d[ -]?){13,19}\b"),
    ("[PHONE]", r"\+?\d[\d\s().-]{7,}\d"),
]


def detect_injection(text: str) -> bool:
    low = text.lower()
    return any(re.search(p, low) for p in _INJECTION)


def sensitive_reason(text: str) -> str | None:
    low = text.lower()
    for reason, pattern in _SENSITIVE.items():
        if re.search(pattern, low):
            return reason
    return None


def redact(text: str) -> str:
    """Mask e-mails, card numbers and phone numbers before storing or sending text anywhere."""
    for label, pattern in _REDACT:
        text = re.sub(pattern, label, text)
    return text
