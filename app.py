"""ResolveAI - support triage desk. Run: streamlit run app.py"""
import html

import streamlit as st

from resolveai import llm
from resolveai.agent import Agent
from resolveai.kb import KB_DIR, add_document, load_kb
from resolveai.store import Store

st.set_page_config(page_title="ResolveAI desk", page_icon="📦", layout="wide")

# Visual identity: cool paper, deep ink, ultramarine actions. Answers are "dispatch slips" with a
# status stamp that always carries an icon + text (never colour alone) and a source ledger below.
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@600;800&family=Public+Sans:wght@400;600&display=swap');
:root{--ink:#14212B;--paper:#FFFFFF;--line:#B9C4D0;--act:#2447D6;--ok:#1F6B45;--warn:#8A5A00;--stop:#A3213F}
html,body,[class*="css"]{font-family:'Public Sans',system-ui,sans-serif}
h1,h2,h3,.slip-head{font-family:'Bricolage Grotesque','Public Sans',sans-serif;letter-spacing:-.01em}
h1{font-weight:800;font-size:2.2rem;margin-bottom:.1rem}
.sub{color:#3C4C5A;margin:0 0 1rem}
.slip{background:var(--paper);border:1.5px solid var(--ink);border-radius:2px 14px 2px 14px;margin:.4rem 0 .6rem;max-width:760px}
.slip-head{display:flex;gap:.75rem;align-items:center;justify-content:space-between;flex-wrap:wrap;
  padding:.5rem .9rem;border-bottom:2px dashed var(--line);font-weight:800}
.stamp{border:2px solid currentColor;padding:.1rem .55rem;border-radius:3px;font-weight:800;transform:rotate(-1.5deg)}
.s-answered{color:var(--ok)}.s-no_evidence{color:var(--warn)}.s-escalated{color:var(--stop)}
.slip-body{padding:.7rem .9rem;line-height:1.55;white-space:pre-wrap}
.ledger{border-top:2px dashed var(--line);padding:.55rem .9rem;font-size:.9rem;color:#2C3B47}
.ledger b{color:var(--ink)}
.q{background:#DCE4F5;border-radius:14px 2px 14px 2px;padding:.55rem .9rem;margin:.6rem 0 .2rem auto;max-width:640px;width:fit-content}
a:focus-visible,button:focus-visible,input:focus-visible,textarea:focus-visible{outline:3px solid var(--act)!important;outline-offset:2px}
@media (max-width:640px){h1{font-size:1.7rem}.slip-head{padding:.45rem .7rem}.slip-body,.ledger{padding-left:.7rem;padding-right:.7rem}}
</style>""", unsafe_allow_html=True)

STATUS = {"answered": ("✓", "Answered from sources"), "no_evidence": ("?", "No evidence found"),
          "escalated": ("→", "Passed to a human agent")}
EXAMPLES = ["My order is 40 minutes late, what do I get?", "Can I cancel my order for free?",
            "An item is missing from my order", "How long does a refund take?"]


@st.cache_resource
def get_store() -> Store:
    return Store()


def build_agent() -> Agent:
    return Agent(load_kb())


if "agent" not in st.session_state:
    st.session_state.agent = build_agent()
    st.session_state.thread = []   # ticket ids shown in the chat
store, agent = get_store(), st.session_state.agent


def slip(t: dict) -> str:
    """HTML for one answer. Every dynamic value is escaped: messages and documents are untrusted."""
    icon, label = STATUS[t["status"]]
    ledger = "".join(f"<div><b>[{html.escape(c['label'])}]</b> {html.escape(c['title'])} › "
                     f"{html.escape(c['heading'])}: “{html.escape(c['quote'])}”</div>" for c in t["citations"])
    reason = f"<div><b>Why:</b> {html.escape(t['reason'])}</div>" if t["reason"] else ""
    return (f"<div class='slip'><div class='slip-head'><span>Ticket #{t['id']} · {html.escape(t['intent'].replace('_', ' '))}"
            f"</span><span class='stamp s-{t['status']}'>{icon} {label}</span></div>"
            f"<div class='slip-body'>{html.escape(t['answer'])}</div>"
            f"<div class='ledger'>{ledger or 'No sources cited.'}{reason}</div></div>")


def ask(question: str) -> None:
    result = agent.handle(question)
    st.session_state.thread.append(store.log(result))


st.title("ResolveAI desk")
st.markdown("<p class='sub'>Support triage for FastBox, a fictional delivery company. "
            "Answers come only from the policy sources; anything else goes to a person.</p>", unsafe_allow_html=True)
if llm.available():
    st.info("LLM mode: answers are written by the configured model from the retrieved sources, and are "
            "rejected in favour of verbatim excerpts if they cite anything else.")
else:
    st.info("Demo mode: no LLM is used. Answers are sentences copied word for word from the policy sources.")

tab_ask, tab_hist, tab_src, tab_rev, tab_admin = st.tabs(["Ask", "History", "Sources", "Review queue", "Admin"])

with tab_ask:
    st.caption("Do not enter card numbers or passwords. E-mails, phone and card numbers are masked before saving.")
    if not st.session_state.thread:
        st.markdown("**Start with a question** or pick an example:")
        cols = st.columns(len(EXAMPLES))
        for col, ex in zip(cols, EXAMPLES):
            if col.button(ex, key=f"ex-{ex}", width="stretch"):
                ask(ex)
                st.rerun()
    for tid in st.session_state.thread:
        t = store.tickets("WHERE id=?", (tid,))[0]
        st.markdown(f"<div class='q'>{html.escape(t['message'])}</div>", unsafe_allow_html=True)
        st.markdown(slip(t), unsafe_allow_html=True)
        if t["rating"] is None:
            a, b, _ = st.columns([1, 1, 4])
            if a.button("Helpful", key=f"up-{tid}"):
                store.rate(tid, True); st.rerun()
            if b.button("Not helpful", key=f"down-{tid}"):
                store.rate(tid, False); st.rerun()
        else:
            st.caption("Thanks for rating: " + ("helpful" if t["rating"] else "not helpful"))
    if question := st.chat_input("Ask about a delivery, cancellation or refund"):
        ask(question)
        st.rerun()

with tab_hist:
    tickets = store.tickets()
    if not tickets:
        st.info("No tickets yet. Ask a question in the Ask tab and it will appear here.")
    else:
        f1, f2 = st.columns(2)
        intents = f1.multiselect("Category", sorted({t["intent"] for t in tickets}))
        statuses = f2.multiselect("Status", ["answered", "no_evidence", "escalated"])
        shown = [t for t in tickets if (not intents or t["intent"] in intents) and (not statuses or t["status"] in statuses)]
        st.dataframe([{"#": t["id"], "when (UTC)": t["created"], "category": t["intent"], "status": t["status"],
                       "review": t["review"], "message": t["message"]} for t in shown], hide_index=True, width="stretch")

with tab_src:
    st.write(f"{len(agent.chunks)} passages from {len({c.doc for c in agent.chunks})} documents. Fictional content.")
    if agent.dropped:
        st.warning(f"Ignored {len(agent.dropped)} passage(s) that look like instructions to the model: "
                   + ", ".join(agent.dropped))
    for doc in sorted({c.doc for c in agent.chunks}):
        group = [c for c in agent.chunks if c.doc == doc]
        with st.expander(f"{group[0].title}  ({group[0].category})"):
            for c in group:
                st.markdown(f"**{c.heading}** `{c.id}`  \n{c.text}")
    st.subheader("Add or update a document")
    up = st.file_uploader("Markdown file with '# Title', 'Category: refund' and '## Section' headings", type="md")
    if up is not None and st.button("Add to knowledge base"):
        try:
            added = add_document(up.name, up.getvalue().decode("utf-8"), KB_DIR)
            st.session_state.agent = build_agent()
            st.success(f"Added {len(added)} passages from {up.name}.")
            st.rerun()
        except (ValueError, UnicodeDecodeError) as exc:
            st.error(f"Could not add the document: {exc}")

with tab_rev:
    pending = store.tickets("WHERE review='pending'")
    if not pending:
        st.info("Nothing waiting for review. Escalated and unanswered tickets show up here.")
    for t in pending:
        with st.container(border=True):
            st.markdown(f"**Ticket #{t['id']}** · {t['intent']} · {STATUS[t['status']][0]} {STATUS[t['status']][1]}")
            st.text(t["message"])
            st.caption(f"Reason: {t['reason'] or 'n/a'}")
            note = st.text_input("Note for the record", key=f"note-{t['id']}")
            a, b, c = st.columns(3)
            for col, decision in zip((a, b, c), ("approved", "corrected", "rejected")):
                if col.button(decision.capitalize(), key=f"{decision}-{t['id']}"):
                    store.review(t["id"], decision, note); st.rerun()

with tab_admin:
    s = store.stats()
    if not s["total"]:
        st.info("No data yet. Indicators appear after the first question.")
    else:
        m = st.columns(4)
        m[0].metric("Tickets", s["total"])
        m[1].metric("Escalation rate", f"{s['escalation_rate'] * 100:.0f}%")
        m[2].metric("Waiting for review", s["pending_review"])
        m[3].metric("Rated helpful", "n/a" if s["helpful_rate"] is None else f"{s['helpful_rate'] * 100:.0f}% of {s['rated']}")
        l, r = st.columns(2)
        l.write("By category"); l.bar_chart(s["by_intent"])
        r.write("By status"); r.bar_chart(s["by_status"])
