"""The /ahrefs/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs).

Every free-tool call costs one Turnstile solve, so each endpoint caches its
own response through cache.cached_call keyed on the validated params, and
the three keyword SERP views share what they can: keywords/serp and
keywords/difficulty slice ONE cached stGetFreeSerpOverviewForKeywordDifficultyChecker
payload (it carries the SERP and the KD score), so hitting both on a
keyword costs one solve; keywords/rank needs its own call (the target is
part of the request). domains/backlinks runs the overview + list pair
behind one solve (the list call takes the overview's signed input).
"""
from cache import cached_call
from ahrefs import cache_config as ttl
from ahrefs import fetch, parsers, refs
from ahrefs.fetch import AhrefsNotFound

TOP_LIST_PAGE_SIZE = 100
TOP_LIST_TOTAL = 1000          # the worldwide list: 10 pages of 100


# ---- domains/* : the free tools ---------------------------------------------

def _authority(target):
    return {"target": target, "link": refs.tool_link("website-authority-checker", target),
            **parsers.parse_authority(fetch.website_overview(target))}


def domain_authority(**data):
    return cached_call("ahrefs.authority", data, _authority, ttl.AUTHORITY_CACHE)


def _backlinks(target, mode):
    overview = fetch.backlinks_overview(target, mode) or {}
    signed = overview.get("signedInput") if isinstance(overview, dict) else None
    listed = fetch.backlinks_list(signed) if signed else None
    backlinks = parsers.parse_backlinks_list(listed)
    return {
        "target": target, "mode": mode,
        "link": refs.tool_link("backlink-checker", target, mode),
        **parsers.parse_authority(overview.get("data") if isinstance(overview, dict) else None),
        "top_backlinks_count": len(backlinks),
        "top_backlinks": backlinks,
    }


def domain_backlinks(**data):
    return cached_call("ahrefs.backlinks", data, _backlinks, ttl.BACKLINKS_CACHE)


def _traffic(target, mode, country):
    payload = fetch.traffic_overview(target, mode, country)
    return {"target": target, "mode": mode, "country": country.upper() if country else None,
            "link": refs.tool_link("traffic-checker", target, mode),
            **parsers.parse_traffic(payload)}


def domain_traffic(**data):
    return cached_call("ahrefs.traffic", data, _traffic, ttl.TRAFFIC_CACHE)


def _broken_links(target, mode):
    return {"target": target, "mode": mode, "link": refs.tool_link("broken-link-checker", target, mode),
            **parsers.parse_broken_links(fetch.broken_links(target, mode))}


def domain_broken_links(**data):
    return cached_call("ahrefs.broken_links", data, _broken_links, ttl.BROKEN_LINKS_CACHE)


def _sitemap(target):
    return {"target": target, "link": refs.tool_link("sitemap-generator", target),
            **parsers.parse_sitemap(fetch.sitemap(target))}


def domain_sitemap(**data):
    return cached_call("ahrefs.sitemap", data, _sitemap, ttl.SITEMAP_CACHE)


# ---- domains/overview, domains/competitors : ahrefstop.com ------------------

def _website_candidates(target):
    """ahrefstop keys most sites by the bare domain but some by their www
    host (www.nhs.uk), so an unknown host is retried the other way once."""
    host = refs.target_host(target)
    other = host[4:] if host.startswith("www.") else "www." + host
    return [host, other]


def _fetch_website_page(target, fetcher, label):
    last = None
    for domain in _website_candidates(target):
        try:
            return domain, fetcher(domain)
        except AhrefsNotFound as e:
            last = e
    raise AhrefsNotFound(f"ahrefs.com/websites has no page for {refs.target_host(target)} "
                         f"({label} covers the ~200,000 most visited websites)")


def _overview(target):
    domain, html = _fetch_website_page(target, fetch.website_page, "the website overview")
    return parsers.parse_website(html, domain)


def domain_overview(**data):
    return cached_call("ahrefs.overview", data, _overview, ttl.WEBSITE_CACHE)


def _competitors(target):
    domain, html = _fetch_website_page(target, fetch.competitors_page, "the competitors list")
    record = parsers.parse_competitors(html, domain)
    record["competitors_count"] = len(record["competitors"])
    return record


def domain_competitors(**data):
    return cached_call("ahrefs.competitors", data, _competitors, ttl.COMPETITORS_CACHE)


# ---- websites/top, websites/trending ----------------------------------------

def _list_page(country, category, page):
    """One ahrefstop ranking page (parsed, cached); None past the end."""
    path = refs.top_list_path(country, category, page)
    if (country or category) and page > 1:
        return None    # country / category lists have one page
    try:
        return parsers.parse_top_list(fetch.top_list_page(path))
    except AhrefsNotFound:
        if page > 1:
            return None
        raise


def _list_meta(country, category):
    return {
        "country": refs.country_code_for_slug(country) if country else None,
        "country_slug": country,
        "category": category,
        "link": refs.TOP_SITE + refs.top_list_path(country, category),
    }


def _top(country, category, page):
    parsed = _list_page(country, category, page)
    rows = parsed["websites"] if parsed else []
    worldwide = not country and not category
    if worldwide:
        total_pages, total_count, has_next = TOP_LIST_TOTAL // TOP_LIST_PAGE_SIZE, TOP_LIST_TOTAL, bool(rows) and page < TOP_LIST_TOTAL // TOP_LIST_PAGE_SIZE
    else:
        total_pages, total_count, has_next = 1, (len(rows) if page == 1 else None), False
    return {
        **_list_meta(country, category),
        "title": parsed["title"] if parsed else None,
        "period": parsed["period"] if parsed else None,
        "websites": rows,
        "pagination": {
            "page": page,
            "items_per_page": TOP_LIST_PAGE_SIZE,
            "has_next": has_next,
            "total_pages": total_pages,
            "total_count": total_count,
        },
    }


def websites_top(**data):
    return cached_call("ahrefs.top_websites", data, _top, ttl.TOP_LIST_CACHE)


def _trending(country, category, direction):
    parsed = _list_page(country, category, 1) or {}
    out = {**_list_meta(country, category), "title": parsed.get("title"), "period": parsed.get("period")}
    if direction in (None, "up"):
        out["trending_up"] = parsed.get("trending_up") or []
    if direction in (None, "down"):
        out["trending_down"] = parsed.get("trending_down") or []
    return out


def websites_trending(**data):
    return cached_call("ahrefs.trending_websites", data, _trending, ttl.TOP_LIST_CACHE)


# ---- keywords/* --------------------------------------------------------------

def _ideas(keyword, country, search_engine, questions):
    engine_public = next((k for k, v in refs.SEARCH_ENGINES.items() if v == search_engine), search_engine)
    payload = fetch.keyword_ideas(keyword, country, search_engine, questions)
    return {"keyword": keyword, "country": country.upper(), "search_engine": engine_public,
            "link": refs.tool_link("keyword-generator", keyword, country=country),
            **parsers.parse_keyword_ideas(payload)}


def keyword_ideas(**data):
    return cached_call("ahrefs.keyword_ideas", data, _ideas, ttl.KEYWORD_IDEAS_CACHE)


def _serp_record(keyword, country):
    payload = fetch.keyword_difficulty(keyword, country)
    if payload is None:
        raise AhrefsNotFound(f'Ahrefs has no SERP data for "{keyword}" in {country.upper()}')
    return parsers.parse_serp(payload)


def _serp(keyword, country):
    """The shared cached SERP + KD record for one (keyword, country)."""
    return cached_call("ahrefs.serp_record", {"keyword": keyword, "country": country}, _serp_record, ttl.SERP_CACHE)


def keyword_serp(keyword, country):
    record = _serp(keyword, country)
    return {"keyword": keyword, "country": country.upper(),
            "link": refs.tool_link("serp-checker", keyword, country=country),
            "last_updated": record["last_updated"],
            "results_count": len(record["results"]), "results": record["results"]}


def keyword_difficulty(keyword, country):
    record = _serp(keyword, country)
    return {"keyword": keyword, "country": country.upper(),
            "link": refs.tool_link("keyword-difficulty", keyword, country=country),
            "difficulty": record["difficulty"],
            "referring_domains_needed": record["referring_domains_needed"],
            "last_updated": record["last_updated"],
            "results": record["results"]}


def _rank(keyword, country, target):
    payload = fetch.keyword_rank(keyword, country, target)
    if payload is None:
        raise AhrefsNotFound(f'Ahrefs has no SERP data for "{keyword}" in {country.upper()}')
    parsed = parsers.parse_rank(payload)
    return {"keyword": keyword, "country": country.upper(), "target": target,
            "link": refs.tool_link("keyword-rank-checker", target, keyword=keyword, country=country),
            "position": parsed["position"], "is_ranking": parsed["position"] is not None,
            "result": parsed["result"], "last_updated": parsed["last_updated"],
            "results": parsed["results"]}


def keyword_rank(**data):
    return cached_call("ahrefs.keyword_rank", data, _rank, ttl.RANK_CACHE)


# ---- brands/* ----------------------------------------------------------------

def _ai_visibility(brand):
    return {"brand": brand, "link": refs.tool_link("ai-visibility-checker", brand),
            **parsers.parse_ai_visibility(fetch.ai_visibility(brand))}


def brand_ai_visibility(**data):
    return cached_call("ahrefs.ai_visibility", data, _ai_visibility, ttl.AI_CACHE)


def _ai_overviews(brand):
    return {"brand": brand, "link": refs.tool_link("ai-overviews-tracker", brand),
            **parsers.parse_ai_tracker(fetch.ai_overviews(brand), "totalAiOverviewsMentions")}


def brand_ai_overviews(**data):
    return cached_call("ahrefs.ai_overviews", data, _ai_overviews, ttl.AI_CACHE)


def _ai_mode(brand):
    return {"brand": brand, "link": refs.tool_link("ai-mode-tracker", brand),
            **parsers.parse_ai_tracker(fetch.ai_mode(brand), "totalAiModeMentions")}


def brand_ai_mode(**data):
    return cached_call("ahrefs.ai_mode", data, _ai_mode, ttl.AI_CACHE)
