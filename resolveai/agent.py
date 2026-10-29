"""Support agent: guard -> classify -> retrieve -> grounded answer, or escalate / admit no evidence.

Statuses: answered | no_evidence | escalated. The agent never performs actions (no refunds,
no cancellations): it only explains the written policy and routes cases to a human.
"""
import re
from dataclasses import dataclass, field

from . import llm
from .guard import detect_injection, redact, sensitive_reason
from .intent import classify
from .kb import Chunk
from .retrieval import Index, tokens

MIN_SCORE = 0.12        # raw cosine below this = "no evidence" (chosen on a first pass of the eval set)
MIN_COVERAGE = 0.5      # more than this share of the question's terms must appear in the top source
MAX_MESSAGE_CHARS = 1000
NOTE_ACTIONS = "Note: I can't issue refunds or cancel orders myself; a human agent does that."

MSG_ESCALATED = "I've passed this to a human agent, who will follow up. Reason: {reason}."
MSG_NO_EVIDENCE = ("I couldn't find this in our policies, so I won't guess. "
                   "A human agent can review it.")


@dataclass
class Result:
    message: str                  # redacted customer message
    intent: str
    status: str
    answer: str
    reason: str = ""
    citations: list = field(default_factory=list)  # {label, chunk_id, doc, title, heading, quote}
    retrieved: list = field(default_factory=list)  # [(chunk_id, raw_score)]
    mode: str = "demo-extractive"


class Agent:
    def __init__(self, chunks: list[Chunk], min_score: float = MIN_SCORE, use_llm: bool = True):
        # Documents are untrusted too: drop any chunk that tries to instruct the model.
        self.dropped = [c.id for c in chunks if detect_injection(c.text)]
        self.chunks = [c for c in chunks if c.id not in self.dropped]
        self.index = Index(self.chunks)
        self._vocab = {c.id: set(tokens(f"{c.heading} {c.text}")) for c in self.chunks}
        self.min_score, self.use_llm = min_score, use_llm

    def retrieve(self, message: str, k: int = 3, intent: str | None = None):
        return self.index.search(message, k, boost_category=intent)

    def handle(self, message: str) -> Result:
        text = redact((message or "").strip()[:MAX_MESSAGE_CHARS])
        if not text:
            return Result(text, "general", "no_evidence", "Please type your question.", "empty message")
        intent, ambiguous, _ = classify(text)

        if detect_injection(text):
            return self._escalate(text, intent, "possible prompt injection")
        if (why := sensitive_reason(text)) is not None:
            return self._escalate(text, intent, why)
        if ambiguous:
            return self._escalate(text, intent, "unclear request: it mixes several topics")

        hits = self.retrieve(text, intent=intent)
        retrieved = [(c.id, round(raw, 3)) for c, raw, _ in hits]
        if not hits or max(raw for _, raw, _ in hits) < self.min_score:
            return Result(text, intent, "no_evidence", MSG_NO_EVIDENCE, "no source above threshold",
                          retrieved=retrieved)
        # Generic words ("order", "delivery") match everywhere; require the question's own terms
        # to be mostly present in the best source, otherwise the base does not really cover it.
        terms = set(tokens(text))
        if len(terms & self._vocab[hits[0][0].id]) / len(terms) <= MIN_COVERAGE:
            return Result(text, intent, "no_evidence", MSG_NO_EVIDENCE, "question terms not covered by sources",
                          retrieved=retrieved)

        citations = self._pick_sentences(text, hits)
        answer, mode = self._compose(text, citations, intent)
        return Result(text, intent, "answered", answer, citations=citations, retrieved=retrieved, mode=mode)

    # -- helpers ---------------------------------------------------------------------------
    def _escalate(self, text, intent, reason) -> Result:
        return Result(text, intent, "escalated", MSG_ESCALATED.format(reason=reason), reason)

    def _pick_sentences(self, query: str, hits) -> list[dict]:
        """Best 2 sentences of the top chunk (+ best sentence of a close second chunk).
        Quotes are exact substrings of the stored chunk text."""
        picks = [(hits[0][0], 2)]
        if len(hits) > 1 and hits[1][1] >= 0.7 * hits[0][1]:
            picks.append((hits[1][0], 1))
        citations = []
        for chunk, n in picks:
            sentences = re.split(r"(?<=[.!?])\s+", chunk.text)
            scores = self.index.sentence_scores(query, sentences)
            best = sorted(sorted(range(len(sentences)), key=lambda i: -scores[i])[:n])
            for i in best:
                citations.append({"label": f"S{len(citations) + 1}", "chunk_id": chunk.id, "doc": chunk.doc,
                                  "title": chunk.title, "heading": chunk.heading, "quote": sentences[i]})
        return citations

    def _compose(self, query, citations, intent) -> tuple[str, str]:
        if self.use_llm:
            text = llm.answer(query, [c["quote"] for c in citations])
            if text:
                return text, "llm"
        answer = " ".join(f"{c['quote']} [{c['label']}]" for c in citations)
        if intent in ("refund", "cancellation"):
            answer += f"\n\n{NOTE_ACTIONS}"
        return answer, "demo-extractive"
