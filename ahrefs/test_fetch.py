"""Offline tests for the Ahrefs exit tiers (ahrefs/fetch.py): the pod's own
IP, the gateway exit for the hold after an exit refusal, a datacenter exit
as the last retry of a call the gateway also failed (2026-11-11). No
network: egress.new_session is replaced by scripted sessions and the
Turnstile mint by a counter.

    python -m pytest ahrefs/test_fetch.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ahrefs import fetch as F  # noqa: E402
from scraper_utils.testing import hosted_only

DC = "http://user:pw@dc.example:823"


class Resp:
    def __init__(self, status=200, body=("Ok", {"domainRating": 90})):
        self.status_code = status
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        return json.loads(self.text)


class Sess:
    def __init__(self, exit_, responses):
        self.exit, self.responses, self.headers, self.closed = exit_, responses, {}, False

    def post(self, url, **kwargs):
        out = self.responses.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    get = post

    def close(self):
        self.closed = True


@pytest.fixture
def tiers(monkeypatch):
    """`tiers.script({exit: [response, ...]})`; `tiers.built` lists the exit
    of every session built, `tiers.tokens` the Turnstile mints."""
    monkeypatch.setattr(F.config, "AHREFS_EXIT", "direct")
    monkeypatch.setattr(F.config, "AHREFS_FALLBACK_EXIT", "gateway")
    monkeypatch.setattr(F.config, "AHREFS_BLOCK_HOLD_S", 600)
    monkeypatch.setattr(F.config, "datacenter_proxy", lambda *a, **k: DC)
    monkeypatch.setattr(F.config, "MAX_RETRIES", 3)
    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    monkeypatch.setattr(F, "_hold_until", 0.0)
    scripted, built, tokens = {}, [], []

    def new_session(exit_, impersonate="chrome", **kw):
        built.append(exit_)
        return Sess(exit_, scripted.setdefault(exit_, []))

    monkeypatch.setattr(F.egress, "new_session", new_session)
    monkeypatch.setattr(F, "mint_captcha", lambda: tokens.append("tok") or "tok")
    F._local.__dict__.clear()
    F.script = lambda by_exit: scripted.update(by_exit)
    F.built, F.tokens = built, tokens
    yield F
    F._local.__dict__.clear()


@hosted_only
def test_knobs_name_the_gateway_as_the_block_tier_and_a_datacenter_exit_as_the_last_retry(tiers):
    assert F.config.ahrefs_proxy() is None
    assert F.config.ahrefs_block_proxy() == "gateway"
    assert F.config.ahrefs_block_proxy(last=True) == DC


@hosted_only
def test_an_exit_refusal_on_the_own_ip_moves_the_retry_and_new_sessions_to_the_gateway(tiers):
    F.script({None: [Resp(403, "<html>Just a moment...</html>")], "gateway": [Resp(), Resp()]})
    assert F.website_overview("tesla.com") == {"domainRating": 90}
    assert F.built == [None, "gateway"] and F._hold_until > 0
    assert F.website_overview("bbc.com") == {"domainRating": 90}
    assert F.built == [None, "gateway"]                        # the thread's gateway session, reused during the hold


@hosted_only
def test_the_gateway_session_ends_with_the_hold(tiers, monkeypatch):
    F.script({None: [Resp(429, "slow"), Resp()], "gateway": [Resp()]})
    assert F.website_overview("tesla.com") == {"domainRating": 90}
    monkeypatch.setattr(F, "_hold_until", 0.0)             # the hold ran out
    assert F.website_overview("bbc.com") == {"domainRating": 90}
    assert F.built == [None, "gateway", None]


@hosted_only
def test_a_refused_captcha_token_starts_no_hold(tiers):
    F.script({None: [Resp(200, ["Error", ["InvalidCaptcha", ""]]), Resp()]})
    assert F.website_overview("tesla.com") == {"domainRating": 90}
    assert F.built == [None, None] and F._hold_until == 0.0 and len(F.tokens) == 2


@hosted_only
def test_a_gateway_failure_degrades_to_a_datacenter_exit_on_the_last_retry(tiers):
    F.script({None: [Resp(403, "denied")], "gateway": [RuntimeError("GatewayError: gateway 504")], DC: [Resp(), Resp()]})
    assert F.website_overview("tesla.com") == {"domainRating": 90}
    assert F.built == [None, "gateway", DC]
    assert F._local.session is None and not F._local.last_resort     # the datacenter session ended with the call
    F.script({"gateway": [Resp()]})
    assert F.website_overview("bbc.com") == {"domainRating": 90} and F.built[-1] == "gateway"     # the hold: gateway first again


@hosted_only
def test_during_the_hold_a_call_tries_the_gateway_twice_then_a_datacenter_exit(tiers):
    F._note_block()
    F.script({"gateway": [Resp(403, "denied"), Resp(429, "slow")], DC: [Resp()]})
    assert F.website_overview("tesla.com") == {"domainRating": 90}
    assert F.built == ["gateway", "gateway", DC]


@hosted_only
def test_a_captcha_refusal_on_the_gateway_buys_no_datacenter_retry(tiers):
    F._note_block()
    bad = Resp(200, ["Error", ["InvalidCaptcha", ""]])
    F.script({"gateway": [bad, bad, Resp()]})
    assert F.website_overview("tesla.com") == {"domainRating": 90}
    assert F.built == ["gateway", "gateway", "gateway"]


@hosted_only
def test_with_a_datacenter_block_tier_or_none_no_last_resort(tiers, monkeypatch):
    monkeypatch.setattr(F.config, "AHREFS_FALLBACK_EXIT", "datacenter")
    F.script({None: [Resp(403, "denied")], DC: [Resp(403, "denied"), Resp()]})
    assert F.website_overview("tesla.com") == {"domainRating": 90}
    assert F.built == [None, DC, DC]
    monkeypatch.setattr(F.config, "AHREFS_FALLBACK_EXIT", None)      # the pre-2026-11-11 behaviour: every retry on AHREFS_EXIT
    monkeypatch.setattr(F, "_hold_until", 0.0)
    F._drop_session()
    del F.built[:]
    F.script({None: [Resp(403, "denied"), Resp(403, "denied"), Resp()]})
    assert F.website_overview("tesla.com") == {"domainRating": 90}
    assert F.built == [None, None, None]
