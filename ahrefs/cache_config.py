"""Cache TTL per /ahrefs/* endpoint (cache.py, keyed on the validated
params). Every free-tool call costs one Turnstile solve (~3 s, a CapSolver
charge) so nothing is fetched twice within a day; Ahrefs' own figures are
monthly (traffic, ahrefstop) or refreshed every few days (SERPs).
"""
from datetime import timedelta

# DR / backlink counts move slowly; Ahrefs recrawls continuously but the
# free tool rounds them anyway.
AUTHORITY_CACHE = timedelta(hours=24)
# Overview + top-20 list for one (target, mode): same cadence.
BACKLINKS_CACHE = timedelta(hours=24)
# Traffic estimates are monthly series.
TRAFFIC_CACHE = timedelta(hours=24)
# Broken links change when either site changes; a day is fine.
BROKEN_LINKS_CACHE = timedelta(hours=24)
# The sitemap generator crawls the site live (up to 1000 URLs): the
# priciest call, cached longest a crawl stays honest.
SITEMAP_CACHE = timedelta(hours=12)
# ahrefstop pages are rebuilt monthly ("Updated monthly").
WEBSITE_CACHE = timedelta(hours=24)
COMPETITORS_CACHE = timedelta(hours=24)
TOP_LIST_CACHE = timedelta(hours=12)
# Keyword ideas: Ahrefs' per-keyword updatedAt stamps are days apart.
KEYWORD_IDEAS_CACHE = timedelta(hours=24)
# SERP overview + KD: the SERP's lastUpdate is refreshed every few days.
SERP_CACHE = timedelta(hours=12)
# Rank check: the same SERP plus the target's position.
RANK_CACHE = timedelta(hours=6)
# AI trackers: cycle counts ("new this cycle") move daily.
AI_CACHE = timedelta(hours=24)
