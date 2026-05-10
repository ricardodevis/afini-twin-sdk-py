# afini-twin-sdk

Official Python SDK for the [AfiniTwin B2B API](https://afini.ai/afinitwin/api).

The AfiniTwin is a portable cognitive profile (Big Five + 5 supplementary layers) built on the [Afini.ai](https://afini.ai) platform. This SDK gives you typed access to a user's snapshot from your own systems — CRMs, custom assistants, internal pipelines.

## Installation

```bash
pip install afini-twin-sdk
```

Requires Python ≥ 3.10. Built on [httpx](https://www.python-httpx.org/) and [pydantic v2](https://docs.pydantic.dev/).

## Get an API key

Active users with a Professional plan on Afini.ai can generate keys at [afini.ai/dashboard/twin/api](https://afini.ai/dashboard/twin/api). The key is shown **once** — store it securely.

## Quick start

### Async

```python
import asyncio
import os
from afini_twin import AfiniTwinClient

async def main():
    async with AfiniTwinClient(api_key=os.environ["AFINITWIN_KEY"]) as client:
        me = await client.me()
        print(f"User has {me['twins']['ready']} ready snapshots; quota {me['quota']['remaining']}/{me['quota']['monthlyLimit']}")

        snapshots = await client.historic()
        for s in snapshots["snapshots"]:
            print(s["id"], s["snapshotDate"])

        # Download standard preset as Markdown
        md = await client.preset("estandar", format="md", lang="es")
        print(md[:200], "…")

asyncio.run(main())
```

### Sync

```python
from afini_twin import AfiniTwinSyncClient

with AfiniTwinSyncClient(api_key=os.environ["AFINITWIN_KEY"]) as client:
    me = client.me()
```

## Sending data into the user's profile (`twin:write` scope)

If your API key has the `twin:write` scope, you can seed life-facts and annotations. They go to the user's review queue at `/dashboard/discoveries`; **nothing is injected into the profile until the user approves**.

```python
from afini_twin import AfiniTwinClient, LifeFactInput

async with AfiniTwinClient(api_key=os.environ["AFINITWIN_KEY"]) as client:
    result = await client.life_facts_create([
        LifeFactInput(
            category="professional",
            value="Trabaja en una startup de IA en Bilbao desde 2023",
            valence="positive",
            consent=True,
            external_ref="crm-12345",
        )
    ])
    print(result["accepted"], "candidates queued ->", result["inboxUrl"])
```

For free-form notes:

```python
from afini_twin import AnnotationInput

await client.annotations_create([
    AnnotationInput(tag="observation", text="Mostró interés por escalar a Pro", consent=True)
])
```

The pydantic models reject `consent != True` at validation time — you can't accidentally submit without an explicit confirmation.

## Verifying webhook signatures

Every webhook POST carries an `X-AfiniTwin-Signature: sha256=<hmac>` header. Verify before trusting the payload:

### FastAPI

```python
from fastapi import FastAPI, Request, HTTPException
from afini_twin import verify_webhook_signature

app = FastAPI()
SECRET = os.environ["AFINITWIN_WEBHOOK_SECRET"]

@app.post("/webhooks/afinitwin")
async def afinitwin_hook(request: Request):
    raw = await request.body()
    sig = request.headers.get("x-afinitwin-signature")
    if not verify_webhook_signature(raw, sig, SECRET):
        raise HTTPException(403)
    payload = await request.json()
    if payload["event"] == "twin.snapshot.ready":
        # … pull the new snapshot
        pass
    elif payload["event"] == "twin.quota.exceeded":
        # … alert your billing
        pass
    return {"ok": True}
```

### Django / Flask

The function is framework-agnostic: pass the **raw body** (bytes or str) plus the header value plus the secret.

## Error handling

```python
from afini_twin import AfiniTwinClient, AfiniTwinApiError

try:
    async with AfiniTwinClient(api_key=key) as client:
        await client.me()
except AfiniTwinApiError as e:
    if e.status == 429 and e.body and e.body.get("code") == "TIER_QUOTA_EXCEEDED":
        # upgrade your B2B tier
        ...
    raise
```

## Rate limits

| Endpoint group | Per minute | Per month |
|----------------|------------|-----------|
| `/health` | 120 | unlimited |
| `/me`, `/historic`, `/snapshots/*`, `/preset/*` | 60 | per tier |
| `/life-facts`, `/annotations` | 30 | per tier |

The monthly cap is enforced **per user across all keys** based on the B2B tier (Included = 10k, Starter = 100k, Pro = 1M, Enterprise = custom).

## License

MIT © [Bilbao AI S.L.](https://afini.ai)
