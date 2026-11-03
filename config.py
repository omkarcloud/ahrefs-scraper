"""Configuration for the Ahrefs Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT               port the API listens on (default 8000)

    CAPSOLVER_API_KEY  needed for the 12 endpoints that run on Ahrefs' free
                       SEO tools (Domain Rating, backlinks, traffic, broken
                       links, sitemap, keyword ideas, keyword difficulty,
                       SERP, rank check, AI visibility / AI Overviews / AI
                       Mode). Every one of those calls carries a Cloudflare
                       Turnstile token; CapSolver mints one in about 3
                       seconds, no browser needed (about $1.20 per 1,000
                       calls at CapSolver's normal price):
                       https://dashboard.capsolver.com/passport/register?inviteCode=lvdYBC4sYKRm
                       The website overview, competitors, top websites and
                       trending websites endpoints need no key at all.

    AHREFS_PROXY       proxy URL for every request, e.g. http://user:pass@host:port
                       (default: none — direct). Ahrefs served every endpoint
                       from home, cloud and proxy connections alike, so you
                       very likely don't need this.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request). A retry
# mints a fresh Turnstile token (they are single-use).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# --- captcha solving --------------------------------------------------------
CAPSOLVER_API_KEY = os.environ.get("CAPSOLVER_API_KEY", "").strip()
# Our CapSolver developer app id: CapSolver pays us a small commission on the
# captchas you solve, at no extra cost to you (you pay CapSolver's normal price).
CAPSOLVER_APP_ID = "DC601421-43D5-45E4-9FDB-B3BAF7A2C3FD"

# The Turnstile widget every Ahrefs free tool shows, and the page URL sent to
# CapSolver with it (any ahrefs.com page works).
AHREFS_TURNSTILE_SITEKEY = "0x4AAAAAAAAzi9ITzSN9xKMi"
AHREFS_CAPTCHA_PAGE = "https://ahrefs.com/backlink-checker"
AHREFS_SOLVE_TIMEOUT = 60          # seconds to wait for one solve (typically 3)

# --- proxy ------------------------------------------------------------------
AHREFS_PROXY = os.environ.get("AHREFS_PROXY") or None


def ahrefs_proxy():
    """The proxy for one session (None = direct)."""
    return os.environ.get("AHREFS_PROXY") or None
