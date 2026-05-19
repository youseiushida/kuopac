"""``HttpSession`` invariants — lazy CSRF preflight + 403 retry."""
from __future__ import annotations

import httpx
import pytest

from kuopac._http import HttpSession
from kuopac.errors import CSRFError, ForbiddenError


CSRF_LANDING = """
<html><body>
<form><input type='hidden' name='csrfmiddlewaretoken' value='tok-1' /></form>
</body></html>
"""

CSRF_LANDING_REFRESHED = """
<html><body>
<form><input type='hidden' name='csrfmiddlewaretoken' value='tok-2' /></form>
</body></html>
"""


def _session(handler) -> HttpSession:
    return HttpSession(transport=httpx.MockTransport(handler))


def test_get_does_not_trigger_csrf_preflight() -> None:
    """Pure-GET workflows must never warm up the CSRF cache."""
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, text="ok")

    s = _session(handler)
    s.get("/opac/opac_search/", params={"kywd": "x"})
    s.get("/opac/opac_search/", params={"kywd": "y"})
    s.close()
    assert len(seen) == 2
    assert all(r.method == "GET" for r in seen)


def test_lazy_csrf_token_parsed_from_landing_html() -> None:
    methods: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        methods.append(req.method)
        if req.method == "GET":
            return httpx.Response(200, text=CSRF_LANDING)
        return httpx.Response(200, text="ok")

    s = _session(handler)
    s.post("/opac/opac_search_localhold/", data={"x": "y"})
    s.close()
    # First call: GET preflight, then POST.
    assert methods == ["GET", "POST"]
    assert s._csrf == "tok-1"


def test_csrf_token_cached_across_posts() -> None:
    method_counts = {"GET": 0, "POST": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        method_counts[req.method] += 1
        if req.method == "GET":
            return httpx.Response(200, text=CSRF_LANDING)
        return httpx.Response(200, text="ok")

    s = _session(handler)
    s.post("/opac/opac_search_localhold/", data={})
    s.post("/opac/opac_search_localhold/", data={})
    s.close()
    assert method_counts == {"GET": 1, "POST": 2}


def test_post_403_refreshes_csrf_then_succeeds() -> None:
    """Spec §0.3 — a stale CSRF token causes a 403 on POST; the session must
    refetch and retry once before giving up."""
    state = {"posts": 0, "gets": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            state["gets"] += 1
            return httpx.Response(
                200,
                text=CSRF_LANDING if state["gets"] == 1 else CSRF_LANDING_REFRESHED,
            )
        state["posts"] += 1
        if state["posts"] == 1:
            return httpx.Response(403, text="stale token")
        return httpx.Response(200, text="ok")

    s = _session(handler)
    r = s.post("/opac/opac_search_localhold/", data={"x": "y"})
    s.close()
    assert r.status_code == 200
    assert state == {"posts": 2, "gets": 2}
    assert s._csrf == "tok-2"


def test_persistent_403_raises_csrf_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            return httpx.Response(200, text=CSRF_LANDING)
        return httpx.Response(403, text="nope")

    s = _session(handler)
    with pytest.raises(CSRFError):
        s.post("/opac/opac_search_localhold/", data={"x": "y"})
    s.close()


def test_csrf_missing_from_landing_raises() -> None:
    s = _session(lambda r: httpx.Response(200, text="<html>no token</html>"))
    with pytest.raises(CSRFError):
        s.post("/opac/opac_search_localhold/", data={})
    s.close()


def test_get_403_raises_forbidden() -> None:
    s = _session(lambda r: httpx.Response(403, text="no referer"))
    with pytest.raises(ForbiddenError):
        s.get("/opac/opac_details/", params={"bibid": "BB1"})
    s.close()


def test_referer_header_is_attached() -> None:
    seen: list[httpx.Request] = []
    s = _session(lambda r: (seen.append(r), httpx.Response(200, text="ok"))[1])
    s.get("/opac/opac_details/", params={"bibid": "BB1"})
    s.close()
    assert seen[0].headers["referer"].endswith("/opac/opac_search/?lang=0")


def test_post_sends_csrftoken_header_and_field() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.method == "GET":
            return httpx.Response(200, text=CSRF_LANDING)
        return httpx.Response(200, text="ok")

    s = _session(handler)
    s.post("/opac/opac_search_localhold/", data={"lang": "0"})
    post = next(r for r in seen if r.method == "POST")
    s.close()
    assert post.headers["x-csrftoken"] == "tok-1"
    assert post.headers["x-requested-with"] == "XMLHttpRequest"
    body = post.content
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    assert "csrfmiddlewaretoken=tok-1" in body
