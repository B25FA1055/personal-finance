"""Chat with an AI financial coach about your own (aggregated) data."""

from datetime import date

import streamlit as st

from core.ai_coach import build_context, rule_based_answer
from core.i18n import current_language, t
from core.ui import engine, page

page("nav_ai", "🤖")

db = engine()
with db.begin() as conn:  # build_context marks the transaction READ ONLY
    context = build_context(conn, date.today(), current_language())

st.caption(t("ai_mode_local"))
with st.expander(t("ai_shared_data")):
    st.json(context, expanded=False)

history: list[dict[str, str]] = st.session_state.setdefault("coach_messages", [])

suggestion = None
with st.container(horizontal=True):
    for key in ("ai_suggest_top", "ai_suggest_food", "ai_suggest_savings", "ai_suggest_budget"):
        if st.button(t(key), key=f"suggest_{key}"):
            suggestion = t(key)
    if history and st.button(t("ai_clear"), key="coach_clear", icon=":material/delete:"):
        history.clear()
        st.rerun()

for message in history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

question = st.chat_input(t("ai_placeholder")) or suggestion
if question:
    history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        answer = rule_based_answer(question, context)
        st.markdown(answer)
    history.append({"role": "assistant", "content": str(answer)})
