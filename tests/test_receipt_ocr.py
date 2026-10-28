import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from PIL import Image

from core.i18n import TEXTS
from core.receipt_ocr import (
    ReceiptError,
    parse_result,
    prepare_image,
    receipt_ref,
)


def _png(width: int = 3000, height: int = 4000) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(out, format="PNG")
    return out.getvalue()


def test_parse_result_valid() -> None:
    data = parse_result(
        {"date": "2026-10-12", "merchant": " CU-334 ", "total": 12500, "payment": "card", "note": "сүү, талх"}
    )
    assert data.txn_date == date(2026, 10, 12)
    assert data.merchant == "CU-334"
    assert data.total == Decimal("12500.00")
    assert data.payment == "card"


@pytest.mark.parametrize(
    "payload",
    [
        {"date": None, "merchant": None, "total": None, "payment": "unknown", "note": ""},
        {"date": "12/10/2026", "merchant": "", "total": -5, "payment": "bitcoin", "note": ""},
        {"date": (date.today() + timedelta(days=30)).isoformat(), "merchant": "X", "total": 0, "payment": "cash", "note": ""},
    ],
)
def test_parse_result_drops_implausible_values(payload) -> None:
    data = parse_result(payload)
    assert data.txn_date is None
    assert data.total is None
    assert data.payment in ("cash", "unknown")


def test_prepare_image_downscales_and_converts_to_jpeg() -> None:
    jpeg = prepare_image(_png())
    with Image.open(io.BytesIO(jpeg)) as img:
        assert img.format == "JPEG"
        assert max(img.size) == 1568


def test_prepare_image_rejects_non_images() -> None:
    with pytest.raises(ReceiptError, match="not_an_image"):
        prepare_image(b"not an image")


def test_receipt_ref_is_stable() -> None:
    assert receipt_ref(b"abc") == receipt_ref(b"abc") != receipt_ref(b"abd")
    assert receipt_ref(b"abc").startswith("RCPT-")


def test_receipts_are_manual_and_local() -> None:
    intro = TEXTS["receipt_intro_manual"]["en"]
    assert "stay on this device" in intro
    assert "ai_mode_local" in TEXTS
