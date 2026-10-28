"""Local receipt-image helpers and validation for manually entered receipt data."""

import hashlib
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 1568  # px; larger images are downscaled by the API anyway


class ReceiptError(Exception):
    """A receipt image could not be prepared; the message is safe to show."""


@dataclass
class ReceiptData:
    txn_date: date | None
    merchant: str | None
    total: Decimal | None
    payment: str
    note: str


def receipt_ref(image: bytes) -> str:
    """Stable reference for a receipt image; saved as bank_ref so it can't be saved twice."""
    return "RCPT-" + hashlib.sha256(image).hexdigest()[:16]


def prepare_image(image: bytes) -> bytes:
    """Rotate per EXIF, downscale, and re-encode locally as JPEG."""
    try:
        with Image.open(io.BytesIO(image)) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise ReceiptError("not_an_image") from exc


def parse_result(payload: dict[str, Any]) -> ReceiptData:
    """Validate locally supplied receipt fields; implausible values become None."""
    txn_date = None
    try:
        txn_date = date.fromisoformat(str(payload.get("date") or "")[:10])
    except ValueError:
        pass
    if txn_date and not (date(2000, 1, 1) <= txn_date <= date.today()):
        txn_date = None

    total = None
    try:
        total = Decimal(str(payload.get("total"))).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        pass
    if total is not None and not (Decimal("0") < total < Decimal("100000000")):
        total = None

    merchant = (payload.get("merchant") or "").strip() or None
    payment = payload.get("payment") if payload.get("payment") in ("card", "cash", "qpay") else "unknown"
    return ReceiptData(txn_date, merchant, total, payment, (payload.get("note") or "").strip())
