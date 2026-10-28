"""Transaction type detection and merchant/counterparty extraction (pure functions)."""

import re

FEE_PREFIXES: tuple[str, ...] = ("XACINFO", "Банк хоорондын шилжүүлгийн шимтгэл")
FEE_MARKER = "TRX:"

BANK_NAMES: tuple[str, ...] = (
    "ХААН БАНК",
    "ГОЛОМТ БАНК",
    "ТӨРИЙН БАНК",
    "ХАС БАНК",
    "АРИГ БАНК",
    "ТӨВ БАНК",
    "КАПИТРОН БАНК",
    "БОГД БАНК",
    "ҮХОБ",
)

# Masked card number then merchant. Xac: '498738**1604'; other banks mask differently
# ('1234**5678', '4567****1234', '4567XXXXXX1234').
_POS_RE = re.compile(r"^\S+\s+.*?\d{4,6}(?:\*{2,}|X{4,})\d{4}\s+(.+)$")
_QPAY_PREFIX_RE = re.compile(r"^qpay\s*[:#-]?\s*", re.I)
_TRAILING_ACCOUNT_RE = re.compile(r"-\d+$")
_SPACES_RE = re.compile(r"\s+")


def normalize(s: str) -> str:
    """Upper-case and collapse whitespace."""
    return _SPACES_RE.sub(" ", s).strip().upper()


def clean_counterparty(cp: str) -> str:
    """Drop the trailing '-<account digits>' and bank name from a counterparty."""
    text = _SPACES_RE.sub(" ", _TRAILING_ACCOUNT_RE.sub("", cp.strip())).strip()
    upper = text.upper()
    for bank in BANK_NAMES:
        if upper.endswith(bank):
            text = text[: len(text) - len(bank)]
            break
    return _SPACES_RE.sub(" ", text).strip()


def detect_type(description: str) -> str:
    """Return 'fee', 'pos', 'qpay' or 'transfer'."""
    text = description.strip()
    if text.startswith(FEE_PREFIXES) or FEE_MARKER in text:
        return "fee"
    if _POS_RE.match(text):
        return "pos"
    if text.lower().startswith("qpay"):
        return "qpay"
    return "transfer"


def extract_merchant(description: str, counterparty: str) -> tuple[str, str | None]:
    """Return (txn_type, normalized merchant name or None)."""
    txn_type = detect_type(description)
    if txn_type == "fee":
        return txn_type, None
    if txn_type == "pos":
        match = _POS_RE.match(description.strip())
        assert match is not None
        return txn_type, normalize(match.group(1)) or None
    merchant = normalize(clean_counterparty(counterparty or "")) or None
    if txn_type == "qpay" and merchant is None:
        # Banks without a counterparty column put the shop after 'QPay' in the description.
        merchant = normalize(_QPAY_PREFIX_RE.sub("", description.strip())) or None
    return txn_type, merchant
