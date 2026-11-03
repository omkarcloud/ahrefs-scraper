"""Ahrefs transport: plain curl_cffi with browser-impersonated TLS, no
browser, no cookies. Two upstream hosts, both open to curl (every surface
200 from a home connection and from datacenter and residential proxy exits
with chrome / safari17_0 impersonation, 2026-11-03; the egress tier is set
by the "ahrefs" knob in config.py, AHREFS_EXIT).

  * FREE-TOOL RPCs  https://ahrefs.com/v4/<name>: JSON in, `["Ok", {...}]`
    or `["Error", ["InvalidCaptcha" | "InvalidUrl" | "InvalidInput", msg]]`
    out (HTTP 200 for most errors, 400 for InvalidInput). Every call carries
    `captcha`: a Cloudflare Turnstile token for site key
    config.AHREFS_TURNSTILE_SITEKEY, minted by CapSolver's proxyless
    Turnstile task in ~3 s (no browser; the token is accepted for any tool
    whatever page URL it was minted for, is single-use, and is not bound to
    the IP that POSTs it — 8/8 through one datacenter exit). The backlinks
    overview also returns a 12-hour `signedInput` that the backlinks LIST
    call takes instead of a captcha. stGetFreeTrafficOverview is a GET
    (?input=<json>), the others POST JSON.

  * AHREFSTOP      https://ahrefstop.com/websites[/<page>|/<country>[/<cat>]]
    and /websites/<domain>[/competitors]: server-rendered HTML, no captcha.
    An unknown domain / list answers a real HTTP 404.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  AhrefsUpstreamError  transport failure / 5xx / odd body       — retryable
  AhrefsBlocked        403 / 429 / challenge / InvalidCaptcha   — retryable
  AhrefsBadRequest     InvalidUrl / InvalidInput                — never retried
  AhrefsNotFound       ahrefstop 404, keyword with no SERP data — never retried
"""
import json
import os
import re
import sys
import threading
import time
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from ahrefs.refs import RPC_BASE, SITE, TOP_SITE

IMPERSONATE = "chrome"
RPC_TIMEOUT = 60      # the sitemap generator crawls up to 1000 URLs
PAGE_TIMEOUT = 40     # ahrefstop list pages are ~1 MB
CAPSOLVER_API = "https://api.capsolver.com"
SOLVE_POLL = 2        # seconds between getTaskResult polls

# Per-request headers; the Accept-Language rides on the session (set from
# its exit when the session is created, egress.accept_language(proxy)).
RPC_HEADERS = {
    "accept": "*/*",
    "content-type": "application/json; charset=utf-8",
    "origin": SITE,
    "referer": SITE + "/free-seo-tools",
}
PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "upgrade-insecure-requests": "1",
}

_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)
_BLOCK_MARKERS = ("just a moment", "attention required", "cf-chl", "challenge-platform")


class AhrefsUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected body — retryable."""


class AhrefsBlocked(AhrefsUpstreamError, Blocked):
    """403 / 429 / challenge page, or a captcha token Ahrefs refused — retryable."""


class AhrefsBadRequest(BadRequest):
    """Ahrefs rejected the input (InvalidUrl / InvalidInput) — never retried."""


class AhrefsNotFound(NotFound):
    """The ahrefstop page does not exist / Ahrefs has no data — never retried."""


class AhrefsCaptchaNotConfigured(RuntimeError):
    """No CAPSOLVER_API_KEY: the free-tool endpoints cannot run at all, so
    this is a configuration error (500, never retried), not a block."""


# One session per cheroot worker thread: a curl handle must not be shared
# across threads; one sticky exit per session, dropped on a retryable failure.
_local = threading.local()


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.ahrefs_proxy()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        sess.headers["accept-language"] = egress.accept_language(proxy)
        _local.session = sess
    return sess


def _drop_session():
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _retrying(fn):
    """Run fn() under the shared retry policy (AhrefsUpstreamError only;
    NotFound / BadRequest surface immediately)."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except AhrefsUpstreamError as e:
            last = e
            _drop_session()
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


# ---- Turnstile tokens (CapSolver) --------------------------------------------

def mint_captcha():
    """One Cloudflare Turnstile token for the free tools (single-use).
    CapSolver's proxyless task; the page URL only has to be on ahrefs.com."""
    key = getattr(config, "CAPSOLVER_API_KEY", "")
    if not key:
        raise AhrefsCaptchaNotConfigured(
            "set CAPSOLVER_API_KEY to use this endpoint: Ahrefs' free tools need a "
            "Cloudflare Turnstile token on every call (see config.py)")
    from curl_cffi import requests as curl_requests
    task = {"type": "AntiTurnstileTaskProxyLess", "websiteURL": config.AHREFS_CAPTCHA_PAGE,
            "websiteKey": config.AHREFS_TURNSTILE_SITEKEY}
    payload = {"clientKey": key, "task": task}
    if getattr(config, "CAPSOLVER_APP_ID", None):
        payload["appId"] = config.CAPSOLVER_APP_ID
    started = time.monotonic()
    try:
        with curl_requests.Session() as s:
            created = s.post(f"{CAPSOLVER_API}/createTask", json=payload, timeout=30).json()
            task_id = created.get("taskId")
            if not task_id:
                raise AhrefsBlocked(f"CapSolver refused the Turnstile task: "
                                    f"{created.get('errorCode')} {created.get('errorDescription')}")
            while time.monotonic() - started < config.AHREFS_SOLVE_TIMEOUT:
                time.sleep(SOLVE_POLL)
                result = s.post(f"{CAPSOLVER_API}/getTaskResult",
                                json={"clientKey": key, "taskId": task_id}, timeout=30).json()
                if result.get("status") == "ready":
                    token = (result.get("solution") or {}).get("token")
                    if not token:
                        raise AhrefsBlocked("CapSolver solved the Turnstile task but returned no token")
                    return token
                if result.get("errorId"):
                    raise AhrefsBlocked(f"CapSolver Turnstile task failed: "
                                        f"{result.get('errorCode')} {result.get('errorDescription')}")
    except AhrefsUpstreamError:
        raise
    except Exception as e:
        raise AhrefsUpstreamError(f"CapSolver request failed: {type(e).__name__}: {e}")
    raise AhrefsUpstreamError(f"CapSolver Turnstile solve timed out after {config.AHREFS_SOLVE_TIMEOUT}s")


# ---- the v4 RPCs -------------------------------------------------------------

def _decode_rpc(resp, name, ok_tags=("Ok",)):
    """`["Ok", payload]` -> payload; the error envelope -> the taxonomy.
    `ok_tags` names the success tags (the backlinks list answers
    `["TopBacklinks", {...}]`, its reportType)."""
    status = resp.status_code
    if status in (401, 403, 429):
        raise AhrefsBlocked(f"HTTP {status} for {name}")
    if status >= 500:
        raise AhrefsUpstreamError(f"HTTP {status} for {name}")
    try:
        envelope = resp.json()
    except Exception:
        head = (resp.text or "")[:200]
        if any(m in head.lower() for m in _BLOCK_MARKERS):
            raise AhrefsBlocked(f"challenge page for {name}")
        raise AhrefsUpstreamError(f"non-JSON reply for {name}: {head}")
    if not isinstance(envelope, list) or not envelope:
        raise AhrefsUpstreamError(f"unexpected reply shape for {name}: {str(envelope)[:200]}")
    tag = envelope[0]
    if tag in ok_tags:
        return envelope[1] if len(envelope) > 1 else None
    if tag == "Error":
        detail = envelope[1] if len(envelope) > 1 else []
        code = detail[0] if isinstance(detail, list) and detail else str(detail)
        message = detail[1] if isinstance(detail, list) and len(detail) > 1 else ""
        if code == "InvalidCaptcha":
            raise AhrefsBlocked("Ahrefs refused the captcha token")
        if code == "InvalidUrl":
            raise AhrefsBadRequest("not a valid domain or page link")
        if code == "InvalidInput":
            raise AhrefsBadRequest(_clean_invalid_input(message))
        raise AhrefsUpstreamError(f"{name}: {code} {message}"[:300])
    if status == 400:
        raise AhrefsBadRequest(str(envelope)[:200])
    raise AhrefsUpstreamError(f"unexpected reply for {name}: {str(envelope)[:200]}")


def _clean_invalid_input(message):
    """'invalid input: Aa_fe_be_country__Country_type.UnknownCountry("zz")'
    -> 'unknown country "zz"' (the OCaml module paths mean nothing to a client)."""
    text = str(message or "")
    match = re.search(r"UnknownCountry\(\"([^\"]*)\"\)", text)
    if match:
        return f'Ahrefs has no data for country "{match.group(1)}"'
    match = re.search(r"UnknownMode\(\"([^\"]*)\"\)", text)
    if match:
        return f'unknown mode "{match.group(1)}"'
    match = re.search(r"expected (\".*?\"(?: or \".*?\")*) but got (\"[^\"]*\")", text)
    if match:
        return f"expected one of {match.group(1)}, got {match.group(2)}"
    return text[:300] or "invalid input"


def rpc(name, body, *, method="POST", captcha=True, ok_tags=("Ok",)):
    """Call one free-tool RPC and return its `Ok` payload. With captcha=True a
    fresh Turnstile token is minted per attempt (they are single-use)."""
    def once():
        payload = dict(body)
        if captcha:
            payload["captcha"] = mint_captcha()
        try:
            if method == "GET":
                url = RPC_BASE + name + "?input=" + quote(json.dumps(payload, separators=(",", ":")))
                resp = _session().get(url, headers=RPC_HEADERS, timeout=RPC_TIMEOUT)
            else:
                resp = _session().post(RPC_BASE + name, data=json.dumps(payload, separators=(",", ":")),
                                       headers=RPC_HEADERS, timeout=RPC_TIMEOUT)
        except Exception as e:
            raise AhrefsUpstreamError(f"request failed: {type(e).__name__}: {e}")
        return _decode_rpc(resp, name, ok_tags)
    return _retrying(once)


def website_overview(target):
    return rpc("stGetFreeWebsiteOverview", {"url": target})


def backlinks_overview(target, mode):
    return rpc("stGetFreeBacklinksOverview", {"url": target, "mode": mode})


def backlinks_list(signed_input):
    """The top-20 backlinks; takes the overview's signedInput, no captcha."""
    return rpc("stGetFreeBacklinksList", {"signedInput": signed_input, "reportType": ["TopBacklinks"]},
               captcha=False, ok_tags=("Ok", "TopBacklinks"))


def traffic_overview(target, mode, country=None):
    return rpc("stGetFreeTrafficOverview",
               {"url": target, "mode": mode, "country": country, "protocol": "both"}, method="GET")


def broken_links(target, mode):
    return rpc("stGetFreeBrokenLinksList", {"url": target, "mode": mode})


def sitemap(target):
    return rpc("stGetFreeSitemapGenerator", {"url": target})


def keyword_ideas(keyword, country, search_engine, with_questions):
    return rpc("stGetFreeKeywordIdeas", {"keyword": keyword, "country": country,
                                         "searchEngine": search_engine, "withQuestionIdeas": bool(with_questions)})


def keyword_difficulty(keyword, country):
    """SERP overview + the KD score (shortage = referring domains needed)."""
    return rpc("stGetFreeSerpOverviewForKeywordDifficultyChecker", {"keyword": keyword, "country": country})


def keyword_rank(keyword, country, domain):
    return rpc("stGetFreeSerpOverviewForKeywordRankChecker",
               {"keyword": keyword, "country": country, "domain": domain})


def ai_visibility(brand):
    return rpc("stGetFreeAIVisibilityOverview", {"brand": brand})


def ai_overviews(brand):
    return rpc("stGetFreeAIOverviewsTrackerOverview", {"brand": brand})


def ai_mode(brand):
    return rpc("stGetFreeAIModeTrackerOverview", {"brand": brand})


# ---- ahrefstop.com pages -----------------------------------------------------

def _page_title(text):
    match = _TITLE_RE.search(text or "")
    return match.group(1).strip() if match else ""


def top_page(path, label):
    """GET one ahrefstop.com page; 404 -> AhrefsNotFound."""
    def once():
        try:
            resp = _session().get(TOP_SITE + path, headers=PAGE_HEADERS, timeout=PAGE_TIMEOUT)
        except Exception as e:
            raise AhrefsUpstreamError(f"request failed: {type(e).__name__}: {e}")
        if resp.status_code == 404:
            raise AhrefsNotFound(f"{label} not found")
        if resp.status_code in (401, 403, 429):
            raise AhrefsBlocked(f"HTTP {resp.status_code} for {label}")
        if resp.status_code != 200:
            raise AhrefsUpstreamError(f"HTTP {resp.status_code} for {label}")
        text = resp.text
        title = _page_title(text).lower()
        if title.startswith("404"):
            raise AhrefsNotFound(f"{label} not found")
        if any(m in text[:3000].lower() for m in _BLOCK_MARKERS):
            raise AhrefsBlocked(f"challenge page for {label}")
        return text
    return _retrying(once)


def website_page(domain):
    return top_page(f"/websites/{domain}", f"website {domain}")


def competitors_page(domain):
    return top_page(f"/websites/{domain}/competitors", f"competitors of {domain}")


def top_list_page(path):
    return top_page(path, f"top websites {path}")
