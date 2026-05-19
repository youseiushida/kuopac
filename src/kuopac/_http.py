"""
Internal HTTP layer — handles KULINE's legacy TLS requirement and lazy CSRF.
"""
from __future__ import annotations

import re
import ssl
from typing import Any

import httpx

from .errors import CSRFError, ForbiddenError

BASE_URL = "https://kuline.kulib.kyoto-u.ac.jp"
DEFAULT_REFERER = f"{BASE_URL}/opac/opac_search/?lang=0"
DEFAULT_UA = "kuopac/0.1 (+https://github.com/local/kuopac)"

_CSRF_RE = re.compile(
    r"""name=['"]csrfmiddlewaretoken['"]\s+value=['"]([^'"]+)['"]"""
)


def make_ssl_context() -> ssl.SSLContext:
    """SSL context KULINE will negotiate with.

    KULINE rejects modern-only cipher lists with TLSV1_ALERT_INSUFFICIENT_SECURITY;
    we lower OpenSSL's security level so legacy ciphers are on the table.
    """
    ctx = ssl.create_default_context()
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=0")
    except ssl.SSLError:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    return ctx


class HttpSession:
    """Thin wrapper over httpx.Client with KULINE-specific defaults.

    The session is **stateless for GET** — the only state it caches is a CSRF
    token for POSTs (lazy-fetched on first use).
    """

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_UA,
        referer: str = DEFAULT_REFERER,
        timeout: float = 30.0,
        verify: Any = None,
        transport: httpx.BaseTransport | None = None,
    ):
        # ``transport`` is the test-injection point — pass an
        # ``httpx.MockTransport`` to replay canned responses without touching
        # the real network or the legacy-cipher SSL handshake.
        client_kwargs: dict[str, Any] = {
            "base_url": BASE_URL,
            "follow_redirects": True,
            "timeout": timeout,
            "headers": {
                "User-Agent": user_agent,
                "Referer": referer,        # silences 403 on opac_details/
                "Accept-Language": "ja",
            },
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        else:
            client_kwargs["verify"] = (
                verify if verify is not None else make_ssl_context()
            )
        self._client = httpx.Client(**client_kwargs)
        self._csrf: str | None = None

    # ---- request helpers -------------------------------------------------

    def get(self, path: str, *, params: dict | None = None,
            headers: dict | None = None) -> httpx.Response:
        r = self._client.get(path, params=params, headers=headers)
        if r.status_code == 403:
            raise ForbiddenError(
                f"GET {r.request.url} → 403. Pass `Referer` header or warm session."
            )
        return r

    def post(self, path: str, *, data: dict | None = None,
             headers: dict | None = None) -> httpx.Response:
        csrf = self._ensure_csrf()
        merged = {
            "X-CSRFToken": csrf,
            "X-Requested-With": "XMLHttpRequest",
            **(headers or {}),
        }
        body = {"csrfmiddlewaretoken": csrf, **(data or {})}
        r = self._client.post(path, data=body, headers=merged)
        if r.status_code == 403:
            # CSRF probably stale — refresh and retry once
            self._csrf = None
            csrf = self._ensure_csrf()
            merged["X-CSRFToken"] = csrf
            body["csrfmiddlewaretoken"] = csrf
            r = self._client.post(path, data=body, headers=merged)
            if r.status_code == 403:
                raise CSRFError(f"POST {r.request.url} → 403 even after CSRF refresh")
        return r

    # ---- CSRF lifecycle --------------------------------------------------

    def _ensure_csrf(self) -> str:
        if self._csrf is None:
            r = self._client.get("/opac/opac_search/", params={"lang": "0"})
            m = _CSRF_RE.search(r.text)
            if not m:
                raise CSRFError("Could not extract csrfmiddlewaretoken from landing")
            self._csrf = m.group(1)
        return self._csrf

    # ---- lifecycle -------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
