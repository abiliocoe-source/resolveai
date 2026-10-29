"""ResolveAI - support counter. Run: streamlit run app.py"""
from pathlib import Path

import streamlit as st

import ui
from resolveai import llm
from resolveai.agent import Agent
from resolveai.kb import KB_DIR, add_document, load_kb
from resolveai.store import Store

st.set_page_config(page_title="Counter 1 · ResolveAI", page_icon=str(Path(__file__).parent / "assets" / "favicon.png"),
                   layout="wide", initial_sidebar_state="collapsed")
ui.inject_css()

EXAMPLES = ["My order is 40 minutes late, what do I get?", "Can I cancel my order for free?",
            "An item is missing from my order", "How long does a refund take?"]


@st.cache_resource
def get_store() -> Store:
    return Store()


def build_agent() -> Agent:
    return Agent(load_kb())


if "agent" not in st.session_state:
    st.session_state.agent = build_agent()
    st.session_state.thread = []    # ticket ids of this visit, oldest first
    st.session_state.results = {}   # ticket id -> agent Result (keeps retrieval scores for this session)
    st.session_state.sel = None     # ticket shown in the sources and details zones
store, agent = get_store(), st.session_state.agent
by_chunk = {c.id: c for c in agent.chunks}


def ask(question: str) -> None:
    result = agent.handle(question)
    tid = store.log(result)
    st.session_state.thread.append(tid)
    st.session_state.results[tid] = result
    st.session_state.sel = tid


ui.mode_strip(llm.available())
ui.brand()
tab_ask, tab_log, tab_lib, tab_rev, tab_admin = st.tabs(["Counter", "Ticket log", "Library", "Review desk", "Dashboard"])

with tab_ask:
    conv, srcs, info = st.columns([3.1, 2.4, 2.0])
    sel = st.session_state.sel
    selected = store.tickets("WHERE id=?", (sel,))[0] if sel else None

    with conv:
        ui.zone("Conversation")
        if not st.session_state.thread:
            ui.notice("empty", "Nobody at the counter yet.", "Take a number: type a question below, or start with one of these. "
                      "E-mails, phone and card numbers are masked before saving. Do not type passwords.")
            for ex in EXAMPLES:
                if st.button(ex, key=f"ex-{ex}", width="stretch"):
                    ask(ex); st.rerun()
        for tid in st.session_state.thread:
            t = store.tickets("WHERE id=?", (tid,))[0]
            st.markdown(ui.customer(t) + ui.answer(t, tid == sel), unsafe_allow_html=True)
            if tid != sel and st.button(f"Open case A-{tid:03d}", key=f"open-{tid}"):
                st.session_state.sel = tid; st.rerun()
        if question := st.chat_input("Ask about a delivery, cancellation or refund"):
            ask(question); st.rerun()

    with srcs:
        ui.zone("Sources")
        if selected is None:
            ui.notice("empty", "No case open.", "Ask something and the passages behind the answer appear here, with the quoted sentence highlighted.")
        elif not selected["citations"]:
            ui.notice("empty", "Nothing cited.", "This case was not answered from sources, so there is no passage to show. See the reason on the right.")
        else:
            res = st.session_state.results.get(sel)
            scores = dict(res.retrieved) if res else {}
            for c in selected["citations"]:
                chunk = by_chunk.get(c["chunk_id"])
                st.markdown(ui.source_card(c, chunk.text if chunk else c["quote"], scores.get(c["chunk_id"])), unsafe_allow_html=True)
            st.caption("Match score: how closely the passage matches the question (TF-IDF cosine). Bands are a rule of thumb.")

    with info:
        ui.zone("Case details")
        if selected is None:
            ui.notice("empty", "No case open.", "Number, category, status, reason and review state show here.")
        else:
            st.markdown(ui.details(selected, st.session_state.results.get(sel)), unsafe_allow_html=True)
            if selected["rating"] is None:
                st.write("Was this answer useful?")
                a, b = st.columns(2)
                if a.button("Helpful", key=f"up-{sel}", width="stretch"):
                    store.rate(sel, True); st.rerun()
                if b.button("Not helpful", key=f"down-{sel}", width="stretch"):
                    store.rate(sel, False); st.rerun()

with tab_log:
    tickets = store.tickets()
    if not tickets:
        ui.notice("empty", "The log is empty.", "Every question taken at the counter is listed here, newest first.")
    else:
        f1, f2 = st.columns(2)
        intents = f1.multiselect("Category", sorted({t["intent"] for t in tickets}))
        statuses = f2.multiselect("Status", ["answered", "no_evidence", "escalated"],
                                  format_func=lambda s: ui.STATUS[s][1])
        shown = [t for t in tickets if (not intents or t["intent"] in intents) and (not statuses or t["status"] in statuses)]
        if shown:
            st.markdown(ui.log_table(shown), unsafe_allow_html=True)
        else:
            ui.notice("empty", "No tickets match.", "Clear a filter to see more.")

with tab_lib:
    ui.zone(f"{len(agent.chunks)} passages · {len({c.doc for c in agent.chunks})} documents · fictional content")
    if agent.dropped:
        ui.notice("error", "Passages ignored.", "These look like instructions to the model, so they are never used: " + ", ".join(agent.dropped))
    for doc in sorted({c.doc for c in agent.chunks}):
        group = [c for c in agent.chunks if c.doc == doc]
        with st.expander(f"{group[0].title} · {group[0].category.replace('_', ' ')}"):
            for c in group:
                st.markdown(f"**{c.heading}** `{c.id}`  \n{c.text}")
    ui.zone("Add or replace a document")
    up = st.file_uploader("Markdown file: '# Title', 'Category: refund', then '## Section' headings", type="md")
    if up is not None and st.button("Add to library"):
        try:
            added = add_document(up.name, up.getvalue().decode("utf-8"), KB_DIR)
            st.session_state.agent = build_agent()
            ui.notice("ok", "Document filed.", f"{len(added)} passages added from {up.name}.")
            st.rerun()
        except (ValueError, UnicodeDecodeError) as exc:
            ui.notice("error", "Document refused.", str(exc))

with tab_rev:
    pending = store.tickets("WHERE review='pending'")
    if not pending:
        ui.notice("empty", "Review desk is clear.", "Cases sent to an agent, or left without a source, wait here.")
    for t in pending:
        with st.container(border=True):
            st.markdown(ui.senha(t["id"]) + " " + ui.seal_cat(t["intent"]) + " " + ui.seal_status(t["status"]), unsafe_allow_html=True)
            st.markdown(f"<div class='cust'>{ui.esc(t['message'])}</div>", unsafe_allow_html=True)
            st.caption(f"Reason: {t['reason'] or 'n/a'}")
            note = st.text_input("Note for the record", key=f"note-{t['id']}")
            cols = st.columns(3)
            for col, decision in zip(cols, ("approved", "corrected", "rejected")):
                if col.button(decision.capitalize(), key=f"{decision}-{t['id']}", width="stretch"):
                    store.review(t["id"], decision, note); st.rerun()

with tab_admin:
    s = store.stats()
    if not s["total"]:
        ui.notice("empty", "No numbers yet.", "Indicators start counting from the first ticket.")
    else:
        m = st.columns(4)
        for col, label, value, unit in [
                (m[0], "tickets taken", f"{s['total']}", ""),
                (m[1], "passed to an agent", f"{s['escalation_rate'] * 100:.0f}", "%"),
                (m[2], "waiting for review", f"{s['pending_review']}", ""),
                (m[3], "rated helpful", "n/a" if s["helpful_rate"] is None else f"{s['helpful_rate'] * 100:.0f}",
                 "" if s["helpful_rate"] is None else f"% of {s['rated']}")]:
            col.markdown(f"<div class='kpi-l'>{label}</div><div class='big'>{value}<small>{unit}</small></div>", unsafe_allow_html=True)
        l, r = st.columns(2)
        with l:
            ui.zone("By category")
            st.markdown(ui.hbars(s["by_intent"]), unsafe_allow_html=True)
        with r:
            ui.zone("By status")
            st.markdown(ui.hbars({ui.STATUS[k][1]: v for k, v in s["by_status"].items()}), unsafe_allow_html=True)
