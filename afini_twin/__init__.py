"""
afini-twin-sdk — Official Python SDK for the AfiniTwin B2B API.

Quick start:

    from afini_twin import AfiniTwinClient

    async with AfiniTwinClient(api_key="atk_live_...") as client:
        me = await client.me()
        snapshots = await client.historic()
        md = await client.preset("estandar", format="md", lang="es")

Sync version:

    with AfiniTwinClient.sync(api_key="atk_live_...") as client:
        me = client.me()

Verify webhook signatures:

    from afini_twin import verify_webhook_signature

    if not verify_webhook_signature(raw_body, request.headers["x-afinitwin-signature"], secret):
        return Response(status_code=403)
"""
from .client import (
    AfiniTwinClient,
    AfiniTwinSyncClient,
    AfiniTwinApiError,
    LifeFactInput,
    AnnotationInput,
    PresetOptions,
)
from .webhooks import verify_webhook_signature, WebhookEventType, WebhookPayload

__version__ = "0.1.0"

__all__ = [
    "AfiniTwinClient",
    "AfiniTwinSyncClient",
    "AfiniTwinApiError",
    "LifeFactInput",
    "AnnotationInput",
    "PresetOptions",
    "verify_webhook_signature",
    "WebhookEventType",
    "WebhookPayload",
]
