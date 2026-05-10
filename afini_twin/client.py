"""
afini-twin client — async-first (httpx) with sync wrapper.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict, Union, overload

import httpx
from pydantic import BaseModel, Field, field_validator


AFINITWIN_API_BASE = "https://api.afini.ai"

LifeFactCategory = Literal[
    "professional",
    "family",
    "partner",
    "hobbies",
    "health",
    "environment",
    "decisions",
    "conflict",
    "exploration",
    "recalibration",
    "general",
]
Valence = Literal["positive", "negative", "aspirational", "ambiguous"]
TwinFormat = Literal["txt", "md", "json", "yaml"]
TwinLang = Literal["es", "en", "fr", "de", "it", "pt"]
TwinVariant = Literal["claude", "gpt", "gemini", "generic"]


class LifeFactInput(BaseModel):
    """One life-fact submission. Requires consent=True."""

    category: LifeFactCategory
    value: str = Field(min_length=3, max_length=1000)
    valence: Valence = "positive"
    consent: bool
    external_ref: Optional[str] = Field(default=None, max_length=200, alias="externalRef")
    confidence: Optional[float] = Field(default=None, ge=0, le=1)

    model_config = {"populate_by_name": True}

    @field_validator("consent")
    @classmethod
    def _consent_must_be_true(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("consent must be True (explicit confirmation)")
        return v


class AnnotationInput(BaseModel):
    """One annotation submission. Requires consent=True."""

    tag: str = Field(min_length=2, max_length=60)
    text: str = Field(min_length=3, max_length=2000)
    consent: bool
    external_ref: Optional[str] = Field(default=None, max_length=200, alias="externalRef")

    model_config = {"populate_by_name": True}

    @field_validator("consent")
    @classmethod
    def _consent_must_be_true(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("consent must be True (explicit confirmation)")
        return v


class PresetOptions(TypedDict, total=False):
    format: TwinFormat
    lang: TwinLang
    variant: TwinVariant
    includeNarratives: bool
    purchaseId: str


class AfiniTwinApiError(Exception):
    """API error with HTTP status + structured body."""

    def __init__(self, status: int, body: Optional[dict[str, Any]], message: Optional[str] = None) -> None:
        self.status = status
        self.body = body
        msg = message or (body or {}).get("message") or f"AfiniTwin API error {status}"
        super().__init__(msg)


# ─────────────────────────────────────────────────────────────────
# Async client (default)
# ─────────────────────────────────────────────────────────────────

class AfiniTwinClient:
    """Async client. Use as async context manager.

    Example::

        async with AfiniTwinClient(api_key="atk_live_...") as client:
            me = await client.me()
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = AFINITWIN_API_BASE,
        timeout: float = 30.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if not api_key.startswith("atk_live_"):
            raise ValueError('AfiniTwinClient: api_key must start with "atk_live_"')
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client
        self._owned_client = client is None

    @classmethod
    def sync(
        cls,
        api_key: str,
        *,
        base_url: str = AFINITWIN_API_BASE,
        timeout: float = 30.0,
    ) -> "AfiniTwinSyncClient":
        """Return a synchronous client (httpx.Client under the hood)."""
        return AfiniTwinSyncClient(api_key=api_key, base_url=base_url, timeout=timeout)

    async def __aenter__(self) -> "AfiniTwinClient":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owned_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── public API ──

    async def health(self) -> dict[str, Any]:
        """Quick health check. Doesn't consume monthly quota."""
        return await self._request("GET", "/v1/public/twin/health")

    async def me(self) -> dict[str, Any]:
        """Identity + plan + quota of the API key owner."""
        return await self._request("GET", "/v1/public/twin/me")

    async def historic(self) -> dict[str, Any]:
        """List all snapshots (twin purchases) of the user."""
        return await self._request("GET", "/v1/public/twin/historic")

    async def snapshot(self, snapshot_id: str) -> dict[str, Any]:
        """Single snapshot metadata."""
        return await self._request("GET", f"/v1/public/twin/snapshots/{snapshot_id}")

    async def preset(
        self,
        slug: str,
        *,
        format: Optional[TwinFormat] = None,
        lang: Optional[TwinLang] = None,
        variant: Optional[TwinVariant] = None,
        include_narratives: Optional[bool] = None,
        purchase_id: Optional[str] = None,
    ) -> Union[str, dict[str, Any]]:
        """Download a preset artifact. Returns dict for json, str for txt/md/yaml."""
        params: dict[str, str] = {}
        if format:
            params["format"] = format
        if lang:
            params["lang"] = lang
        if variant:
            params["variant"] = variant
        if include_narratives is not None:
            params["includeNarratives"] = str(include_narratives).lower()
        if purchase_id:
            params["purchaseId"] = purchase_id

        path = f"/v1/public/twin/preset/{slug}"
        client = self._ensure_client()
        resp = await client.get(
            f"{self.base_url}{path}",
            params=params,
            headers=self._headers(),
        )
        await self._assert_ok(resp, path)
        if format == "json" or format is None:
            return resp.json()
        return resp.text

    async def life_facts_create(self, facts: list[LifeFactInput]) -> dict[str, Any]:
        """Submit life-facts to the user's review queue (twin:write scope required)."""
        body = {"facts": [f.model_dump(by_alias=True, exclude_none=True) for f in facts]}
        return await self._request("POST", "/v1/public/twin/life-facts", json=body)

    async def annotations_create(self, annotations: list[AnnotationInput]) -> dict[str, Any]:
        """Submit annotations to the user's review queue (twin:write scope required)."""
        body = {"annotations": [a.model_dump(by_alias=True, exclude_none=True) for a in annotations]}
        return await self._request("POST", "/v1/public/twin/annotations", json=body)

    # ── internals ──

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
            self._owned_client = True
        return self._client

    def _headers(self) -> dict[str, str]:
        return {
            "X-Twin-Key": self.api_key,
            "User-Agent": "afini-twin-sdk-py/0.1.0",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, *, json: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        client = self._ensure_client()
        resp = await client.request(method, f"{self.base_url}{path}", json=json, headers=self._headers())
        await self._assert_ok(resp, path)
        return resp.json()

    async def _assert_ok(self, resp: httpx.Response, path: str) -> None:
        if resp.is_success:
            return
        body: Optional[dict[str, Any]] = None
        try:
            j = resp.json()
            body = j.get("error") if isinstance(j, dict) else None
        except Exception:
            pass
        raise AfiniTwinApiError(resp.status_code, body, f"{resp.status_code} {path}")


# ─────────────────────────────────────────────────────────────────
# Sync client (thin wrapper over httpx.Client)
# ─────────────────────────────────────────────────────────────────

class AfiniTwinSyncClient:
    """Synchronous client. Mirrors AfiniTwinClient methods.

    Example::

        with AfiniTwinSyncClient(api_key="atk_live_...") as client:
            me = client.me()
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = AFINITWIN_API_BASE,
        timeout: float = 30.0,
    ) -> None:
        if not api_key.startswith("atk_live_"):
            raise ValueError('AfiniTwinSyncClient: api_key must start with "atk_live_"')
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    def __enter__(self) -> "AfiniTwinSyncClient":
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _ensure(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _headers(self) -> dict[str, str]:
        return {
            "X-Twin-Key": self.api_key,
            "User-Agent": "afini-twin-sdk-py/0.1.0",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, *, json: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        client = self._ensure()
        resp = client.request(method, f"{self.base_url}{path}", json=json, headers=self._headers())
        if not resp.is_success:
            body: Optional[dict[str, Any]] = None
            try:
                j = resp.json()
                body = j.get("error") if isinstance(j, dict) else None
            except Exception:
                pass
            raise AfiniTwinApiError(resp.status_code, body, f"{resp.status_code} {path}")
        return resp.json()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/v1/public/twin/health")

    def me(self) -> dict[str, Any]:
        return self._request("GET", "/v1/public/twin/me")

    def historic(self) -> dict[str, Any]:
        return self._request("GET", "/v1/public/twin/historic")

    def snapshot(self, snapshot_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/public/twin/snapshots/{snapshot_id}")

    def preset(
        self,
        slug: str,
        *,
        format: Optional[TwinFormat] = None,
        lang: Optional[TwinLang] = None,
        variant: Optional[TwinVariant] = None,
        include_narratives: Optional[bool] = None,
        purchase_id: Optional[str] = None,
    ) -> Union[str, dict[str, Any]]:
        params: dict[str, str] = {}
        if format:
            params["format"] = format
        if lang:
            params["lang"] = lang
        if variant:
            params["variant"] = variant
        if include_narratives is not None:
            params["includeNarratives"] = str(include_narratives).lower()
        if purchase_id:
            params["purchaseId"] = purchase_id
        client = self._ensure()
        resp = client.get(f"{self.base_url}/v1/public/twin/preset/{slug}", params=params, headers=self._headers())
        if not resp.is_success:
            raise AfiniTwinApiError(resp.status_code, None, f"{resp.status_code} preset")
        if format == "json" or format is None:
            return resp.json()
        return resp.text

    def life_facts_create(self, facts: list[LifeFactInput]) -> dict[str, Any]:
        body = {"facts": [f.model_dump(by_alias=True, exclude_none=True) for f in facts]}
        return self._request("POST", "/v1/public/twin/life-facts", json=body)

    def annotations_create(self, annotations: list[AnnotationInput]) -> dict[str, Any]:
        body = {"annotations": [a.model_dump(by_alias=True, exclude_none=True) for a in annotations]}
        return self._request("POST", "/v1/public/twin/annotations", json=body)
