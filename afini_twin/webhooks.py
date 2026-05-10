"""
Webhook signature verification + payload typing.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any, Literal, Optional, TypedDict, Union


WebhookEventType = Literal[
    "twin.snapshot.ready",
    "twin.snapshot.failed",
    "twin.api_key.revoked",
    "twin.quota.warning_80",
    "twin.quota.exceeded",
    "twin.test",
]


class WebhookPayload(TypedDict, total=False):
    event: WebhookEventType
    deliveryId: str
    timestamp: str
    data: dict[str, Any]


def verify_webhook_signature(
    raw_body: Union[bytes, str],
    signature_header: Optional[str],
    secret: str,
) -> bool:
    """Verify the HMAC-SHA256 signature of an AfiniTwin webhook.

    Args:
        raw_body: Exact raw body bytes/string from the request. Don't json.loads first.
        signature_header: Value of the ``X-AfiniTwin-Signature`` header (``sha256=<hex>``).
        secret: Plaintext secret (``whsec_...``) saved when creating the webhook.

    Returns:
        True if the signature is valid, False otherwise.

    Example::

        if not verify_webhook_signature(request.body, request.headers["x-afinitwin-signature"], SECRET):
            raise HTTPException(403)
    """
    if not signature_header:
        return False
    sig_hex = signature_header[7:] if signature_header.startswith("sha256=") else signature_header
    body_bytes = raw_body if isinstance(raw_body, (bytes, bytearray)) else raw_body.encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    if len(sig_hex) != len(expected):
        return False
    return hmac.compare_digest(sig_hex, expected)
