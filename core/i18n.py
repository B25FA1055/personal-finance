"""UI texts in Mongolian and English, plus the sidebar language switcher."""

from collections.abc import Iterable
from typing import Any

import streamlit as st

LANGUAGES: dict[str, str] = {"mn": "Монгол", "en": "English"}
DEFAULT_LANGUAGE = "mn"

# Plain session key (not a widget key) so the choice survives page switches.
_STATE_KEY = "lang"
_WIDGET_KEY = "_lang_selector"

TEXTS: dict[str, dict[str, str]] = {
    # --- common / navigation -------------------------------------------------
    "nav_home": {"mn": "Нүүр", "en": "Home"},
    "nav_upload": {"mn": "Хуулга оруулах", "en": "Upload statements"},
    "nav_classify": {"mn": "Ангилал", "en": "Classify"},
    "nav_reports": {"mn": "Тайлан", "en": "Reports"},
    "nav_budget": {"mn": "Төсөв ба зорилго", "en": "Budget & Goals"},
    "nav_ai": {"mn": "Санхүүгийн зөвлөх", "en": "Financial Coach"},
    "nav_recurring": {"mn": "Тогтмол төлбөр", "en": "Recurring bills"},
    "language": {"mn": "Хэл", "en": "Language"},
    "theme": {"mn": "Өнгөний загвар", "en": "Theme"},
    "theme_light": {"mn": "Цайвар", "en": "Light"},
    "theme_dark": {"mn": "Бараан", "en": "Dark"},
    "theme_pastel": {"mn": "Зөөлөн хаврын пастел", "en": "Soft Spring Pastel"},
    "theme_emerald": {"mn": "Маргад ногоон", "en": "Emerald Green"},
    "theme_blue": {"mn": "Мэргэжлийн цэнхэр", "en": "Professional Blue"},
    "theme_modern_dark": {"mn": "Орчин үеийн бараан", "en": "Modern Dark"},
    "db_error": {
        "mn": "Өгөгдлийн санд холбогдож чадсангүй. PostgreSQL ажиллаж байгаа эсэх, "
        ".env файлд зөв DATABASE_URL байгаа эсэхийг шалгана уу.\n\nДэлгэрэнгүй: {details}",
        "en": "Cannot connect to the database. Check that PostgreSQL is running and "
        "that .env contains a valid DATABASE_URL.\n\nDetails: {details}",
    },
    "kind_income": {"mn": "Орлого", "en": "Income"},
    "kind_expense": {"mn": "Зарлага", "en": "Expense"},
    "kind_transfer": {"mn": "Шилжүүлэг", "en": "Transfer"},
    "type_pos": {"mn": "Карт (POS)", "en": "Card (POS)"},
    "type_qpay": {"mn": "QPay", "en": "QPay"},
    "type_transfer": {"mn": "Шилжүүлэг", "en": "Transfer"},
    "type_fee": {"mn": "Шимтгэл", "en": "Fee"},
    "type_other": {"mn": "Бусад", "en": "Other"},
    "type_cash": {"mn": "Бэлэн / баримт", "en": "Cash / receipt"},
    "col_date": {"mn": "Огноо", "en": "Date"},
    "col_category": {"mn": "Ангилал", "en": "Category"},
    "col_merchant": {"mn": "Харилцагч", "en": "Merchant"},
    "col_type": {"mn": "Төрөл", "en": "Type"},
    "col_amount": {"mn": "Дүн ₮", "en": "Amount ₮"},
    "col_total": {"mn": "Нийт ₮", "en": "Total ₮"},
    "col_count": {"mn": "Тоо", "en": "Count"},
    "col_pct": {"mn": "%", "en": "%"},
    # --- home ----------------------------------------------------------------
    "m_transactions": {"mn": "Гүйлгээ", "en": "Transactions"},
    "m_to_review": {"mn": "Шалгах", "en": "To review"},
    "m_month_expense": {"mn": "Энэ сарын зарлага", "en": "Expense this month"},
    "m_last_import": {"mn": "Сүүлд оруулсан", "en": "Last import"},
    "dti_title": {"mn": "Өр орлогын харьцаа (DTI)", "en": "Debt-to-income ratio (DTI)"},
    "dti_month": {"mn": "{month} · сарын дүн", "en": "{month} · month to date"},
    "dti_income": {"mn": "Нийт орлого", "en": "Gross income"},
    "dti_debt": {"mn": "Сарын өр төлбөр", "en": "Monthly debt payments"},
    "dti_limit": {"mn": "Аюулгүйн дээд хязгаар: {limit}%", "en": "Safety limit: {limit}%"},
    "dti_safe": {"mn": "🟢 Эрсдэлгүй", "en": "🟢 Safe"},
    "dti_moderate": {"mn": "🟡 Анхаарах бүс", "en": "🟡 Moderate"},
    "dti_high_risk": {
        "mn": "🔴 Өр орлогын зааг (45%) хэтэрсэн",
        "en": "🔴 Over the 45% limit: high risk",
    },
    "dti_badge_safe": {"mn": "Эрсдэлгүй · <35%", "en": "Safe · <35%"},
    "dti_badge_moderate": {"mn": "Анхаарах · 35–45%", "en": "Warning · 35–45%"},
    "dti_badge_high_risk": {"mn": "Өндөр эрсдэл · >45%", "en": "High risk · >45%"},
    "dti_badge_unavailable": {"mn": "Мэдээлэлгүй", "en": "No data"},
    "dti_benchmark": {
        "mn": "Аюулгүйн хязгаар {limit}%",
        "en": "Safety benchmark {limit}%",
    },
    "home_counts": {
        "mn": "{count} гүйлгээ · шалгах: {review} · сүүлд оруулсан: {last}",
        "en": "{count} transactions · to review: {review} · last import: {last}",
    },
    "dti_unavailable": {
        "mn": "Энэ сард орлогын гүйлгээ бүртгэгдээгүй тул DTI тооцох боломжгүй.",
        "en": "DTI cannot be calculated because no income is recorded this month.",
    },
    "dti_high_alert": {
        "mn": "Таны сарын өр орлогын харьцаа 45%-ийн аюулгүйн хязгаараас хэтэрсэн байна. "
        "Шинээр зээл авах эсвэл лизинг хийхэд эрсдэлтэй.",
        "en": "Your monthly debt-to-income ratio is above the 45% safety limit. "
        "Taking a new loan or lease may be risky.",
    },
    "dti_reduce": {
        "mn": "Харьцааг 45%-д хүргэхийн тулд сарын өр төлбөрөө дор хаяж {amount}-өөр "
        "бууруулах эсвэл орлогоо нэмэгдүүлэх шаардлагатай.",
        "en": "To reach 45%, reduce monthly debt payments by at least {amount} "
        "or increase gross income.",
    },
    "dti_moderate_tip": {
        "mn": "Сарын өр төлбөрөө хянаж, шинэ зээл авахын өмнө нийт үүргээ тооцоорой.",
        "en": "Monitor monthly debt payments and account for existing obligations before borrowing.",
    },
    "home_classify_link": {
        "mn": "Гүйлгээ харах, ангилах",
        "en": "View and classify transactions",
    },
    # --- upload --------------------------------------------------------------
    "upload_drop": {
        "mn": "Банкны хуулгаа энд чирж оруулна уу (Хас, Хаан, Голомт · .xlsx, .xls, .csv)",
        "en": "Drag & drop bank statements (Xac, Khan, Golomt · .xlsx, .xls, .csv)",
    },
    "upload_button": {"mn": "Оруулах", "en": "Import"},
    "upload_bank": {"mn": "Банк", "en": "Bank"},
    "upload_bank_auto": {"mn": "Автоматаар таних", "en": "Detect automatically"},
    "upload_bank_help": {
        "mn": "Ихэнх хуулгаас банкийг автоматаар танина. Файлд банкны нэр байхгүй бол "
        "энд сонгоно уу.",
        "en": "Most statements name their bank and are detected automatically. If a file "
        "doesn't, choose the bank here.",
    },
    "upload_unknown_bank": {
        "mn": "'{file}': хуулга мөн боловч аль банкных болохыг таньсангүй. Дээрээс банкаа "
        "сонгоод дахин оруулна уу.",
        "en": "'{file}': looks like a statement, but the bank could not be identified. "
        "Choose the bank above and import again.",
    },
    "upload_duplicate": {
        "mn": "'{file}' өмнө нь оруулсан тул алгаслаа.",
        "en": "'{file}' was already imported — skipped.",
    },
    "upload_success": {
        "mn": "'{file}': {inserted} шинээр нэмэгдсэн, {skipped} давхардсан тул алгассан, "
        "{review} шалгах.",
        "en": "'{file}': {inserted} inserted, {skipped} skipped, {review} to review.",
    },
    "upload_pending": {
        "mn": "{count} гүйлгээ ({groups} харилцагч) ангилал шалгах шаардлагатай байна",
        "en": "{count} transactions from {groups} merchants need a category",
    },
    "upload_go_classify": {"mn": "Ангилал руу очих", "en": "Go to Classify"},
    "upload_gap": {
        "mn": "Анхаар: {start} – {end} хооронд хуулга оруулаагүй байна. Тэр хугацааны "
        "хуулгыг оруулбал түүх тасралтгүй болно.",
        "en": "Note: no statement covers {start} – {end} for this account. Import that "
        "period to keep the history continuous.",
    },
    "upload_opening_mismatch": {
        "mn": "Анхаар: '{file}'-ийн эхний үлдэгдэл өмнөх хуулгын эцсийн үлдэгдэлтэй таарахгүй "
        "байна — дунд нь гүйлгээ дутуу байж магадгүй.",
        "en": "Note: the opening balance of '{file}' doesn't match the previous statement's "
        "closing balance — some transactions may be missing in between.",
    },
    "upload_history": {"mn": "Оруулсан түүх", "en": "Import history"},
    "upload_no_history": {
        "mn": "Одоогоор хуулга оруулаагүй байна.",
        "en": "No statements imported yet.",
    },
    "col_file": {"mn": "Файл", "en": "File"},
    "col_bank": {"mn": "Банк", "en": "Bank"},
    "col_account": {"mn": "Данс", "en": "Account"},
    "col_period_start": {"mn": "Эхлэх", "en": "Period start"},
    "col_period_end": {"mn": "Дуусах", "en": "Period end"},
    "col_rows_read": {"mn": "Уншсан мөр", "en": "Rows read"},
    "col_rows_inserted": {"mn": "Нэмэгдсэн мөр", "en": "Rows inserted"},
    "col_imported_at": {"mn": "Оруулсан огноо", "en": "Imported at"},
    "tab_statements": {"mn": "Банкны хуулга", "en": "Bank statements"},
    "tab_receipt": {"mn": "Баримтын зураг", "en": "Receipt photo"},
    "receipt_intro_manual": {
        "mn": "Зургаа өөр дээрээ хадгалж, огноо, дэлгүүр, дүн болон ангиллыг доорх маягтад "
        "гараар оруулна уу. Зураг болон гүйлгээний мэдээлэл энэ төхөөрөмжөөс гарахгүй.",
        "en": "Keep the photo on your device and enter the date, merchant, amount, and "
        "category below. The image and transaction details stay on this device.",
    },
    "receipt_upload": {"mn": "Баримтын зураг (PNG, JPG)", "en": "Receipt image (PNG, JPG)"},
    "receipt_already_saved": {
        "mn": "Энэ баримт аль хэдийн хадгалагдсан байна.",
        "en": "This receipt has already been saved.",
    },
    "receipt_total": {"mn": "Нийт дүн (₮)", "en": "Total (₮)"},
    "receipt_auto_category": {
        "mn": "Автоматаар (дүрмээр)",
        "en": "Automatic (by rules)",
    },
    "receipt_note": {"mn": "Тэмдэглэл", "en": "Note"},
    "receipt_confirm_duplicate": {
        "mn": "Банкны хуулгад ижил дүн байсан ч хадгалах",
        "en": "Save even if a bank-statement transaction has the same amount",
    },
    "receipt_duplicate_help": {
        "mn": "Картаар төлсөн баримт банкны хуулгад давхар гарч болно. Зөвхөн бэлнээр "
        "эсвэл хуулгад ороогүй гүйлгээ бол чагтална уу.",
        "en": "Card-paid receipts also appear in your bank statement. Tick this only for "
        "cash purchases or ones not in any statement.",
    },
    "receipt_save": {"mn": "Гүйлгээ хадгалах", "en": "Save transaction"},
    "receipt_missing": {
        "mn": "Дэлгүүрийн нэр болон 0-ээс их дүн оруулна уу.",
        "en": "Please enter the shop name and an amount above 0.",
    },
    "receipt_duplicate_found": {
        "mn": "Банкны хуулгад {amount} дүнтэй ойролцоо огноотой гүйлгээ байна — давхар "
        "тоологдож магадгүй. Өөр гүйлгээ бол дээрх чагтыг тэмдэглээд дахин хадгална уу.",
        "en": "Your bank statement already has a {amount} transaction near this date — it "
        "may be the same purchase. If it is different, tick the box above and save again.",
    },
    "receipt_saved": {
        "mn": "Баримт хадгалагдлаа: {merchant} — {amount}.",
        "en": "Receipt saved: {merchant} — {amount}.",
    },
    # --- classify ------------------------------------------------------------
    "classify_title": {"mn": "Гүйлгээ ангилах", "en": "Classify transactions"},
    "classify_search": {
        "mn": "Тайлбар эсвэл харилцагчаар хайх",
        "en": "Search descriptions or merchants",
    },
    "tab_transactions": {"mn": "Гүйлгээнүүд", "en": "Transactions"},
    "tab_review": {"mn": "Шалгах ({count})", "en": "To review ({count})"},
    "classify_showing": {
        "mn": "Сүүлийн 500 хүртэлх гүйлгээ · {count} харуулж байна",
        "en": "Showing up to 500 transactions · {count} shown",
    },
    "classify_no_match": {
        "mn": "Хайлт эсвэл шүүлтүүрт тохирох гүйлгээ алга.",
        "en": "No transactions match this search or filter.",
    },
    "classify_no_categories": {
        "mn": "Идэвхтэй ангилал алга.",
        "en": "No active categories are available.",
    },
    "col_description": {"mn": "Гүйлгээний утга", "en": "Description"},
    "col_source": {"mn": "Ангилсан арга", "en": "Classification source"},
    "col_direction": {"mn": "Чиглэл", "en": "Direction"},
    "col_first": {"mn": "Эхний", "en": "First"},
    "col_last": {"mn": "Сүүлийн", "en": "Last"},
    "col_example": {"mn": "Жишээ", "en": "Example"},
    "col_remember": {"mn": "Санах", "en": "Remember"},
    "remember_help": {
        "mn": "Дараагийн хуулгуудыг автоматаар ангилах дүрэм үүсгэнэ",
        "en": "Create a rule so future statements are classified automatically",
    },
    "src_rule": {"mn": "Автомат дүрэм", "en": "Automatic rule"},
    "src_merchant": {"mn": "Автомат (үндсэн)", "en": "Automatic default"},
    "src_manual": {"mn": "Гараар", "en": "Manual"},
    "src_none": {"mn": "Ангилаагүй", "en": "Unclassified"},
    "dir_in": {"mn": "Орлого", "en": "In"},
    "dir_out": {"mn": "Зарлага", "en": "Out"},
    "classify_save": {
        "mn": "Ангиллын өөрчлөлтийг хадгалах",
        "en": "Save category changes",
    },
    "classify_no_changes": {
        "mn": "Хадгалах өөрчлөлт алга.",
        "en": "No category changes to save.",
    },
    "classify_updated": {
        "mn": "{count} гүйлгээний ангиллыг шинэчиллээ.",
        "en": "Updated {count} transaction categories.",
    },
    "classify_auto_option": {"mn": "↺ Автомат ангилал руу буцаах", "en": "↺ Back to automatic"},
    "classify_pending": {"mn": "Хадгалаагүй {count} өөрчлөлт", "en": "{count} unsaved changes"},
    "classify_hint": {
        "mn": "Ангилал баганаас сонгож засна. Гараар сонгосон ангиллыг автомат ангилал дарж бичихгүй.",
        "en": "Change a row in the Category column. Automatic classification never overwrites your choice.",
    },
    "classify_reset_n": {
        "mn": "{count} гүйлгээг автомат ангилал руу буцаалаа.",
        "en": "Reset {count} transactions to automatic.",
    },
    "classify_filter": {"mn": "Харуулах", "en": "Show"},
    "classify_filter_all": {"mn": "Бүгд", "en": "All"},
    "classify_filter_auto": {"mn": "Автомат", "en": "Automatic"},
    "classify_filter_manual": {"mn": "Гараар", "en": "Manual"},
    "classify_filter_review": {"mn": "Шалгах", "en": "To review"},
    "cat_new": {"mn": "Шинэ ангилал", "en": "New category"},
    "cat_name": {"mn": "Ангиллын нэр", "en": "Category name"},
    "cat_place": {"mn": "Байршил", "en": "Place under"},
    "cat_new_main": {"mn": "{kind} · Шинэ үндсэн ангилал", "en": "{kind} · New main category"},
    "cat_create": {"mn": "Ангилал үүсгэх", "en": "Create category"},
    "cat_created": {"mn": "Ангилал үүслээ: {name}.", "en": "Created category: {name}."},
    "cat_err_name": {"mn": "Ангиллын нэр 1–60 тэмдэгт байна.", "en": "A category name needs 1 to 60 characters."},
    "cat_err_exists": {"mn": "Ийм нэртэй ангилал аль хэдийн байна.", "en": "A category with this name already exists."},
    "cat_err_parent": {"mn": "Идэвхтэй үндсэн ангилал сонгоно уу.", "en": "Choose an active main category."},
    "cat_err_kind": {"mn": "Орлого, зарлага эсвэл шилжүүлэг сонгоно уу.", "en": "Choose income, expense or transfer."},
    "upload_recent_title": {"mn": "Энэ удаа оруулсан гүйлгээ ({count})", "en": "Just imported ({count})"},
    "upload_recent_help": {
        "mn": "Автоматаар ангилсан. Буруу ангиллыг Ангилал баганаас засаад хадгална уу.",
        "en": "Classified automatically. Fix any wrong category in the Category column, then save.",
    },
    "upload_recent_close": {"mn": "Хаах", "en": "Close"},
    "review_nothing": {
        "mn": "Шалгах зүйл алга: бүх гүйлгээ дүрмээр эсвэл таны сонголтоор ангилагдсан.",
        "en": "Nothing to review: every transaction was matched by a rule or set by you.",
    },
    "review_intro": {
        "mn": "**{count}** гүйлгээ (**{groups}** харилцагч) ямар ч дүрэмд тохироогүй тул "
        "**{other}**-д орсон. Зөв ангиллыг сонгоорой; дараагийн удаа автоматаар "
        "ангилагдахын тулд *Санах*-ыг чагтална уу.",
        "en": "**{count}** transactions from **{groups}** merchants matched no rule and "
        "were put in **{other}**. Pick the right category; tick *Remember* to classify "
        "them automatically next time.",
    },
    "review_save": {
        "mn": "Бүлгийн ангиллыг хадгалах",
        "en": "Save group classifications",
    },
    "review_pick_one": {
        "mn": "Дор хаяж нэг харилцагчид ангилал сонгоно уу.",
        "en": "Pick a category for at least one merchant first.",
    },
    "review_saved": {
        "mn": "{rows} гүйлгээ ангилж, {rules} дүрэм хадгаллаа.",
        "en": "Classified {rows} transactions; saved {rules} rules.",
    },
    # --- reports -------------------------------------------------------------
    "period": {"mn": "Хугацаа", "en": "Period"},
    "quick_range": {"mn": "Хурдан сонголт", "en": "Quick range"},
    "export_excel": {"mn": "Excel татах", "en": "Export to Excel"},
    "export_pdf": {"mn": "PDF татах", "en": "Export to PDF"},
    "export_help": {
        "mn": "Сонгосон хугацааны KPI, сар, ангилал, газрууд болон бүх гүйлгээ.",
        "en": "KPIs, months, categories, merchants and every transaction for the selected period.",
    },
    "report_title": {"mn": "FinTrack санхүүгийн тайлан", "en": "FinTrack financial report"},
    "report_metric": {"mn": "Үзүүлэлт", "en": "Metric"},
    "report_value": {"mn": "Утга", "en": "Value"},
    "report_generated": {"mn": "Бэлтгэсэн", "en": "Generated"},
    "report_page": {"mn": "Хуудас", "en": "Page"},
    "report_sheet_summary": {"mn": "Хураангуй", "en": "Summary"},
    "report_sheet_categories": {"mn": "Ангилал", "en": "Categories"},
    "report_sheet_merchants": {"mn": "Газрууд", "en": "Merchants"},
    "report_sheet_transactions": {"mn": "Гүйлгээ", "en": "Transactions"},
    "report_top_merchants": {"mn": "Хамгийн их зарцуулсан газрууд", "en": "Top merchants"},
    "report_transactions": {"mn": "Гүйлгээний түүх", "en": "Transaction history"},
    "preset_last_week": {"mn": "Өнгөрсөн долоо хоног", "en": "Last week"},
    "preset_this_month": {"mn": "Энэ сар", "en": "This month"},
    "preset_last_30_days": {"mn": "Сүүлийн 30 хоног", "en": "Last 30 days"},
    "preset_this_year": {"mn": "Энэ жил", "en": "This year"},
    "preset_all_time": {"mn": "Бүх хугацаа", "en": "All time"},
    "pick_range": {
        "mn": "Эхлэх ба дуусах огноог сонгоно уу.",
        "en": "Pick a start and an end date.",
    },
    "no_txns_period": {
        "mn": "Энэ хугацаанд гүйлгээ алга.",
        "en": "No transactions in this period.",
    },
    "m_net": {"mn": "Цэвэр", "en": "Net"},
    "m_savings_rate": {"mn": "Хадгаламжийн хувь", "en": "Savings rate"},
    "m_total_income": {"mn": "Нийт орлого", "en": "Total income"},
    "m_total_expense": {"mn": "Нийт зарлага", "en": "Total expense"},
    "m_net_balance": {"mn": "Цэвэр баланс", "en": "Net cash flow"},
    "vs_previous": {"mn": "өмнөх үеэс", "en": "vs previous period"},
    "delta_help": {
        "mn": "Өөрчлөлтийг өмнөх ижил урттай хугацаатай ({start} – {end}) харьцуулсан.",
        "en": "Change compared with the previous period of equal length ({start} – {end}).",
    },
    "points": {"mn": "{value} пункт", "en": "{value} pts"},
    "monthly_chart": {
        "mn": "Сарын орлого ба зарлага",
        "en": "Monthly income vs expense",
    },
    "col_month": {"mn": "Сар", "en": "Month"},
    "spending_by_category": {"mn": "Ангиллаар зарлага", "en": "Spending by category"},
    "no_expenses": {
        "mn": "Энэ хугацаанд зарлага алга.",
        "en": "No expenses in this period.",
    },
    "top_pos": {
        "mn": "Картаар хамгийн их зарцуулсан газрууд",
        "en": "Top POS merchants",
    },
    "income_by_category": {"mn": "Ангиллаар орлого", "en": "Income by category"},
    # --- budget & goals ------------------------------------------------------
    "budget_month": {"mn": "Төсвийн сар", "en": "Budget month"},
    "monthly_budgets": {"mn": "Сарын төсөв · {month}", "en": "Monthly budgets · {month}"},
    "no_expense_categories": {
        "mn": "Идэвхтэй зарлагын ангилал алга.",
        "en": "No active expense categories are available.",
    },
    "col_monthly_limit": {"mn": "Сарын хязгаар (₮)", "en": "Monthly limit (₮)"},
    "limit_help": {
        "mn": "Энэ ангиллын төсвийг устгах бол хоосон үлдээнэ үү.",
        "en": "Leave blank to remove the budget for this category.",
    },
    "save_limits": {"mn": "Сарын хязгаарыг хадгалах", "en": "Save monthly limits"},
    "limits_saved": {
        "mn": "{count} сарын төсвийн хязгаар хадгаллаа.",
        "en": "Saved {count} monthly budget limits.",
    },
    "spending_progress": {"mn": "Зарцуулалтын явц", "en": "Spending progress"},
    "unclassified_expenses": {
        "mn": "Энэ сарын ангилаагүй зарлага: {amount}. Төсөвт тооцуулахын тулд "
        "Ангилал хуудсанд ангилна уу.",
        "en": "Unclassified expenses this month: {amount}. Assign categories on the "
        "Classify page to include them in a budget.",
    },
    "spent_no_limit": {
        "mn": "Зарцуулсан {spent} · Сарын хязгаар тогтоогоогүй",
        "en": "Spent {spent} · No monthly limit set",
    },
    "progress_of": {"mn": "{spent} / {limit} · {pct}", "en": "{spent} of {limit} · {pct}"},
    "m_spent": {"mn": "Зарцуулсан", "en": "Spent"},
    "m_remaining": {"mn": "Үлдсэн", "en": "Remaining"},
    "m_over_budget": {"mn": "Хэтэрсэн", "en": "Over budget"},
    "budget_exceeded": {
        "mn": "Төсөв {amount}-өөр хэтэрлээ.",
        "en": "Budget exceeded by {amount}.",
    },
    "budget_approaching": {
        "mn": "Энэ ангилал сарын төсвийнхөө 80%-иас дээшийг зарцуулсан.",
        "en": "This category has used at least 80% of its monthly budget.",
    },
    "alerts_title": {"mn": "Төсвийн анхааруулга · {month}", "en": "Budget alerts · {month}"},
    "alert_exceeded": {
        "mn": "**{category}**: {spent} / {limit} — төсөв {over}-өөр хэтэрсэн.",
        "en": "**{category}**: {spent} of {limit} — over budget by {over}.",
    },
    "alert_approaching": {
        "mn": "**{category}**: төсвийн {pct} ашигласан ({spent} / {limit}).",
        "en": "**{category}**: {pct} of the budget used ({spent} of {limit}).",
    },
    "alerts_open_budget": {"mn": "Төсөв ба зорилго нээх", "en": "Open Budget & Goals"},
    "copy_budgets": {
        "mn": "Өмнөх сарын хязгаарыг хуулах",
        "en": "Copy last month's limits",
    },
    "budgets_copied": {
        "mn": "Өмнөх сараас {count} хязгаар хууллаа.",
        "en": "Copied {count} limits from last month.",
    },
    "nothing_to_copy": {
        "mn": "Өмнөх сард хуулах хязгаар алга.",
        "en": "Last month has no limits to copy.",
    },
    "savings_goals": {"mn": "Хуримтлалын зорилго", "en": "Savings goals"},
    "tab_budget": {"mn": "Сарын төсөв", "en": "Monthly budget"},
    "tab_goals": {"mn": "Урт хугацааны зорилго", "en": "Long-term goals"},
    "budget_vs_actual": {"mn": "Төсөв ба бодит зарцуулалт", "en": "Budget vs actual"},
    "no_budgets_yet": {
        "mn": "Энэ сард хязгаар тогтоогоогүй байна. Дээрх хүснэгтэд үндсэн ангилал бүрт дүн оруулна уу.",
        "en": "No limits set for this month yet. Enter amounts per main category in the table above.",
    },
    "unbudgeted_spending": {
        "mn": "Хязгааргүй ангиллын зарцуулалт ({count})",
        "en": "Spending in categories without a limit ({count})",
    },
    "goal_type": {"mn": "Төрөл", "en": "Type"},
    "goal_type_emergency": {"mn": "Яаралтай тусламжийн сан", "en": "Emergency fund"},
    "goal_type_education": {"mn": "Боловсролын төлбөр", "en": "Education fee"},
    "goal_type_purchase": {"mn": "Томоохон худалдан авалт", "en": "Major purchase"},
    "goal_type_travel": {"mn": "Аялал", "en": "Travel fund"},
    "goal_type_other": {"mn": "Бусад", "en": "Other"},
    "goal_name_placeholder": {"mn": "ж: Яаралтай сан, Зуны аялал", "en": "e.g. Emergency fund, Summer trip"},
    "goal_m_saved": {"mn": "Нийт хуримтлуулсан", "en": "Total saved"},
    "goal_m_target": {"mn": "Нийт зорилт", "en": "Total target"},
    "goal_m_monthly": {"mn": "Сард хадгалах шаардлагатай", "en": "Needed per month"},
    "goal_m_planned": {"mn": "Төлөвлөсөн хуримтлал / сар", "en": "Planned savings per month"},
    "goal_monthly_help": {
        "mn": "Бүх зорилгодоо хугацаандаа хүрэхийн тулд сар бүр хадгалах дүн.",
        "en": "What to save each month to reach every goal on time.",
    },
    "goal_monthly_needed": {"mn": "Сард хадгалах", "en": "Save per month"},
    "goal_planned_monthly": {"mn": "Төлөвлөсөн дүн / сар", "en": "Planned per month"},
    "goal_projected_date": {"mn": "Төлөвлөсөн дуусах", "en": "Projected completion"},
    "goal_funding_sources": {"mn": "Санхүүжилтийн эх үүсвэр", "en": "Funding sources"},
    "goal_funding_help": {
        "mn": "Цалин, нэмэлт орлого, нэг удаагийн урамшуулал эсвэл зээл зэрэг эх үүсвэрийг "
        "нэмж болно. Төлөвлөгөө нь одоогийн хуримтлал биш; бодит орлогыг доорх хуримтлалын "
        "гүйлгээгээр бүртгэнэ.",
        "en": "Add sources such as salary, side income, a one-time bonus, or a loan. "
        "These are planned amounts, not current savings; actual savings are tracked from "
        "the transactions assigned below.",
    },
    "goal_funding_source": {"mn": "Эх үүсвэр", "en": "Source"},
    "goal_funding_kind": {"mn": "Төрөл", "en": "Type"},
    "goal_funding_kind_monthly": {"mn": "Сар бүр", "en": "Monthly"},
    "goal_funding_kind_lump_sum": {"mn": "Нэг удаа", "en": "One-time"},
    "goal_funding_kind_loan": {"mn": "Зээл", "en": "Loan"},
    "goal_funding_amount": {"mn": "Дүн (₮)", "en": "Amount (₮)"},
    "goal_funding_start": {"mn": "Эхлэх сар", "en": "Start month"},
    "goal_funding_end": {"mn": "Дуусах сар", "en": "End month"},
    "goal_funding_save": {"mn": "Эх үүсвэр хадгалах", "en": "Save funding plan"},
    "goal_funding_incomplete": {
        "mn": "Эх үүсвэр бүрийн нэр, төрөл, дүн, эхлэх сарыг бүрэн оруулна уу.",
        "en": "Each funding source needs a name, type, amount, and start month.",
    },
    "goal_funding_saved": {"mn": "Санхүүжилтийн төлөвлөгөөг хадгаллаа.", "en": "Funding plan saved."},
    "goal_plan_shortfall": {"mn": "Хугацааны дутагдал", "en": "Deadline shortfall"},
    "goal_plan_status_done": {
        "mn": "Зорилго биелсэн.",
        "en": "Goal reached.",
    },
    "goal_plan_status_no_plan": {
        "mn": "Санхүүжилтийн төлөвлөгөө оруулаагүй.",
        "en": "No funding plan entered.",
    },
    "goal_plan_status_covered": {
        "mn": "Төлөвлөсөн эх үүсвэр хугацаанд хүрнэ.",
        "en": "Planned sources cover the goal by the deadline.",
    },
    "goal_plan_status_gap": {
        "mn": "Хугацаанд хүрэхэд {amount} дутна; сард нэмэлт {extra} хадгалах шаардлагатай.",
        "en": "{amount} is still unfunded by the deadline; save an extra {extra} per month.",
    },
    "goal_savings_plan_met": {
        "mn": "Энэ сарын хуримтлалын төлөвлөгөө биелсэн.",
        "en": "This month's savings plan is met.",
    },
    "goal_savings_plan_remaining": {
        "mn": "Энэ сарын төлөвлөгөөг биелүүлэхэд {amount} дутуу байна.",
        "en": "{amount} remains to meet this month's plan.",
    },
    "goal_savings_unplanned": {
        "mn": "Энэ сард {amount} хуримтлуулсан боловч төлөвлөгөө тохируулаагүй байна.",
        "en": "{amount} saved this month without a planned savings allocation.",
    },
    "assign_funding_source": {"mn": "Эх үүсвэр", "en": "Funding source"},
    "assign_source_goal_mismatch": {
        "mn": "Сонгосон эх үүсвэр нь сонгосон зорилгод хамаарахгүй байна.",
        "en": "The selected funding source does not belong to the selected goal.",
    },
    "goal_months_left": {"mn": "Үлдсэн сар", "en": "Months left"},
    "goal_status_done": {"mn": "Биелсэн", "en": "Reached"},
    "goal_status_ahead": {"mn": "Төлөвлөгөөнөөс түрүүлсэн", "en": "Ahead"},
    "goal_status_on_track": {"mn": "Төлөвлөгөөний дагуу", "en": "On track"},
    "goal_status_behind": {"mn": "Хоцорч байна", "en": "Behind"},
    "goal_status_overdue": {"mn": "Хугацаа дууссан", "en": "Past deadline"},
    "goal_breakdown": {
        "mn": "Эхлэлийн дүн {start} + хуримтлалын {count} гүйлгээ {contributed} · эцсийн хугацаа "
        "{deadline} · одоогоор {expected}%-д хүрсэн байх ёстой",
        "en": "Starting amount {start} + {count} savings transactions {contributed} · deadline "
        "{deadline} · should be at {expected}% by now",
    },
    "goal_starting": {"mn": "Эхлэлийн дүн (₮)", "en": "Starting amount (₮)"},
    "goal_starting_help": {
        "mn": "Хуримтлалын гүйлгээнээс гадуур хадгалсан мөнгө (жишээ нь өмнөх хадгаламж).",
        "en": "Money saved outside the tracked savings transactions (e.g. earlier savings).",
    },
    "assign_title": {"mn": "Хуримтлалын гүйлгээг зорилгод хуваарилах", "en": "Assign savings to goals"},
    "assign_help": {
        "mn": "\"{savings}\" ангилалтай гүйлгээ (хадгаламж руу шилжүүлсэн мөнгө) зорилгын явцад "
        "тооцогдоно. Гүйлгээ бүрийг аль зорилгод хамаарахыг сонгоно уу.",
        "en": "Transactions classified \"{savings}\" (money moved to savings) count towards goals. "
        "Choose which goal each one belongs to.",
    },
    "assign_none": {
        "mn": "Хуваарилаагүй хуримтлалын гүйлгээ алга. Хадгаламж руу шилжүүлсэн гүйлгээг Ангилал "
        "хуудсанд \"{savings_path}\" болгож ангилна уу.",
        "en": "No unassigned savings transactions. On the Classify page, set transfers to savings as "
        "\"{savings_path}\".",
    },
    "assign_need_goal": {
        "mn": "Хуримтлалын гүйлгээ байна — эхлээд зорилго үүсгэнэ үү.",
        "en": "There are savings transactions — create a goal first.",
    },
    "assign_goal": {"mn": "Зорилго", "en": "Goal"},
    "assign_save": {"mn": "Хуваарилалт хадгалах", "en": "Save assignments"},
    "assigned_n": {"mn": "{count} гүйлгээг зорилгод хуваариллаа.", "en": "Assigned {count} transactions to goals."},
    "subcategory_breakdown": {"mn": "Хүснэгт ба дэд ангилал", "en": "Table and subcategories"},
    "col_main_category": {"mn": "Үндсэн ангилал", "en": "Main category"},
    "col_subcategory": {"mn": "Дэд ангилал", "en": "Subcategory"},
    "goal_name": {"mn": "Зорилгын нэр", "en": "Goal name"},
    "target_amount": {"mn": "Зорилтот дүн (₮)", "en": "Target amount (₮)"},
    "already_saved": {"mn": "Хуримтлуулсан (₮)", "en": "Already saved (₮)"},
    "deadline": {"mn": "Эцсийн хугацаа", "en": "Deadline"},
    "create_goal": {"mn": "Зорилго үүсгэх", "en": "Create savings goal"},
    "goal_created": {
        "mn": "Хуримтлалын зорилго үүслээ: {name}.",
        "en": "Created savings goal: {name}.",
    },
    "no_goals": {
        "mn": "Идэвхтэй хуримтлалын зорилго алга.",
        "en": "No active savings goals yet.",
    },
    "deadline_caption": {"mn": "Эцсийн хугацаа: {date}", "en": "Deadline: {date}"},
    "current_saved": {"mn": "Одоогийн хуримтлал (₮)", "en": "Current saved amount (₮)"},
    "update_saved": {"mn": "Хуримтлалыг шинэчлэх", "en": "Update saved amount"},
    "archive_goal": {"mn": "Зорилгыг архивлах", "en": "Archive goal"},
    "goal_updated": {
        "mn": "{name} зорилгын хуримтлалыг шинэчиллээ.",
        "en": "Updated savings for {name}.",
    },
    "goal_archived": {
        "mn": "Хуримтлалын зорилгыг архивлалаа: {name}.",
        "en": "Archived savings goal: {name}.",
    },
    # --- recurring bills -----------------------------------------------------
    "rec_alerts_title": {"mn": "Тогтмол төлбөрүүд", "en": "Recurring bills"},
    "rec_status_overdue": {"mn": "Хугацаа хэтэрсэн", "en": "Overdue"},
    "rec_status_due": {"mn": "Өнөөдөр", "en": "Due today"},
    "rec_status_upcoming": {"mn": "Удахгүй", "en": "Upcoming"},
    "rec_action_confirmed": {"mn": "Төлсөн", "en": "Already paid"},
    "rec_action_log": {"mn": "Бэлнээр бүртгэх", "en": "Log as cash payment"},
    "rec_action_skipped": {"mn": "Энэ удаа алгасах", "en": "Skip this time"},
    "rec_done_confirmed": {"mn": "Төлсөнд тооцлоо.", "en": "Marked as paid."},
    "rec_done_log": {"mn": "Бэлэн төлбөрөөр бүртгэлээ.", "en": "Logged as a cash payment."},
    "rec_done_skipped": {"mn": "Энэ удаа алгаслаа.", "en": "Skipped this time."},
    "rec_alerts_help": {
        "mn": "Банкны хуулгад төлбөр олдвол автоматаар төлсөнд тооцогдоно. \"Төлсөн\" — "
        "өөр аргаар төлсөн; \"Бэлнээр бүртгэх\" — Бэлэн мөнгө дансанд гүйлгээ үүсгэнэ.",
        "en": "Payments found in an imported bank statement are marked paid automatically. "
        "\"Already paid\" — paid some other way; \"Log as cash payment\" — adds a "
        "transaction to the Cash account.",
    },
    "rec_auto_matched": {
        "mn": "Банкны хуулгаас {count} тогтмол төлбөр олдож төлсөнд тооцлоо.",
        "en": "{count} recurring bills were found in your bank statements and marked paid.",
    },
    "rec_m_monthly": {"mn": "Сард дунджаар", "en": "Per month (avg.)"},
    "rec_m_active": {"mn": "Идэвхтэй", "en": "Active"},
    "rec_m_next": {"mn": "Дараагийн төлбөр", "en": "Next bill"},
    "rec_add": {"mn": "Шинэ тогтмол төлбөр нэмэх", "en": "Add a recurring bill"},
    "rec_name": {"mn": "Нэр", "en": "Name"},
    "rec_name_placeholder": {"mn": "ж: Түрээс, Интернет, Netflix", "en": "e.g. Rent, Internet, Netflix"},
    "rec_amount": {"mn": "Дүн (₮)", "en": "Amount (₮)"},
    "rec_frequency": {"mn": "Давтамж", "en": "Frequency"},
    "rec_next_due": {"mn": "Төлөх огноо", "en": "Due date"},
    "rec_pattern": {"mn": "Хуулгад таних үг", "en": "Statement keyword"},
    "rec_pattern_help": {
        "mn": "Банкны хуулгын гүйлгээний утга/харилцагчид агуулагдах үг (ж: UNITEL). "
        "Хоосон бол яг ижил дүнгээр хайна; бөглөвөл дүн өөр байсан ч таньна.",
        "en": "A word in the statement description/counterparty (e.g. UNITEL). Empty = match "
        "the exact amount; filled = match this word even if the amount varies.",
    },
    "rec_save_new": {"mn": "Нэмэх", "en": "Add"},
    "rec_invalid_name": {"mn": "Нэр оруулна уу.", "en": "Please enter a name."},
    "rec_invalid_amount": {"mn": "0-ээс их дүн оруулна уу.", "en": "Please enter an amount above 0."},
    "rec_invalid_frequency": {"mn": "Давтамж сонгоно уу.", "en": "Please choose a frequency."},
    "rec_added": {"mn": "Нэмлээ: {name}.", "en": "Added: {name}."},
    "rec_list": {"mn": "Тогтмол төлбөр ба захиалгууд", "en": "Subscriptions and fixed bills"},
    "rec_empty": {
        "mn": "Тогтмол төлбөр алга. Дээрээс нэмнэ үү (түрээс, интернет, утас, захиалга…).",
        "en": "No recurring bills yet. Add one above (rent, internet, phone, subscriptions…).",
    },
    "rec_active": {"mn": "Идэвхтэй", "en": "Active"},
    "rec_monthly": {"mn": "Сард (₮)", "en": "Per month (₮)"},
    "rec_edit_help": {
        "mn": "Хүснэгтэд шууд засаад хадгална уу. Зогсоох бол \"Идэвхтэй\"-г арилгана.",
        "en": "Edit in the table and save. To stop a bill, untick \"Active\".",
    },
    "rec_save_changes": {"mn": "Өөрчлөлт хадгалах", "en": "Save changes"},
    "rec_updated": {"mn": "{count} мөр шинэчиллээ.", "en": "Updated {count} rows."},
    "rec_history": {"mn": "Төлбөрийн түүх", "en": "Payment history"},
    "rec_history_empty": {"mn": "Түүх алга.", "en": "No history yet."},
    "rec_hist_matched": {"mn": "Хуулгаас олдсон", "en": "Found in statement"},
    "rec_hist_confirmed": {"mn": "Төлсөн (гараар)", "en": "Paid (confirmed)"},
    "rec_hist_logged": {"mn": "Бэлнээр бүртгэсэн", "en": "Logged as cash"},
    "rec_hist_skipped": {"mn": "Алгассан", "en": "Skipped"},
    "rec_status": {"mn": "Төлөв", "en": "Status"},
    "rec_paid_on": {"mn": "Төлсөн огноо", "en": "Paid on"},
    "freq_weekly": {"mn": "Долоо хоног бүр", "en": "Weekly"},
    "freq_monthly": {"mn": "Сар бүр", "en": "Monthly"},
    "freq_yearly": {"mn": "Жил бүр", "en": "Yearly"},
    # --- AI assistant --------------------------------------------------------
    "ai_mode_local": {
        "mn": "Зөвхөн энэ төхөөрөмж дээрх өгөгдөл болон дүрмээр ажиллана. Гаднын AI үйлчилгээ ашиглахгүй.",
        "en": "Uses local data and built-in rules only. No external AI service is called.",
    },
    "ai_shared_data": {
        "mn": "Хариулт гаргахад ашиглах дотоод нэгтгэсэн өгөгдөл",
        "en": "Local aggregate data used to generate answers",
    },
    "ai_placeholder": {
        "mn": "Санхүүгийнхээ талаар асуугаарай…",
        "en": "Ask about your finances…",
    },
    "ai_suggest_top": {
        "mn": "Энэ сард хамгийн их юунд зарцуулсан бэ?",
        "en": "Where did I spend the most this month?",
    },
    "ai_suggest_food": {
        "mn": "Хоол хүнсний зардлаа яаж бууруулах вэ?",
        "en": "How can I reduce my food expenses?",
    },
    "ai_suggest_savings": {
        "mn": "Миний хуримтлалын явц ямар байна?",
        "en": "What is my current savings progress?",
    },
    "ai_suggest_budget": {
        "mn": "Төсвөөсөө хэтэрсэн ангилал байна уу?",
        "en": "Am I over budget anywhere?",
    },
    "ai_clear": {"mn": "Яриаг цэвэрлэх", "en": "Clear conversation"},
    "coach_no_data": {
        "mn": "Энэ сарын зарлага алга. Шинэ хуулгаа Хуулга оруулах хуудсаар оруулна уу.",
        "en": "No expenses this month yet. Upload your latest statement on the Upload page.",
    },
    "coach_top": {
        "mn": "Энэ сард хамгийн их зарцуулсан ангилал: **{category}** — **{amount}**.",
        "en": "Your biggest spending category this month is **{category}** — **{amount}**.",
    },
    "coach_top_merchants": {
        "mn": "Картаар/QPay-ээр хамгийн их төлсөн газрууд:",
        "en": "Top card/QPay merchants:",
    },
    "coach_food": {
        "mn": "Хоол хүнс, ресторан: энэ сард **{now}** (өмнөх сард {before}).",
        "en": "Food and restaurants: **{now}** this month (last month {before}).",
    },
    "coach_food_merchants": {"mn": "Гол зарцуулсан газрууд:", "en": "Where it went:"},
    "coach_food_tips": {
        "mn": "Санал:\n- Төсөв ба зорилго хуудсанд \"{food}\" ангилалд сарын хязгаар тогтоо.\n"
        "- Долоо хоногийн худалдан авалтаа төлөвлөж, жижиг дэлгүүрээр олон дахин орохоо цөөл.\n"
        "- Ресторан, кафег долоо хоногт тодорхой тоогоор хязгаарла.",
        "en": "Suggestions:\n- Set a monthly limit for \"{food}\" on the Budget & Goals page.\n"
        "- Plan one weekly shop instead of many small convenience-store trips.\n"
        "- Cap restaurant and café visits to a set number per week.",
    },
    "coach_no_goals": {
        "mn": "Хуримтлалын зорилго алга. Төсөв ба зорилго хуудсанд зорилго үүсгээрэй.",
        "en": "No savings goals yet. Create one on the Budget & Goals page.",
    },
    "coach_goals_intro": {"mn": "Таны хуримтлалын явц:", "en": "Your savings progress:"},
    "coach_goal_line": {
        "mn": "- **{name}**: {saved} / {target} ({percent}%), эцсийн хугацаа {deadline}",
        "en": "- **{name}**: {saved} of {target} ({percent}%), due {deadline}",
    },
    "coach_no_budgets": {
        "mn": "Энэ сард төсөв тогтоогоогүй байна. Төсөв ба зорилго хуудсанд хязгаар оруулаарай.",
        "en": "No budgets are set for this month. Add limits on the Budget & Goals page.",
    },
    "coach_budgets_intro": {"mn": "Энэ сарын төсөв:", "en": "Budgets this month:"},
    "coach_budget_line": {
        "mn": "- **{category}**: {spent} / {limit} — {status}",
        "en": "- **{category}**: {spent} of {limit} — {status}",
    },
    "coach_status_within": {"mn": "хэвийн", "en": "on track"},
    "coach_status_approaching": {"mn": "80%-д ойртсон", "en": "over 80% used"},
    "coach_status_exceeded": {"mn": "хэтэрсэн", "en": "exceeded"},
    "coach_summary": {
        "mn": "{month}: орлого **{income}**, зарлага **{expense}**, цэвэр **{net}**.",
        "en": "{month}: income **{income}**, expense **{expense}**, net **{net}**.",
    },
    "coach_help": {
        "mn": "Би дараах асуултад хариулж чадна: хамгийн их зарцуулалт, хоол хүнсний "
        "зардал, төсвийн байдал, хуримтлалын явц, сарын орлого/зарлага.",
        "en": "I can answer: where you spent the most, food spending, budget status, "
        "savings progress, and monthly income vs expense.",
    },
}


# Categories are stored in Mongolian (the database is the source of truth); this gives
# the English name of every seeded category. User-created ones show as typed.
CATEGORY_EN: dict[str, str] = {
    "Хоол хүнс": "Food & Groceries",
    "Супермаркет": "Supermarkets",
    "Хүнсний дэлгүүр": "Convenience stores",
    "Ресторан & Кафе": "Dining & Cafes",
    "Ресторан": "Restaurants",
    "Кафе & Кофе шоп": "Cafes & Coffee shops",
    "Түргэн хоол": "Fast food",
    "Паб & Баар": "Pubs & Bars",
    "Боловсрол": "Education & Career",
    "Сургалтын төлбөр": "Tuition fees",
    "Курс & Сургалт": "Courses & Training",
    "Ном & Хэрэгсэл": "Books & Supplies",
    "Гоо сайхан & Арчилгаа": "Beauty & Personal Care",
    "Гоо сайхны бүтээгдэхүүн": "Cosmetics",
    "Салон & Үйлчилгээ": "Salons & Services",
    "Тээврийн хэрэгсэл": "Transport & Fuel",
    "Нийтийн тээвэр": "Public transport",
    "Такси": "Taxi",
    "Шатахуун": "Fuel",
    "Зогсоол": "Parking",
    "Тогтмол зардлууд": "Utilities & Subscriptions",
    "Түрээс": "Rent",
    "Интернет & ТВ": "Internet & TV",
    "Гар утас": "Mobile phone",
    "Банкны шимтгэл": "Bank fees",
    "Худалдан авалт": "Shopping",
    "Хувцас": "Clothing",
    "Электроник": "Electronics",
    "Гэр ахуй": "Household",
    "Эрүүл мэнд": "Health",
    "Зугаа цэнгэл": "Entertainment",
    "Зээлийн төлбөр": "Debt payments",
    "Бусад": "Other",
    "Шилжүүлэг & Хуримтлал": "Transfers & Savings",
    "Дотоод шилжүүлэг": "Internal transfer",
    "Хуримтлал": "Savings",
    "Өөрийн орлого": "Earned income",
    "Бэлэг": "Gifts",
    "Хандив": "Donations",
}
# Placeholders the queries use for "no category".
_UNCLASSIFIED = {"Unclassified", "Ангилаагүй", None}


def category_name(name: str | None, lang: str | None = None) -> str:
    """Display name of a category in lang (default: the selected UI language)."""
    lang = lang or current_language()
    if name in _UNCLASSIFIED:
        return TEXTS["src_none"][lang]
    return CATEGORY_EN.get(name, name) if lang == "en" else name


def persisted_choice(state_key: str, query_key: str, allowed: Iterable[str], default: str) -> str:
    """A sidebar choice kept in the session and mirrored in the URL (?lang=en&theme=blue),
    so a page refresh or a bookmarked tab keeps it."""
    allowed = set(allowed)
    value = st.session_state.get(state_key)
    if value not in allowed:
        try:
            value = st.query_params.get(query_key)
        except Exception:  # no script run (tests, worker threads): no URL to read
            value = None
        if value not in allowed:
            value = default
        st.session_state[state_key] = value
    return value


def sync_url(query_key: str, value: str, default: str) -> None:
    """Write the choice into the URL (or drop it when it is the default)."""
    try:
        if value == default:
            st.query_params.pop(query_key, None)
        elif st.query_params.get(query_key) != value:
            st.query_params[query_key] = value
    except Exception:
        pass


def current_language() -> str:
    return persisted_choice(_STATE_KEY, "lang", LANGUAGES, DEFAULT_LANGUAGE)


def t(key: str, **kwargs: Any) -> str:
    """Return the text for key in the selected language, formatted with kwargs."""
    entry = TEXTS[key]
    text = entry.get(current_language()) or entry["en"]
    return text.format(**kwargs) if kwargs else text


def language_selector() -> None:
    """Sidebar Монгол / English switch; kept for the session and in the URL."""

    def remember_choice() -> None:
        st.session_state[_STATE_KEY] = st.session_state[_WIDGET_KEY]

    codes = list(LANGUAGES)
    st.sidebar.radio(
        "🌐 " + t("language"),
        codes,
        index=codes.index(current_language()),
        format_func=LANGUAGES.__getitem__,
        horizontal=True,
        key=_WIDGET_KEY,
        on_change=remember_choice,
    )
    sync_url("lang", current_language(), DEFAULT_LANGUAGE)
