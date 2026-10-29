"""ResolveAI - support queue. Run: streamlit run app.py"""
from pathlib import Path

import streamlit as st

import ui
from resolveai import llm
from resolveai.agent import Agent
from resolveai.kb import KB_DIR, add_document, load_kb
from resolveai.store import Store

st.set_page_config(page_title="Queue · ResolveAI", page_icon=str(Path(__file__).parent / "assets" / "favicon.png"), layout="wide")
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
    st.session_state.results = {}   # ticket id -> agent Result (keeps retrieval scores for this visit)
    st.session_state.sel = None     # the open case
    st.session_state.qv = 0         # bumps when a new case is opened, so the queue list re-selects it
store, agent = get_store(), st.session_state.agent
by_chunk = {c.id: c for c in agent.chunks}


def ask(question: str) -> None:
    result = agent.handle(question)
    tid = store.log(result)
    st.session_state.results[tid] = result
    st.session_state.sel = tid
    st.session_state.qv += 1


ui.mode_strip(llm.available())
stats = store.stats()
with st.sidebar:
    ui.brand("FastBox support, fictional")
    ui.waiting(stats["pending_review"])
    st.caption("E-mails, phone and card numbers are masked before a case is saved. Do not type passwords.")

if stats["total"]:
    answered = stats["by_status"]["answered"]
    finding = (f"<b>{stats['pending_review']} of {stats['total']} cases</b> wait for an agent. "
               f"{answered} {'was' if answered == 1 else 'were'} answered from the sources.")
else:
    finding = "No case has been opened yet."
ui.title("Support desk", finding)

tab_q, tab_r, tab_l, tab_d = st.tabs(["Queue", "Review desk", "Library", "Dashboard"])

with tab_q:
    left, middle, right = st.columns([1.15, 2.0, 1.1])
    tickets = store.tickets()
    by_id = {t["id"]: t for t in tickets}
    with left:
        ui.region("Cases", f"{len(tickets)} in the log")
        view = st.segmented_control("Show", ["All", "Needs an agent"], default="All", key="view", label_visibility="collapsed")
        shown = tickets if view in (None, "All") else [t for t in tickets if t["review"] == "pending"]
        if not tickets:
            ui.note("empty", "The queue is empty.", "Questions asked at this desk are listed here, newest first.")
        elif not shown:
            ui.note("empty", "Nothing waits for an agent.", "Every open case was answered from the sources.")
        else:
            ids = [t["id"] for t in shown]
            current = st.session_state.sel
            choice = st.radio("Cases", ids, index=ids.index(current) if current in ids else 0, key=f"q-{st.session_state.qv}-{view}",
                              format_func=lambda i: ui.row_label(by_id[i]), label_visibility="collapsed")
            st.session_state.sel = choice
    sel = st.session_state.sel
    selected = by_id.get(sel)

    with middle:
        ui.region("Case", "question, answer and the passages behind it")
        if selected is None:
            ui.note("empty", "No case open.", "Ask a question below, or start from one of these.")
            for ex in EXAMPLES:
                if st.button(ex, key=f"ex-{ex}", width="stretch"):
                    ask(ex)
                    st.rerun()
        else:
            st.markdown(ui.case_view(selected), unsafe_allow_html=True)
            st.markdown("<div class='sec-h'>Sources</div>", unsafe_allow_html=True)
            if not selected["citations"]:
                ui.note("empty", "Nothing cited.", "This case was not answered from the sources, so there is no passage to show. The reason is in the details.")
            else:
                scores = dict(st.session_state.results[sel].retrieved) if sel in st.session_state.results else {}
                for c in selected["citations"]:
                    chunk = by_chunk.get(c["chunk_id"])
                    st.markdown(ui.source_card(c, chunk.text if chunk else c["quote"], scores.get(c["chunk_id"])), unsafe_allow_html=True)
                st.markdown("<div class='hint'>Match score is the TF-IDF similarity between the question and the passage. The bands are a rule of thumb.</div>",
                            unsafe_allow_html=True)
        if question := st.chat_input("Ask about a delivery, a cancellation or a refund"):
            ask(question)
            st.rerun()

    with right:
        ui.region("Details")
        if selected is None:
            ui.note("empty", "No case open.", "Reason, review state and rating show here.")
        else:
            st.markdown(ui.details(selected, st.session_state.results.get(sel)), unsafe_allow_html=True)
            if selected["rating"] is None:
                st.markdown("<div class='hint'>Was this answer useful?</div>", unsafe_allow_html=True)
                a, b = st.columns(2)
                if a.button("Helpful", key=f"up-{sel}", width="stretch"):
                    store.rate(sel, True)
                    st.rerun()
                if b.button("Not helpful", key=f"down-{sel}", width="stretch"):
                    store.rate(sel, False)
                    st.rerun()

with tab_r:
    pending = store.tickets("WHERE review='pending'")
    ui.region("Review desk", f"{len(pending)} waiting")
    if not pending:
        ui.note("empty", "Nobody is waiting.", "Cases passed to an agent, or left without a source, show up here.")
    for t in pending:
        with st.container(border=True):
            st.markdown(ui.ticket(t["id"]) + " " + ui.pills(t), unsafe_allow_html=True)
            st.markdown(f"<div class='said' style='margin-top:12px'>{ui.esc(t['message'])}</div>", unsafe_allow_html=True)
            st.caption(f"Reason: {t['reason'] or 'none'}")
            note = st.text_input("Note for the record", key=f"note-{t['id']}")
            cols = st.columns(3)
            for col, decision in zip(cols, ("approved", "corrected", "rejected")):
                if col.button(decision.capitalize(), key=f"{decision}-{t['id']}", width="stretch"):
                    store.review(t["id"], decision, note)
                    st.rerun()

with tab_l:
    ui.region("Library", f"{len(agent.chunks)} passages in {len({c.doc for c in agent.chunks})} documents, fictional")
    if agent.dropped:
        ui.note("error", "Passages ignored.", "They look like instructions to the model, so they are never used: " + ", ".join(agent.dropped))
    for doc in sorted({c.doc for c in agent.chunks}):
        group = [c for c in agent.chunks if c.doc == doc]
        with st.expander(f"{group[0].title} · {group[0].category.replace('_', ' ')}"):
            for c in group:
                st.markdown(f"**{c.heading}** `{c.id}`  \n{c.text}")
    st.markdown("<div class='sec-h'>Add or replace a document</div>", unsafe_allow_html=True)
    up = st.file_uploader("Markdown file with a title, a Category line and ## sections", type="md", label_visibility="collapsed")
    if up is not None and st.button("Add to library", type="primary"):
        try:
            added = add_document(up.name, up.getvalue().decode("utf-8"), KB_DIR)
            st.session_state.agent = build_agent()
            ui.note("ok", "Document filed.", f"{len(added)} passages added from {up.name}.")
            st.rerun()
        except (ValueError, UnicodeDecodeError) as exc:
            ui.note("error", "Document refused.", str(exc))

with tab_d:
    ui.region("Dashboard", "all cases in the log")
    if not stats["total"]:
        ui.note("empty", "No numbers yet.", "Indicators count from the first case.")
    else:
        helpful = "n/a" if stats["helpful_rate"] is None else f"{stats['helpful_rate'] * 100:.0f}"
        st.markdown(ui.kpi_strip([("Cases taken", f"{stats['total']}", ""), ("Passed to an agent", f"{stats['escalation_rate'] * 100:.0f}", "%"),
                                  ("Waiting for review", f"{stats['pending_review']}", ""),
                                  ("Rated helpful", helpful, "" if stats["helpful_rate"] is None else f"% of {stats['rated']}")]), unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("<div class='sec-h'>By category</div>" + ui.hbars(stats["by_intent"]), unsafe_allow_html=True)
        with c2:
            st.markdown("<div class='sec-h'>By status</div>" + ui.hbars({ui.STATUS[k]: v for k, v in stats["by_status"].items()}), unsafe_allow_html=True)
