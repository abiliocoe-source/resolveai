"""Presentation components for ResolveAI. Every dynamic value is escaped: messages and documents are untrusted."""
import html
import re
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
STATUS = {"answered": "Answered", "no_evidence": "No source found", "escalated": "Passed to an agent"}
REVIEW = {"pending": "Waiting for an agent", "not_needed": "No review needed", "approved": "Approved",
          "corrected": "Corrected", "rejected": "Rejected"}


def esc(x) -> str:
    return html.escape(str(x))


def inject_css() -> None:
    st.markdown(f"<style>{(ROOT / 'assets' / 'style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def mode_strip(llm_mode: bool) -> None:
    """Fixed to the top of the window: the answer mode is never out of sight."""
    if llm_mode:
        st.markdown("<div class='mode llm'><b>LLM mode</b><span class='long'>Answers come from the configured model and are discarded if they cite "
                    "anything but the sources.</span><span class='short'>sources only</span></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='mode'><b>Demo mode</b><span class='long'>No LLM is connected. Every answer is copied word for word from the fictional "
                    "FastBox policies.</span><span class='short'>no LLM, quotes only</span></div>", unsafe_allow_html=True)


def brand(scope: str) -> None:
    mark = ("<svg width='28' height='32' viewBox='0 0 28 32' aria-hidden='true'><path d='M2 4h24v24H2z' fill='#FFD23F'/>"
            "<circle cx='2' cy='16' r='4' fill='#fff'/><circle cx='26' cy='16' r='4' fill='#fff'/>"
            "<rect x='8' y='10' width='12' height='3' fill='#14201B'/><rect x='8' y='17' width='8' height='3' fill='#0E4D3A'/></svg>")
    st.markdown(f"<div class='brand'>{mark}<div><div class='n'>ResolveAI</div><div class='s'>{esc(scope)}</div></div></div>", unsafe_allow_html=True)


def waiting(n: int) -> None:
    word = "case waits" if n == 1 else "cases wait"
    st.markdown(f"<div class='waiting'><div class='v'>{n}</div><div class='l'>{word} for an agent</div></div>", unsafe_allow_html=True)


def title(h1: str, finding: str) -> None:
    st.markdown(f"<div class='title'><h1>{esc(h1)}</h1><p>{finding}</p></div>", unsafe_allow_html=True)


def note(kind: str, title: str, text: str = "") -> None:
    st.markdown(f"<div class='note {kind}'><b>{esc(title)}</b> {esc(text)}</div>", unsafe_allow_html=True)


def region(title: str, sub: str = "") -> None:
    st.markdown(f"<div class='region-h'><h2>{esc(title)}</h2><span class='sub'>{esc(sub)}</span></div>", unsafe_allow_html=True)


def ago(iso: str) -> str:
    """Time in words, as a queue shows it: 'now', '5 min', '3 h', or the date."""
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    secs = (datetime.now(timezone.utc) - t).total_seconds()
    if secs < 60:
        return "now"
    if secs < 3600:
        return f"{int(secs // 60)} min"
    if secs < 86400:
        return f"{int(secs // 3600)} h"
    return t.strftime("%d %b")


def stamp(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b, %H:%M UTC")
    except ValueError:
        return iso


def row_label(t: dict) -> str:
    """Two-line queue row: ticket, state and time; then what the customer asked."""
    msg = t["message"] if len(t["message"]) <= 64 else t["message"][:63].rstrip() + "…"
    return f"**A-{t['id']:03d}** · {STATUS[t['status']]} · {ago(t['created'])}  \n{msg}"


def ticket(i: int, big: bool = False) -> str:
    return f"<span class='tk{' big' if big else ''}'>A-{i:03d}</span>"


def pills(t: dict) -> str:
    return (f"<span class='pill cat'>{esc(t['intent'].replace('_', ' '))}</span>"
            f"<span class='pill {t['status']}'>{esc(STATUS[t['status']])}</span>")


def case_view(t: dict) -> str:
    body = re.sub(r"\[(S\d+)\]", r"<sup class='cite'>\1</sup>", esc(t["answer"]))
    return (f"<div class='case-h'>{ticket(t['id'])}{pills(t)}<span class='when'>{esc(ago(t['created']))} · {esc(t['created'][11:16])} UTC</span></div>"
            f"<div class='said'>{esc(t['message'])}<small>Personal data was masked before saving.</small></div>"
            f"<div class='reply'><div class='lbl'>Answer</div><div class='body'>{body}</div></div>")


def score_chip(score) -> str:
    """Retrieval score band: a UI rule of thumb (0.30 strong, 0.15 medium), not a calibrated probability."""
    if score is None:
        return ""
    band = "strong" if score >= 0.30 else "medium" if score >= 0.15 else "weak"
    return f"<span class='chip'>match score {score:.2f} · {band}</span>"


def source_card(c: dict, chunk_text: str, score) -> str:
    quote = esc(c["quote"])
    full = esc(chunk_text).replace(quote, f"<mark>{quote}</mark>", 1)
    return (f"<div class='src'><div class='h'>[{esc(c['label'])}] {esc(c['title'])} › {esc(c['heading'])}</div>"
            f"<div class='q'><mark>{quote}</mark></div><div class='meta'>{score_chip(score)}</div>"
            f"<details><summary>Read the full passage</summary><p>{full}</p></details></div>")


def details(t: dict, result) -> str:
    rating = "not rated" if t["rating"] is None else ("helpful" if t["rating"] else "not helpful")
    rev = esc(REVIEW.get(t["review"], t["review"])) + (f", {esc(t['review_note'])}" if t["review_note"] else "")
    table = ""
    if result is not None and result.retrieved:
        rows = "".join(f"<tr><td>{esc(cid)}</td><td class='r'>{s:.3f}</td></tr>" for cid, s in result.retrieved)
        table = f"<table class='rt'><thead><tr><th>Passages retrieved</th><th class='r'>Score</th></tr></thead><tbody>{rows}</tbody></table>"
    return (f"<div>{ticket(t['id'], big=True)}</div>"
            f"<dl class='dl'><dt>Reason</dt><dd>{esc(t['reason'] or 'none')}</dd><dt>Answer mode</dt><dd>{esc(t['mode'])}</dd>"
            f"<dt>Agent review</dt><dd>{rev}</dd><dt>User rating</dt><dd>{rating}</dd><dt>Opened</dt><dd>{esc(stamp(t['created']))}</dd></dl>{table}")


def kpi_strip(cells) -> str:
    return "<div class='kpis'>" + "".join(f"<div class='kpi'><div class='l'>{esc(l)}</div><div class='v'>{v}<small>{esc(u)}</small></div></div>" for l, v, u in cells) + "</div>"


def hbars(data: dict) -> str:
    top = max(data.values()) if data and max(data.values()) else 1
    return "".join(f"<div class='hbar'><span>{esc(k.replace('_', ' '))}</span><div class='t'><i style='width:{v / top * 100:.0f}%'></i></div><span class='n'>{v}</span></div>"
                   for k, v in data.items())
