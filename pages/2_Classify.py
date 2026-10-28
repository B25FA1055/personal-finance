"""Review automatic classifications and assign categories manually."""

import pandas as pd
import streamlit as st

from core.classify_service import (
    assign_group,
    classification_transactions,
    set_transaction_categories,
    unclassified_counts,
    unclassified_groups,
)
from core.i18n import category_name, t
from core.ui import category_options, engine, page

page("classify_title", "🏷️")

db = engine()
if flash := st.session_state.pop("classify_flash", None):
    st.success(flash)

search = st.text_input(t("classify_search"))
with db.connect() as conn:
    pending, group_count = unclassified_counts(conn)
    groups = unclassified_groups(conn)
    transactions = classification_transactions(conn, search=search)
    categories = category_options(conn)

# Labels are translated, so the editors work with labels and map back to ids.
label_to_id = {label: category_id for category_id, label in categories}
id_to_label = {category_id: label for category_id, label in categories}
type_labels = {code: t(f"type_{code}") for code in ("pos", "qpay", "transfer", "fee", "cash", "other")}
source_labels = {
    "Automatic rule": t("src_rule"),
    "Automatic default": t("src_merchant"),
    "Manual": t("src_manual"),
    "Unclassified": t("src_none"),
}

tabs = st.tabs([t("tab_transactions"), t("tab_review", count=int(pending))])
with tabs[0]:
    st.caption(t("classify_showing", count=f"{transactions.shape[0]:,}"))
    if transactions.empty:
        st.info(t("classify_no_match"))
    elif not categories:
        st.warning(t("classify_no_categories"))
    else:
        original_ids = {
            int(row.id): None if pd.isna(row.category_id) else int(row.category_id)
            for row in transactions.itertuples()
        }
        editable = pd.DataFrame(
            {
                "id": transactions["id"],
                "date": transactions["date"],
                "merchant": transactions["merchant"],
                "description": transactions["description"],
                "txn_type": transactions["txn_type"].map(type_labels).fillna(transactions["txn_type"]),
                "amount": transactions["amount"].astype(float),
                "category": [id_to_label.get(original_ids[int(i)]) for i in transactions["id"]],
                "classified_by": transactions["classified_by"].map(source_labels),
            }
        )
        changed = st.data_editor(
            editable,
            hide_index=True,
            width="stretch",
            key=f"transactions_{st.session_state.get('transaction_version', 0)}",
            disabled=[column for column in editable.columns if column != "category"],
            column_config={
                "id": None,
                "date": st.column_config.DateColumn(t("col_date")),
                "merchant": t("col_merchant"),
                "description": t("col_description"),
                "txn_type": t("col_type"),
                "amount": st.column_config.NumberColumn(
                    t("col_amount"), format="localized", step=1
                ),
                "category": st.column_config.SelectboxColumn(
                    t("col_category"), options=list(label_to_id), required=False
                ),
                "classified_by": t("col_source"),
            },
        )
        if st.button(t("classify_save"), type="primary"):
            category_changes = {
                int(row.id): label_to_id[row.category]
                for row in changed.itertuples()
                if pd.notna(row.category)
                and label_to_id[row.category] != original_ids[int(row.id)]
            }
            if not category_changes:
                st.info(t("classify_no_changes"))
            else:
                with db.begin() as conn:
                    updated = set_transaction_categories(conn, category_changes)
                st.session_state["classify_flash"] = t("classify_updated", count=updated)
                st.session_state["transaction_version"] = (
                    st.session_state.get("transaction_version", 0) + 1
                )
                st.rerun()

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
