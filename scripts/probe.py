"""
KULINE OPAC live investigation toolkit.

Saves every request/response to probe_data/<label>/{req.json,resp.html|json}.
Maintains a single httpx.Client so cookies persist (Django sessionid + csrftoken).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import ssl

import httpx

BASE = "https://kuline.kulib.kyoto-u.ac.jp"


def _make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    # KULINE rejects modern-only cipher suites with TLSV1_ALERT_INSUFFICIENT_SECURITY;
    # lower the OpenSSL security level so legacy/weak ciphers are negotiable.
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=0")
    except ssl.SSLError:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    return ctx
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "probe_data"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 "
    "(kuopac research probe; contact: nezowarui0504@gmail.com)"
)

DELAY_SEC = 1.5  # be nice to a university OPAC


@dataclass
class Probe:
    client: httpx.Client = field(default_factory=lambda: httpx.Client(
        base_url=BASE,
        headers={"User-Agent": UA, "Accept-Language": "ja,en-US;q=0.7,en;q=0.3"},
        follow_redirects=True,
        timeout=30.0,
        verify=_make_ssl_context(),
    ))
    log: list[dict[str, Any]] = field(default_factory=list)
    last_csrf: str | None = None
    last_opkey: str | None = None

    def _save(self, label: str, *, method: str, url: str, params=None,
              data=None, status: int, resp_headers: dict, body: bytes,
              note: str = "") -> Path:
        slug = re.sub(r"[^A-Za-z0-9_\-]", "_", label)[:80]
        ts = time.strftime("%Y%m%dT%H%M%S")
        dir_ = DATA / f"{ts}_{slug}"
        dir_.mkdir(parents=True, exist_ok=True)
        meta = {
            "label": label,
            "note": note,
            "method": method,
            "url": url,
            "params": params,
            "data": data,
            "status": status,
            "headers": dict(resp_headers),
        }
        (dir_ / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        ext = "html"
        ctype = resp_headers.get("content-type", "")
        if "json" in ctype:
            ext = "json"
        elif "javascript" in ctype:
            ext = "js"
        (dir_ / f"body.{ext}").write_bytes(body)
        self.log.append({"label": label, "dir": str(dir_.relative_to(ROOT))})
        return dir_

    def get(self, path: str, *, params=None, label: str = "", note: str = "",
            extra_headers: dict | None = None) -> httpx.Response:
        url = urljoin(BASE, path)
        headers = {}
        if extra_headers:
            headers.update(extra_headers)
        if label and ("_=" in (urlencode(params or {})) or any(k in (params or {}) for k in ("_",))):
            pass
        r = self.client.get(path, params=params, headers=headers or None)
        self._save(label or path, method="GET", url=str(r.request.url),
                   params=params, data=None, status=r.status_code,
                   resp_headers=r.headers, body=r.content, note=note)
        self._scrape_tokens(r)
        time.sleep(DELAY_SEC)
        return r

    def post(self, path: str, *, data=None, label: str = "", note: str = "",
             extra_headers: dict | None = None) -> httpx.Response:
        url = urljoin(BASE, path)
        headers = {"Referer": f"{BASE}/opac/opac_search/?lang=0"}
        if extra_headers:
            headers.update(extra_headers)
        r = self.client.post(path, data=data, headers=headers)
        self._save(label or path, method="POST", url=str(r.request.url),
                   params=None, data=data, status=r.status_code,
                   resp_headers=r.headers, body=r.content, note=note)
        self._scrape_tokens(r)
        time.sleep(DELAY_SEC)
        return r

    def _scrape_tokens(self, r: httpx.Response) -> None:
        if "text/html" in r.headers.get("content-type", ""):
            txt = r.text
            m = re.search(r"name=['\"]csrfmiddlewaretoken['\"] value=['\"]([^'\"]+)['\"]", txt)
            if m:
                self.last_csrf = m.group(1)
            m = re.search(r"name=['\"]opkey['\"] value=['\"]([^'\"]+)['\"]", txt)
            if m:
                self.last_opkey = m.group(1)
            else:
                m = re.search(r"opkey=([A-Z]\d+)", txt)
                if m:
                    self.last_opkey = m.group(1)

    def cookies(self) -> dict:
        return {c.name: c.value for c in self.client.cookies.jar}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="List runnable probes")
    parser.add_argument("probes", nargs="*", help="Probe names to run (all if empty)")
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    import probes  # type: ignore
    registry = probes.REGISTRY

    if args.list:
        for name, (fn, doc) in registry.items():
            print(f"  {name:30s} {doc}")
        return 0

    names = args.probes or list(registry)
    p = Probe()
    try:
        for name in names:
            if name not in registry:
                print(f"!! unknown probe: {name}", file=sys.stderr)
                continue
            fn, doc = registry[name]
            print(f"== probe: {name}  --  {doc}")
            fn(p)
    finally:
        (DATA / f"_session_log_{time.strftime('%Y%m%dT%H%M%S')}.json").write_text(
            json.dumps({"log": p.log, "cookies": p.cookies(),
                        "last_csrf": p.last_csrf, "last_opkey": p.last_opkey},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        p.client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
