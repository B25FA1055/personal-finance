"""Upload bank statements (.xlsx) or scan receipt photos."""

import os
import tempfile
from datetime import date
from pathlib import Path
from decimal import Decimal

import streamlit as st

from core import reports
from core.budget_service import expense_categories, import_months
from core.classify_service import unclassified_counts
from core.i18n import category_name, t
from core.importer import BANK_NAMES, import_file
from core.parsers import BANK_CODES, UnknownBankError
from core.receipt_ocr import receipt_ref
from core.receipt_service import possible_duplicates, receipt_saved, save_receipt
from core.ui import engine, fmt_mnt, page, show_budget_alerts

page("nav_upload", "📤")

db = engine()
if flash := st.session_state.pop("upload_flash", None):
    st.success(flash)

tab_statements, tab_receipt = st.tabs([t("tab_statements"), t("tab_receipt")])

# --- Bank statements ----------------------------------------------------------------
with tab_statements:
    files = st.file_uploader(
        t("upload_drop"),
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
    )
    bank_code = st.selectbox(
        t("upload_bank"),
        [None, *BANK_CODES],
        format_func=lambda code: t("upload_bank_auto") if code is None else BANK_NAMES[code],
        help=t("upload_bank_help"),
    )

    if st.button(t("upload_button"), type="primary", disabled=not files):
        imported_ids: list[int] = []
        for uploaded in files:
            # Keep the extension: it decides how the file is read (.xlsx/.xls/.csv).
            fd, tmp_path = tempfile.mkstemp(suffix=Path(uploaded.name).suffix.lower())
            try:
                with os.fdopen(fd, "wb") as tmp:
                    tmp.write(uploaded.getbuffer())
                result = import_file(tmp_path, uploaded.name, db, bank_code)
            except UnknownBankError:
                st.error(t("upload_unknown_bank", file=uploaded.name))
                continue
            except Exception as exc:  # one bad file must not stop the others
                st.error(f"'{uploaded.name}': {exc}")
                continue
            finally:
                os.unlink(tmp_path)

            if result.duplicate_file:
                st.info(t("upload_duplicate", file=uploaded.name))
            else:
                imported_ids.append(result.import_id)
                st.success(
                    t(
                        "upload_success",
                        file=uploaded.name,
                        inserted=result.inserted,
                        skipped=result.skipped,
                        review=result.unclassified,
                    )
                )
                if result.gap_from:
                    st.warning(t("upload_gap", start=result.gap_from, end=result.gap_to))
                if result.opening_mismatch:
                    st.warning(t("upload_opening_mismatch", file=uploaded.name))

        with db.connect() as conn:
            pending, groups = unclassified_counts(conn)
            months = import_months(conn, imported_ids)
        if pending:
            st.warning(t("upload_pending", count=int(pending), groups=groups))
            st.page_link("pages/2_Classify.py", label=t("upload_go_classify"), icon="🏷️")
        # Warn right away if the new transactions pushed any budget near or over its limit.
        with db.connect() as conn:
            for month in months:
                show_budget_alerts(conn, month)

    st.subheader(t("upload_history"))
    with db.connect() as conn:
        history = reports.import_history(conn)

    if history.empty:
        st.caption(t("upload_no_history"))
    else:
        st.dataframe(
            history,
            hide_index=True,
            width="stretch",
            column_config={
                "file": t("col_file"),
                "bank": t("col_bank"),
                "account": t("col_account"),
                "period_start": t("col_period_start"),
                "period_end": t("col_period_end"),
                "rows_read": t("col_rows_read"),
                "rows_inserted": t("col_rows_inserted"),
                "imported_at": st.column_config.DatetimeColumn(
                    t("col_imported_at"), format="YYYY-MM-DD HH:mm"
                ),
            },
        )

# --- Receipt photo ---------------------------------------------------------------
with tab_receipt:
    st.caption(t("receipt_intro_manual"))
    version = st.session_state.get("receipt_uploader_version", 0)
    image = st.file_uploader(
        t("receipt_upload"), type=["png", "jpg", "jpeg"], key=f"receipt_file_{version}"
    )

    if image is not None:
        data = image.getvalue()
        ref = receipt_ref(data)
        with db.connect() as conn:
            already_saved = receipt_saved(conn, ref)

        left, right = st.columns([1, 2], gap="large")
        left.image(data, caption=image.name)

        with right:
            if already_saved:
                st.info(t("receipt_already_saved"))
            else:
                with db.connect() as conn:
                    categories = expense_categories(conn)
                category_names = {cid: category_name(name) for cid, name in categories}
                category_ids: list[int | None] = [None, *category_names]

                with st.form(f"receipt_form_{ref}"):
                    txn_date = st.date_input(
                        t("col_date"), value=date.today(),
                        max_value=date.today(), format="YYYY-MM-DD",
                    )
                    merchant = st.text_input(t("col_merchant"))
                    amount = st.number_input(
                        t("receipt_total"), min_value=0.0, step=100.0, format="%.2f",
                    )
                    category_id = st.selectbox(
                        t("col_category"),
                        category_ids,
                        format_func=lambda cid: t("receipt_auto_category") if cid is None else category_names[cid],
                    )
                    note = st.text_input(t("receipt_note"))
                    confirm = st.checkbox(t("receipt_confirm_duplicate"), help=t("receipt_duplicate_help"))
                    submitted = st.form_submit_button(t("receipt_save"), type="primary")

                if submitted:
                    total = Decimal(str(amount)).quantize(Decimal("0.01"))
                    if not merchant.strip() or total <= 0:
                        st.warning(t("receipt_missing"))
                    else:
                        with db.connect() as conn:
                            duplicates = possible_duplicates(conn, txn_date, total)
                        if duplicates and not confirm:
                            st.warning(t("receipt_duplicate_found", amount=fmt_mnt(total)))
                            for dup in duplicates:
                                st.caption(f"{dup['date']} · {dup['description']} · {fmt_mnt(dup['amount'])}")
                        else:
                            with db.begin() as conn:
                                save_receipt(
                                    conn, ref=ref, txn_date=txn_date, merchant=merchant,
                                    total=total, category_id=category_id, note=note,
                                )
                            st.session_state["receipt_uploader_version"] = version + 1
                            st.session_state["upload_flash"] = t(
                                "receipt_saved", merchant=merchant.strip(), amount=fmt_mnt(total)
                            )
                            st.rerun()
