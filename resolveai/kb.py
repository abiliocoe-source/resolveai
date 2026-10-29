"""Knowledge base: load markdown documents and split them into chunks (one per section)."""
import re
from dataclasses import dataclass
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "kb"
MAX_DOC_CHARS = 50_000   # documents are untrusted input: cap their size
MAX_CHUNK_WORDS = 80


@dataclass(frozen=True)
class Chunk:
    id: str        # "<doc>#<n>"
    doc: str       # document id (file name without .md)
    title: str
    category: str  # delay | cancellation | refund | incomplete_order | general
    heading: str
    text: str


def _split_long(text: str) -> list[str]:
    """Break a long section into pieces of at most MAX_CHUNK_WORDS words, on sentence borders."""
    pieces, current = [], []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        if current and len(" ".join(current + [sentence]).split()) > MAX_CHUNK_WORDS:
            pieces.append(" ".join(current))
            current = []
        current.append(sentence)
    if current:
        pieces.append(" ".join(current))
    return pieces


def parse_document(doc_id: str, raw: str) -> list[Chunk]:
    """'# Title', optional 'Category: x', then '## Heading' sections -> chunks."""
    if len(raw) > MAX_DOC_CHARS:
        raise ValueError(f"document too large (max {MAX_DOC_CHARS} characters)")
    title = doc_id
    category = "general"
    sections: list[tuple[str, list[str]]] = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif line.startswith("# "):
            title = line[2:].strip()
        elif line.lower().startswith("category:"):
            category = line.split(":", 1)[1].strip().lower() or "general"
        elif line and sections:
            sections[-1][1].append(line)
    chunks = []
    for heading, body in sections:
        for piece in _split_long(" ".join(body)):
            chunks.append(Chunk(f"{doc_id}#{len(chunks) + 1}", doc_id, title, category, heading, piece))
    return chunks


def load_kb(kb_dir: Path = KB_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(Path(kb_dir).glob("*.md")):
        chunks += parse_document(path.stem, path.read_text(encoding="utf-8"))
    return chunks


def safe_doc_id(name: str) -> str:
    """File names from uploads are untrusted: keep only [a-z0-9_-]."""
    stem = re.sub(r"[^a-z0-9_-]+", "_", Path(name).stem.lower()).strip("_")
    if not stem:
        raise ValueError("invalid document name")
    return stem[:60]


def add_document(name: str, raw: str, kb_dir: Path = KB_DIR) -> list[Chunk]:
    """Validate and save a new/updated document, return its chunks. Caller rebuilds the index."""
    doc_id = safe_doc_id(name)
    chunks = parse_document(doc_id, raw)
    if not chunks:
        raise ValueError("no sections found: use '# Title' and '## Heading' markdown")
    Path(kb_dir).mkdir(parents=True, exist_ok=True)
    (Path(kb_dir) / f"{doc_id}.md").write_text(raw, encoding="utf-8")
    return chunks
