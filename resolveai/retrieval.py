"""TF-IDF retrieval. Chosen over embeddings because the base is small, the vocabulary is
domain-specific, results are deterministic and explainable, and it needs no model download."""
import re

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .kb import Chunk


def stem(word: str) -> str:
    """Tiny suffix stripper so 'cancelled', 'cancel' and 'cancellation'-like forms meet."""
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            word = word[: -len(suffix)]
            break
    if len(word) > 4 and word.endswith("e"):
        word = word[:-1]
    if len(word) > 4 and word[-1] == word[-2] and word[-1] not in "aeiou":
        word = word[:-1]
    return word


def tokens(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in ENGLISH_STOP_WORDS]


class Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = list(chunks)
        self.vectorizer = TfidfVectorizer(tokenizer=tokens, lowercase=False, token_pattern=None,
                                          ngram_range=(1, 2), sublinear_tf=True)
        self.matrix = None
        if self.chunks:
            self.matrix = self.vectorizer.fit_transform(f"{c.heading} {c.text}" for c in self.chunks)

    def search(self, query: str, k: int = 3, boost_category: str | None = None):
        """Return [(chunk, raw_score, ranked_score)] best first. Category match boosts ranking only."""
        if self.matrix is None or not tokens(query):
            return []
        sims = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        rows = []
        for chunk, s in zip(self.chunks, sims):
            if s > 0:
                boost = 1.2 if boost_category and chunk.category == boost_category else 1.0
                rows.append((chunk, float(s), float(s) * boost))
        return sorted(rows, key=lambda r: -r[2])[:k]

    def sentence_scores(self, query: str, sentences: list[str]) -> list[float]:
        if self.matrix is None or not sentences:
            return [0.0] * len(sentences)
        q = self.vectorizer.transform([query])
        return [float(x) for x in cosine_similarity(q, self.vectorizer.transform(sentences))[0]]
