"""Review automatic classifications and assign categories manually."""

import pandas as pd
import streamlit as st

from core.classify_service import (
    CATEGORY_KINDS,
    SOURCE_FILTERS,
    assign_group,
    classification_transactions,
    create_category,
    main_categories,
    unclassified_counts,
    unclassified_groups,
)
from core.i18n import category_name, t
from core.ui import category_editor, category_options, engine, page

page("classify_title", "🏷️")

db = engine()
if flash := st.session_state.pop("classify_flash", None):
    st.success(flash, icon=":material/check_circle:")

with db.connect() as conn:
    mains = main_categories(conn)

# Toolbar: search, which rows to show, and a new custom category.
with st.container(horizontal=True, vertical_alignment="bottom", key="classify_toolbar"):
    search = st.text_input(t("classify_search"), width=320)
    source = st.segmented_control(
        t("classify_filter"), SOURCE_FILTERS, default="all",
        format_func=lambda code: t(f"classify_filter_{code}"),
    ) or "all"
    with st.popover(t("cat_new"), icon=":material/add:"):
        # A new main category per kind, or a subcategory under an existing main one.
        placements = [(None, kind) for kind in CATEGORY_KINDS] + [(cid, kind) for cid, kind, _ in mains]
        main_names = {cid: name for cid, _, name in mains}
        with st.form("new_category", clear_on_submit=True, border=False):
            new_name = st.text_input(t("cat_name"), max_chars=60)
            parent_id, kind = st.selectbox(
                t("cat_place"), placements,
                format_func=lambda p: t("cat_new_main", kind=t(f"kind_{p[1]}")) if p[0] is None
                else f"{t('kind_' + p[1])} · {category_name(main_names[p[0]])} › …",
            )
            create = st.form_submit_button(t("cat_create"), type="primary")
        if create:
            try:
                with db.begin() as conn:
                    create_category(conn, new_name, kind, parent_id)
            except ValueError as exc:
                st.error(t(str(exc)))
            else:
                st.session_state["classify_flash"] = t("cat_created", name=" ".join(new_name.split()))
                st.rerun()

with db.connect() as conn:
    pending, group_count = unclassified_counts(conn)
    groups = unclassified_groups(conn)
    transactions = classification_transactions(conn, search=search, source=source)
    categories = category_options(conn)

# Labels are translated, so the editors work with labels and map back to ids.
label_to_id = {label: category_id for category_id, label in categories}
type_labels = {code: t(f"type_{code}") for code in ("pos", "qpay", "transfer", "fee", "cash", "other")}

tabs = st.tabs([t("tab_transactions"), t("tab_review", count=int(pending))])
with tabs[0]:
    st.caption(t("classify_showing", count=f"{transactions.shape[0]:,}"))
    if transactions.empty:
        st.info(t("classify_no_match"))
    elif not categories:
        st.warning(t("classify_no_categories"))
    else:
        category_editor(transactions, categories, key="classify_editor", flash_key="classify_flash")

with tabs[1]:
    if not pending:
        st.success(t("review_nothing"))
    else:
        st.write(t("review_intro", count=int(pending), groups=group_count, other=category_name("Бусад")))

        table = groups.drop(columns=["merchant_id"]).assign(
            txn_type=groups["txn_type"].map(type_labels).fillna(groups["txn_type"]),
            direction=groups["direction"].map({"in": t("dir_in"), "out": t("dir_out")}),
            total=groups["total"].astype(float),
            category=None,
            remember=True,
        )
        edited = st.data_editor(
            table,
            hide_index=True,
            width="stretch",
            key=f"groups_{st.session_state.get('classify_version', 0)}",
            disabled=[column for column in table.columns if column not in ("category", "remember")],
            column_config={
                "merchant": t("col_merchant"),
                "txn_type": t("col_type"),
                "direction": t("col_direction"),
                "count": t("col_count"),
                "total": st.column_config.NumberColumn(
                    t("col_total"), format="localized", step=1
                ),
                "first_date": st.column_config.DateColumn(t("col_first")),
                "last_date": st.column_config.DateColumn(t("col_last")),
                "example": t("col_example"),
                "category": st.column_config.SelectboxColumn(
                    t("col_category"), options=list(label_to_id), required=False
                ),
                "remember": st.column_config.CheckboxColumn(
                    t("col_remember"), help=t("remember_help")
                ),
            },
        )

        if st.button(t("review_save"), type="primary"):
            chosen = edited[edited["category"].notna()]
            if chosen.empty:
                st.warning(t("review_pick_one"))
            else:
                rows_saved = rules_saved = 0
                with db.begin() as conn:
                    for index, row in chosen.iterrows():
                        merchant_id = groups.at[index, "merchant_id"]
                        rows, rule_saved = assign_group(
                            conn,
                            None if pd.isna(merchant_id) else int(merchant_id),
                            groups.at[index, "direction"],
                            label_to_id[row["category"]],
                            bool(row["remember"]),
                        )
                        rows_saved += rows
                        rules_saved += rule_saved
                st.session_state["classify_flash"] = t(
                    "review_saved", rows=rows_saved, rules=rules_saved
                )
                st.session_state["classify_version"] = (
                    st.session_state.get("classify_version", 0) + 1
                )
                st.rerun()
