"""Presentation components for ResolveAI. Every dynamic value is escaped: messages and documents are untrusted."""
import html
import re
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
STATUS = {"answered": ("✓", "Answered from sources"), "no_evidence": ("?", "No source found"),
          "escalated": ("→", "Passed to an agent")}
REVIEW = {"pending": "Waiting for an agent", "not_needed": "No review needed", "approved": "Approved",
          "corrected": "Corrected", "rejected": "Rejected"}


def esc(x) -> str:
    return html.escape(str(x))


def inject_css() -> None:
    st.markdown(f"<style>{(ROOT / 'assets' / 'style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def mode_strip(llm_mode: bool) -> None:
    """Fixed to the top of the window: the mode is never out of sight."""
    if llm_mode:
        st.markdown("<div class='mode-strip llm'><span class='long'>LLM MODE · answers are written by the configured model from the "
                    "sources and discarded if they cite anything else.</span><span class='short'>LLM MODE · sources only</span></div>",
                    unsafe_allow_html=True)
    else:
        st.markdown("<div class='mode-strip'><span class='long'>DEMO MODE · no LLM in use · every answer is copied word for word "
                    "from the fictional FastBox policies.</span><span class='short'>DEMO MODE · no LLM · quotes only</span></div>",
                    unsafe_allow_html=True)


def brand() -> None:
    st.markdown("<div class='brand'><span class='name'>RESOLVEAI</span>"
                "<span class='sub'>Counter 1 · FastBox support, a fictional delivery company</span></div>", unsafe_allow_html=True)


def zone(title: str) -> None:
    st.markdown(f"<div class='zone-title'>{esc(title)}</div>", unsafe_allow_html=True)


def notice(kind: str, title: str, text: str) -> None:
    st.markdown(f"<div class='notice {kind}'><b>{esc(title)}</b><br>{esc(text)}</div>", unsafe_allow_html=True)


def senha(ticket_id: int, big: bool = False) -> str:
    return f"<span class='senha{' big' if big else ''}'>A-{ticket_id:03d}</span>"


def seal_cat(intent: str) -> str:
    return f"<span class='seal cat'>{esc(intent.replace('_', ' '))}</span>"


def seal_status(status: str) -> str:
    glyph, label = STATUS[status]
    return f"<span class='seal {status}'>{glyph} {label}</span>"


def customer(t: dict) -> str:
    return f"<div class='cust'>{esc(t['message'])}<br><small>{esc(t['created'][11:16])} UTC · personal data masked</small></div>"


def answer(t: dict, selected: bool) -> str:
    body = esc(t["answer"])
    body = re.sub(r"\[(S\d+)\]", r"<sup class='cite'>\1</sup>", body)
    return (f"<div class='ans{' sel' if selected else ''}'><div class='meta'>{senha(t['id'])}{seal_cat(t['intent'])}"
            f"{seal_status(t['status'])}</div><div class='body'>{body}</div></div>")


def score_chip(score) -> str:
    """Retrieval score band. Bands are a UI heuristic (>=0.30 strong, >=0.15 medium), not a calibrated probability."""
    if score is None:
        return ""
    band = "strong" if score >= 0.30 else "medium" if score >= 0.15 else "weak"
    return f"<span class='chip'>match score {score:.2f} · {band}</span>"


def source_card(citation: dict, chunk_text: str, score) -> str:
    quote = esc(citation["quote"])
    full = esc(chunk_text).replace(quote, f"<mark>{quote}</mark>", 1)
    return (f"<div class='src'><div class='head'>[{esc(citation['label'])}] {esc(citation['title'])} › {esc(citation['heading'])}</div>"
            f"<div class='quote'><mark>{quote}</mark></div>{score_chip(score)}"
            f"<details><summary>Read the full passage</summary><p>{full}</p><span class='chip'>{esc(citation['chunk_id'])}</span></details></div>")


def details(t: dict, result) -> str:
    rows = ""
    if result is not None and result.retrieved:
        body = "".join(f"<tr><td>{esc(cid)}</td><td class='r'>{s:.3f}</td></tr>" for cid, s in result.retrieved)
        rows = (f"<div class='tbl-wrap'><table class='tbl'><thead><tr><th>retrieved passage</th><th class='r'>score</th></tr></thead>"
                f"<tbody>{body}</tbody></table></div>")
    rating = "not rated" if t["rating"] is None else ("helpful" if t["rating"] else "not helpful")
    return (f"<div>{senha(t['id'], big=True)}</div><div style='margin:.6rem 0'>{seal_cat(t['intent'])} {seal_status(t['status'])}</div>"
            f"<dl class='dl'><dt>Reason</dt><dd>{esc(t['reason'] or 'none')}</dd><dt>Answer mode</dt><dd>{esc(t['mode'])}</dd>"
            f"<dt>Agent review</dt><dd>{esc(REVIEW.get(t['review'], t['review']))}"
            f"{' · ' + esc(t['review_note']) if t['review_note'] else ''}</dd><dt>User rating</dt><dd>{rating}</dd>"
            f"<dt>Opened</dt><dd>{esc(t['created'].replace('T', ' '))} UTC</dd></dl>{rows}")


def hbars(data: dict) -> str:
    top = max(data.values()) if data and max(data.values()) else 1
    return "".join(f"<div class='hbar'><span>{esc(k.replace('_', ' '))}</span><div class='t'><i style='width:{v / top * 100:.0f}%'></i></div>"
                   f"<span class='n'>{v}</span></div>" for k, v in data.items())


def log_table(tickets) -> str:
    rows = "".join(f"<tr><td>A-{t['id']:03d}</td><td>{esc(t['created'][5:16].replace('T', ' '))}</td><td>{esc(t['intent'].replace('_', ' '))}</td>"
                   f"<td>{STATUS[t['status']][0]} {esc(STATUS[t['status']][1])}</td><td>{esc(REVIEW.get(t['review'], t['review']))}</td>"
                   f"<td>{esc(t['message'][:90])}</td></tr>" for t in tickets)
    head = "".join(f"<th>{h}</th>" for h in ["No.", "Opened (UTC)", "Category", "Status", "Review", "Message"])
    return f"<div class='tbl-wrap'><table class='tbl'><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>"
