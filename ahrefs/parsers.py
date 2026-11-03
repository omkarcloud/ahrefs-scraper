"""Raw Ahrefs JSON / ahrefstop HTML -> clean dicts for every /ahrefs/*
endpoint. Pure functions, no I/O.

Two kinds of input:

  * the free-tool v4 payloads (fetch.rpc): camelCase JSON with OCaml-style
    variant encodings — `["Some", x]` / `"None"` options, `["Url", {...}]`
    and `["organic", {...}]` tagged tuples, model names as one-element
    lists (`{"model": ["Chatgpt"]}`). The parsers flatten those.
  * ahrefstop.com pages: server-rendered HTML whose figures are display-
    rounded ("3.5B", "$563.4M", "↑2", "−129.7M"); three inline JSON blobs
    (window.AhrefsTop.countriesData / trafficChartData / backlinksChartData)
    carry the exact monthly series.

Value conventions (shared with the other scraper packages):
  * keys snake_case; `link` not `url`; booleans read as questions
  * compact figures -> numbers ("3.5B" -> 3500000000, "7.5%" -> 7.5);
    rank arrows -> signed ints (↑2 -> 2, ↓433 -> -433); money as a numeric
    amount with a separate `currency` (Ahrefs reports USD)
  * dates ISO (YYYY-MM-DD / YYYY-MM for months); missing -> null

Fixtures captured 2026-11-03 (ahrefs/fixtures/): every RPC's payload for
omkar.cloud / "seo tools" / brand "ahrefs" (the sitemap generator's for
paulgraham.com, a capped 1,000-URL crawl; plus the empty / unknown
variants), the worldwide top list pages 1-2, the India and India+Shopping
lists, youtube.com's and bulbagarden.net's website pages, youtube.com's
competitors page and the ahrefstop 404 page.
"""
import json
import re

from bs4 import BeautifulSoup

from ahrefs import refs

CURRENCY = "USD"

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}
_COMPACT_RE = re.compile(r"^([+\-−]?)\$?\s*(\d+(?:[.,]\d+)?)\s*([kmbtKMBT]?)(%?)$")
_ARROW_RE = re.compile(r"^([↑↓])\s*(\d+)$")
_MONTH_YEAR_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b")
_BLOB_RE = re.compile(r"window\.AhrefsTop\.(\w+)\s*=\s*(\{.*?\});\s*(?:\n|</script>)", re.S)


# ---- value helpers -----------------------------------------------------------

def _text(node, sep=" "):
    return node.get_text(sep, strip=True) if node is not None else ""


def _clean(value):
    if value is None:
        return None
    value = " ".join(str(value).split())
    return value or None


def parse_compact(value):
    """"3.5B" -> 3500000000, "$563.4M" -> 563400000, "+1.7B" -> 1700000000,
    "−129.7M" -> -129700000, "7.5%" -> 7.5, "99" -> 99; anything else None."""
    text = _clean(value)
    if not text:
        return None
    match = _COMPACT_RE.match(text.replace(",", ""))
    if not match:
        return None
    sign, digits, suffix, percent = match.groups()
    number = float(digits) * _SUFFIX.get(suffix.lower(), 1)
    if sign in ("-", "−"):
        number = -number
    if percent or suffix == "" and "." in digits:
        return round(number, 2)
    return int(round(number))


def parse_arrow(value):
    """"↑2" -> 2 (moved up), "↓433" -> -433, "" / "–" -> None."""
    text = _clean(value)
    if not text:
        return None
    match = _ARROW_RE.match(text)
    if not match:
        return None
    n = int(match.group(2))
    return n if match.group(1) == "↑" else -n


def parse_month(value):
    """"October 2026" -> "2026-10"; a text containing it works too."""
    match = _MONTH_YEAR_RE.search(value or "")
    if not match:
        return None
    return f"{match.group(2)}-{_MONTHS[match.group(1).lower()]:02d}"


def _iso_date(value):
    """"2026-05-01T00:00:00Z" -> "2026-05-01"; "2026-05-01" unchanged."""
    text = _clean(value)
    return text[:10] if text and re.match(r"^\d{4}-\d{2}-\d{2}", text) else text


def _iso_month(value):
    text = _iso_date(value)
    return text[:7] if text else None


def _option(value):
    """`["Some", x]` -> x, `"None"` / None -> None, anything else as is."""
    if isinstance(value, list) and len(value) == 2 and value[0] == "Some":
        return value[1]
    if value == "None":
        return None
    return value


def _tagged(value):
    """`["Url", {...}]` / `["organic", {...}]` -> (tag, body)."""
    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
        return value[0], value[1]
    return None, value


def _model_name(value):
    """`["Chatgpt"]` / "Chatgpt" -> "chatgpt" (refs.AI_MODELS), unknown tokens snake_cased."""
    token = value[0] if isinstance(value, list) and value else value
    if not isinstance(token, str):
        return None
    return refs.AI_MODELS.get(token) or re.sub(r"(?<!^)(?=[A-Z])", "_", token).lower()


def _int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


def _link(value):
    """A protocol-less upstream path ("zapier.com/blog/x") -> https link."""
    text = _clean(value)
    if not text:
        return None
    return text if text.startswith(("http://", "https://")) else "https://" + text


# ---- free-tool payloads ----------------------------------------------------------

def _usd_from_cents(value):
    """The free tools report traffic value in US cents (tesla.com:
    costMontlyAvg 555450000 for ~10.7M visits = $5.55M, against ahrefstop's
    $4.6M for 8.6M visits) -> dollars, 2 decimals."""
    number = _float(value)
    return round(number / 100, 2) if number is not None else None


def parse_authority(data):
    """stGetFreeWebsiteOverview / the backlinks overview's `data` block."""
    data = _dict(data)
    return {
        "domain_rating": _float(data.get("domainRating")),
        "backlinks": _int(data.get("backlinks")),
        "referring_domains": _int(data.get("refdomains")),
        "dofollow_backlinks_percent": _float(data.get("dofollowBacklinks")),
        "dofollow_referring_domains_percent": _float(data.get("dofollowRefdomains")),
    }


def _redirects(value):
    return [{"link": _clean(hop.get("url")), "http_code": _int(hop.get("redirectCode"))}
            for hop in _list(value) if isinstance(hop, dict)]


def parse_backlink(item):
    item = _dict(item)
    return {
        "source_link": _clean(item.get("urlFrom")),
        "source_title": _clean(item.get("title")),
        "source_domain_rating": _float(item.get("domainRating")),
        "target_link": _clean(item.get("urlTo")),
        "anchor": _clean(item.get("anchor")),
        "text_before": _clean(item.get("textPre")),
        "text_after": _clean(item.get("textPost")),
        "redirect_chain": _redirects(item.get("redirectChain")),
        "is_in_raw_html": item.get("inRaw") if isinstance(item.get("inRaw"), bool) else None,
        "is_in_rendered_html": item.get("inRendered") if isinstance(item.get("inRendered"), bool) else None,
    }


def parse_backlinks_list(data):
    """stGetFreeBacklinksList -> up to 20 backlinks (one per linking domain)."""
    return [parse_backlink(b) for b in _list(_dict(data).get("backlinks"))]


def parse_traffic(data):
    """stGetFreeTrafficOverview."""
    data = _dict(data)
    traffic = _dict(data.get("traffic"))
    return {
        "monthly_organic_traffic": _int(traffic.get("trafficMonthlyAvg")),
        "monthly_traffic_value": _usd_from_cents(traffic.get("costMontlyAvg", traffic.get("costMonthlyAvg"))),
        "currency": CURRENCY,
        "traffic_history": [
            {"month": _iso_month(row.get("date")), "organic_traffic": _int(row.get("organic"))}
            for row in _list(data.get("traffic_history")) if isinstance(row, dict)],
        "top_pages": [
            {"link": _clean(row.get("url")), "traffic": _int(row.get("traffic")),
             "share_percent": _round(row.get("share"))}
            for row in _list(data.get("top_pages")) if isinstance(row, dict)],
        "top_countries": [
            {"country": (_clean(row.get("country")) or "").upper() or None,
             "share_percent": _round(row.get("share"))}
            for row in _list(data.get("top_countries")) if isinstance(row, dict)],
        "top_keywords": [
            {"keyword": _clean(row.get("keyword")), "position": _int(row.get("position")),
             "traffic": _int(row.get("traffic"))}
            for row in _list(data.get("top_keywords")) if isinstance(row, dict)],
    }


def _round(value, digits=2):
    number = _float(value)
    return round(number, digits) if number is not None else None


def _broken_link(item):
    row = parse_backlink(item)
    row.pop("is_in_raw_html", None)
    row.pop("is_in_rendered_html", None)
    row["http_code"] = _int(_dict(item).get("httpCode"))
    return row


def parse_broken_links(data):
    """stGetFreeBrokenLinksList: `inbound` / `outbound` are each wrapped in
    their own ["Ok", {...}] envelope."""
    data = _dict(data)
    inbound_tag, inbound = _tagged(data.get("inbound"))
    outbound_tag, outbound = _tagged(data.get("outbound"))
    inbound = _dict(inbound) if inbound_tag == "Ok" else {}
    outbound = _dict(outbound) if outbound_tag == "Ok" else {}
    # dofollowBacklinks / dofollowLinks are the tool's "Dofollow 50%" share,
    # like dofollowBacklinks on the backlink checker (24 = 24%).
    return {
        "inbound": {
            "total_backlinks": _int(inbound.get("totalBacklinks")),
            "dofollow_backlinks_percent": _float(inbound.get("dofollowBacklinks")),
            "broken_links": [_broken_link(b) for b in _list(inbound.get("inboundLinks"))],
        },
        "outbound": {
            "total_links": _int(outbound.get("totalLinks")),
            "dofollow_links_percent": _float(outbound.get("dofollowLinks")),
            "broken_links": [_broken_link(b) for b in _list(outbound.get("outboundLinks"))],
        },
    }


def parse_sitemap(data):
    data = _dict(data)
    return {
        "host": _clean(data.get("host")),
        "url_count": _int(data.get("urlCount")),
        "crawled_count": _int(data.get("crawledTotal")),
        "excluded_count": _int(data.get("excluded")),
        "is_capped": data.get("capped") if isinstance(data.get("capped"), bool) else None,
        "cap": _int(data.get("cap")),
        "entries": [{"link": _clean(e.get("url")), "last_modified": _iso_date(e.get("lastmod"))}
                    for e in _list(data.get("entries")) if isinstance(e, dict)],
    }


_VOLUME_WORDS = {"ten": 10, "hundred": 100, "thousand": 1000, "million": 1_000_000}


def _volume_floor(label):
    """"MoreThanHundredThousand" -> 100000, "MoreThanOneThousand" -> 1000,
    "MoreThanTen" -> 10; an unknown label -> None."""
    text = _clean(label) or ""
    if not text.startswith("MoreThan"):
        return None
    words = re.findall(r"[A-Z][a-z]+", text[len("MoreThan"):])
    number, unit = 1, None
    for word in words:
        low = word.lower()
        if low == "one":
            continue
        if low in ("ten", "hundred"):
            number *= _VOLUME_WORDS[low]
        elif low in ("thousand", "million"):
            unit = _VOLUME_WORDS[low]
        else:
            return None
    return number * (unit or 1)


def _keyword_idea(item):
    item = _dict(item)
    difficulty = _clean(item.get("difficultyLabel"))
    return {
        "keyword": _clean(item.get("keyword")),
        "country": (_clean(item.get("country")) or "").upper() or None,
        "difficulty": difficulty.lower() if difficulty and difficulty != "Unknown" else None,
        "volume_at_least": _volume_floor(item.get("volumeLabel")),
        "updated_at": _iso_date(item.get("updatedAt")),
    }


def parse_keyword_ideas(data):
    data = _dict(data)
    ideas = _dict(data.get("allIdeas"))
    questions = _dict(data.get("questionIdeas"))
    return {
        "total_ideas": _int(ideas.get("total")),
        "ideas": [_keyword_idea(i) for i in _list(ideas.get("results"))],
        "total_questions": _int(questions.get("total")) if questions else None,
        "questions": [_keyword_idea(i) for i in _list(questions.get("results"))] if questions else [],
    }


def _serp_metrics(metrics):
    metrics = _dict(metrics)
    return {
        "ahrefs_rank": _int(metrics.get("rank")),
        "domain_rating": _float(metrics.get("domainRating")),
        "url_rating": _float(metrics.get("urlRating")),
        "backlinks": _int(metrics.get("refpages")),
        "referring_domains": _int(metrics.get("domains")),
        "traffic": _int(metrics.get("traffic")),
        "traffic_value": _usd_from_cents(metrics.get("cost")),
        "keywords": _int(metrics.get("keywords")),
        "top_keyword": _clean(metrics.get("topKeyword")),
        "top_keyword_volume": _int(metrics.get("topVolume")),
        "word_count": _int(metrics.get("nrWords")),
        "http_code": _int(metrics.get("httpCode")),
    }


def _serp_link(link):
    """The organic result's `link` option -> (title, link, display_link, metrics, is_target)."""
    link = _dict(_option(link))
    _, url = _tagged(link.get("url"))
    url = _dict(url)
    return {
        "title": _clean(link.get("title")),
        "link": _clean(url.get("url")),
        "display_link": _clean(link.get("url_visual")),
        "is_target": link.get("isTarget") if isinstance(link.get("isTarget"), bool) else None,
        "metrics": _serp_metrics(link.get("metrics")) if link.get("metrics") is not None else None,
    }


def parse_serp_result(item):
    """One `serp.results` row: {content: [type, body], pos, posWithMetrics}."""
    item = _dict(item)
    kind, body = _tagged(item.get("content"))
    out = {"position": _int(item.get("pos")), "type": kind or None,
           "organic_position": _int(item.get("posWithMetrics"))}
    if kind == "organic":
        body = _dict(body)
        out.update(_serp_link(body.get("link")))
        out["sitelinks"] = [_serp_link(s) for s in _list(body.get("siteLinks")) if _option(s) is not None]
    elif kind == "ai_overview":
        body = _dict(body)
        out.update({"title": _clean(body.get("title")), "description": _clean(body.get("description"))})
    elif kind == "questions":
        out["questions"] = [
            {"question": _clean(_dict(_option(q)).get("title")), "link": _clean(_option(_dict(_option(q)).get("link")))}
            for q in _list(body)]
    elif isinstance(body, dict):
        # a SERP feature the fixtures never showed (video, snippet, ...):
        # keep its printable scalars rather than dropping it
        out.update({re.sub(r"(?<!^)(?=[A-Z])", "_", k).lower(): v for k, v in body.items()
                    if isinstance(v, (str, int, float, bool)) or v is None})
    return out


def parse_serp(data):
    """The SERP overview shared by keywords/serp, /difficulty and /rank."""
    data = _dict(data)
    serp = _dict(data.get("serp"))
    results = [parse_serp_result(r) for r in _list(serp.get("results"))]
    return {
        "last_updated": _iso_date(data.get("lastUpdate")),
        "difficulty": _int(data.get("difficulty")),
        "referring_domains_needed": _int(data.get("shortage")),
        "results": results,
    }


def parse_rank(data):
    """stGetFreeSerpOverviewForKeywordRankChecker: the target's best position
    (null when it is not in the top 100) plus the SERP."""
    data = _dict(data)
    top = _option(data.get("topPosition"))
    top = top if isinstance(top, dict) else None
    out = parse_serp(data)
    out.pop("difficulty", None)
    out.pop("referring_domains_needed", None)
    out["position"] = _int(_dict(top).get("pos")) if top else None
    out["result"] = parse_serp_result(top) if top else None
    return out


def _cited(items, key):
    out = []
    for row in _list(items):
        row = _dict(row)
        entry = {key: _clean(row.get("domain" if key == "domain" else "url")), "mentions": _int(row.get("mentions"))}
        if key == "link":
            entry["link"] = _link(row.get("url"))
        out.append(entry)
    return out


def _topics(items):
    return [{"topic": _clean(t.get("topic")), "ai_responses": _int(t.get("aiResponses"))}
            for t in _list(items) if isinstance(t, dict)]


def _timeline(items):
    return [{"month": _iso_month(t.get("date")), "citations": _int(t.get("citations"))}
            for t in _list(items) if isinstance(t, dict)]


def parse_ai_visibility(data):
    data = _dict(data)
    return {
        "total_citations": _int(data.get("totalAiCitations")),
        "citations_by_model": [
            {"model": _model_name(row.get("model")), "citations": _int(row.get("count"))}
            for row in _list(data.get("citationsByModel")) if isinstance(row, dict)],
        "monthly_citations_by_model": [
            {"model": _model_name(row.get("model")), "timeline": _timeline(row.get("timeline"))}
            for row in _list(data.get("monthlyCitationsByModel")) if isinstance(row, dict)],
        "top_cited_domains": _cited(data.get("topCitedDomains"), "domain"),
        "top_cited_pages": _cited(data.get("topCitedPages"), "link"),
        "top_topics": _topics(data.get("topTopics")),
    }


def parse_ai_tracker(data, total_key):
    """stGetFreeAIOverviewsTrackerOverview / stGetFreeAIModeTrackerOverview
    (same shape; the total's key names the product)."""
    data = _dict(data)
    return {
        "total_mentions": _int(data.get(total_key)),
        "new_mentions_this_cycle": _int(data.get("newMentionsThisCycle")),
        "total_topics": _int(data.get("totalTopics")),
        "total_domains": _int(data.get("totalDomains")),
        "top_topics": _topics(data.get("topTopics")),
        "top_cited_domains": _cited(data.get("topCitedDomains"), "domain"),
        "top_cited_pages": _cited(data.get("topCitedPages"), "link"),
        "ai_overviews_timeline": _timeline(data.get("aiOverviewsTimeline")),
        "ai_mode_timeline": _timeline(data.get("aiModeTimeline")),
    }


# ---- ahrefstop.com -------------------------------------------------------------------

def _soup(html):
    return BeautifulSoup(html, "lxml")


def _blobs(html):
    """window.AhrefsTop.<name> = {...}; -> {name: parsed JSON} (the chart
    blobs use unquoted keys, so they are repaired before json.loads)."""
    out = {}
    for name, body in _BLOB_RE.findall(html or ""):
        fixed = re.sub(r"([{,]\s*)([A-Za-z_]\w*)\s*:", r'\1"\2":', body)
        try:
            out[name] = json.loads(fixed)
        except ValueError:
            continue
    return out


_FLAG_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]")


def _label_text(node):
    """A label's own words: flag emoji and the (i) tooltip copy dropped."""
    if node is None:
        return ""
    parts = []
    for string in node.find_all(string=True):
        if any("tooltip" in " ".join(p.get("class") or []) for p in string.parents if p is not node and p.name):
            continue
        parts.append(str(string))
    return _FLAG_RE.sub("", " ".join(" ".join(parts).split())).strip()


def _number_component(node):
    """<div class="number-component"> -> (label, value text, delta text)."""
    label = _label_text(node.select_one(".number-label-top, .number-label-bottom"))
    value = _text(node.select_one(".number-value"))
    delta = _text(node.select_one(".number-delta"))
    return label, value, delta


def _rank_block(container):
    """The "Rank by traffic" metrics (hero / competitor card): worldwide,
    country and category ranks with their month-on-month moves."""
    out = {"worldwide": None, "country": None, "category": None}
    if container is None:
        return out
    for anchor in container.select("a"):
        href = anchor.get("href") or ""
        label, value, delta = _number_component(anchor)
        entry = {"rank": parse_compact(value), "rank_change": parse_arrow(delta)}
        match = re.match(r"^/websites(?:/([^#]+))?#", href)
        slug = (match.group(1) if match else "") or ""
        if not slug:
            out["worldwide"] = entry
        elif slug in refs.COUNTRY_SLUGS:
            out["country"] = {"country": refs.country_code_for_slug(slug), "name": label or None, **entry}
        else:
            out["category"] = {"category": slug, "name": label or None, **entry}
    return out


def _grid_rows(grid, width):
    """A .domain-grid's data cells (headers / CTA skipped) in rows of `width`."""
    cells = [c for c in grid.select(":scope > .grid-cell") if "grid-header" not in (c.get("class") or [])]
    return [cells[i:i + width] for i in range(0, len(cells) - len(cells) % width, width)]


def _value_and_delta(cell):
    """A grid value cell: "99.6M<span class=grid-stacked-delta>-2.1M</span>"."""
    delta_node = cell.select_one(".grid-stacked-delta, .delta-positive, .delta-negative")
    delta = _text(delta_node) if delta_node is not None else ""
    value = _text(cell).replace(delta, "").strip() if delta else _text(cell)
    return parse_compact(value), parse_compact(delta) if delta else None


def _rank_cell(cell):
    """"1 ↑2" -> (1, 2)."""
    arrow = cell.select_one("span")
    change = parse_arrow(_text(arrow)) if arrow is not None else None
    value = _text(cell).replace(_text(arrow), "").strip() if arrow is not None else _text(cell)
    return parse_compact(value), change


def _domain_cell(cell):
    anchor = cell.select_one("a[href^='/websites/']")
    if anchor is None:
        return None, None
    slug = (anchor.get("href") or "").split("/websites/", 1)[-1].split("#")[0].strip("/")
    return _text(anchor) or slug, refs.website_link(slug) if slug else None


def _period(node):
    return parse_month(_text(node)) if node is not None else None


def parse_website(html, domain=None):
    """One ahrefstop.com/websites/<domain> page -> the full record."""
    soup = _soup(html)
    blobs = _blobs(html)
    title = _text(soup.select_one("h1.domain-hero-title")) or domain
    sections = {}
    for section in soup.select("section.domain-section"):
        heading = _text(section.select_one("h2.section-heading")).lower()
        for key in ("search traffic", "traffic by location", "top keywords", "top competing",
                    "similarly ranked", "backlink profile"):
            if heading.startswith(key):
                sections[key] = section

    # hero
    ranks = _rank_block(soup.select_one(".domain-hero .domain-rank-metrics"))
    description = _clean(_text(soup.select_one("#domain-description")))

    # search traffic
    traffic_section = sections.get("search traffic")
    traffic = {"traffic": None, "traffic_change": None, "traffic_value": None,
               "traffic_value_change": None, "keywords": None}
    if traffic_section is not None:
        for comp in traffic_section.select(".section-numbers-row .number-component"):
            label, value, delta = _number_component(comp)
            low = label.lower()
            if low == "traffic":
                traffic["traffic"], traffic["traffic_change"] = parse_compact(value), parse_compact(delta)
            elif low == "traffic value":
                traffic["traffic_value"], traffic["traffic_value_change"] = parse_compact(value), parse_compact(delta)
            elif low == "keywords":
                traffic["keywords"] = parse_compact(value)
    period = _period(traffic_section.select_one(".section-date")) if traffic_section is not None else None

    chart = _dict(blobs.get("trafficChartData"))
    labels, traffic_series, value_series = _list(chart.get("labels")), _list(chart.get("trafficData")), _list(chart.get("valueData"))
    history = []
    for i, label in enumerate(labels):
        history.append({"month": _iso_month(label),
                        "organic_traffic": _int(traffic_series[i]) if i < len(traffic_series) else None,
                        "traffic_value": _int(value_series[i]) if i < len(value_series) else None})

    # traffic by location (exact figures from the blob; the grid only rounds them)
    countries = []
    for code, row in _dict(blobs.get("countriesData")).items():
        row = _dict(row)
        current, previous = _int(row.get("traffic")), _int(row.get("trafficPrev"))
        share = _float(row.get("trafficShare"))
        countries.append({"country": str(code).upper(), "traffic": current, "previous_traffic": previous,
                          "traffic_change": (current - previous) if current is not None and previous is not None else None,
                          "share_percent": round(share * 100, 1) if share is not None else None})
    countries.sort(key=lambda c: -(c["traffic"] or 0))

    # top keywords
    keywords, keywords_country = [], None
    section = sections.get("top keywords")
    if section is not None:
        keywords_country = _clean(re.sub(r"[\U0001F1E6-\U0001F1FF]", "", _text(section.select_one(".section-country"))))
        grid = section.select_one(".domain-grid--keywords")
        for row in (_grid_rows(grid, 7) if grid is not None else []):
            volume, volume_change = _value_and_delta(row[1])
            kw_traffic, traffic_change = _value_and_delta(row[3])
            position, position_change = _value_and_delta(row[5])
            position_change = parse_arrow(_text(row[6])) if _text(row[6]) else None
            keywords.append({"keyword": _text(row[0]) or None, "volume": volume, "volume_change": volume_change,
                             "traffic": kw_traffic, "traffic_change": traffic_change,
                             "position": position, "position_change": position_change})

    # competitors
    competitors, competitors_country = [], None
    section = sections.get("top competing")
    if section is not None:
        competitors_country = _clean(re.sub(r"[\U0001F1E6-\U0001F1FF]", "", _text(section.select_one(".section-country"))))
        grid = section.select_one(".domain-grid--competitors")
        for row in (_grid_rows(grid, 6) if grid is not None else []):
            name, link = _domain_cell(row[1])
            if not name:
                continue
            c_traffic, c_change = _value_and_delta(row[2])
            competitors.append({"domain": name, "link": link, "traffic": c_traffic, "traffic_change": c_change,
                                "pages": parse_compact(_text(row[4]))})

    # similarly ranked
    similar = []
    section = sections.get("similarly ranked")
    if section is not None:
        grid = section.select_one(".domain-grid")
        for row in (_grid_rows(grid, 5) if grid is not None else []):
            name, link = _domain_cell(row[1])
            if not name:
                continue
            s_traffic, s_change = _value_and_delta(row[2])
            rank, rank_change = _rank_cell(row[4])
            similar.append({"domain": name, "link": link, "is_target": name == title,
                            "traffic": s_traffic, "traffic_change": s_change,
                            "rank": rank, "rank_change": rank_change})

    # backlink profile
    backlinks = {"domain_rating": None, "linking_websites": None, "linking_websites_change": None}
    section = sections.get("backlink profile")
    backlinks_period = None
    if section is not None:
        backlinks_period = _period(section.select_one(".section-date"))
        for comp in section.select(".number-component"):
            label, value, delta = _number_component(comp)
            low = label.lower()
            if low == "domain rating":
                backlinks["domain_rating"] = parse_compact(value)
            elif low == "linking websites":
                backlinks["linking_websites"], backlinks["linking_websites_change"] = parse_compact(value), parse_compact(delta)
    refdomains = _dict(_dict(blobs.get("backlinksChartData")).get("refdomainsHistory"))
    xs, ys = _list(refdomains.get("x")), _list(refdomains.get("y"))
    refdomains_history = [{"month": _iso_month(x), "linking_websites": _int(ys[i]) if i < len(ys) else None}
                          for i, x in enumerate(xs)]

    updated = None
    for script in soup.select("script[type='application/ld+json']"):
        try:
            updated = _iso_date(_dict(json.loads(script.string or "")).get("dateModified"))
        except ValueError:
            continue
        if updated:
            break

    slug = title or domain
    return {
        "domain": slug,
        "name": _clean(_text(soup.select_one(".domain-hero-subtitle"))),
        "link": refs.website_link(slug) if slug else None,
        "description": description,
        "period": period,
        "ranks": ranks,
        "search_traffic": {**traffic, "currency": CURRENCY},
        "traffic_history": history,
        "traffic_by_country": countries,
        "top_keywords": {"country": keywords_country, "keywords": keywords},
        "competitors": {"country": competitors_country, "websites": competitors},
        "similarly_ranked": similar,
        "backlink_profile": {**backlinks, "period": backlinks_period, "linking_websites_history": refdomains_history},
        "updated_at": updated,
    }


def parse_competitors(html, domain=None):
    """ahrefstop.com/websites/<domain>/competitors -> the competitor cards."""
    soup = _soup(html)
    country = _clean(_FLAG_RE.sub("", _text(soup.select_one(".competitor-hero-country, .section-country"))))
    cards = []
    main_first = False
    for card in soup.select(".competitor-card"):
        name, link = _domain_cell(card.select_one(".competitor-card-title"))
        if not name:
            continue
        if not cards:
            main_first = "competitor-card--main" in (card.get("class") or [])
        metrics = {"traffic": None, "traffic_change": None, "traffic_value": None, "traffic_value_change": None,
                   "pages": None, "domain_rating": None}
        for comp in card.select(".competitor-card-metrics .number-component"):
            label, value, delta = _number_component(comp)
            low = label.lower()
            if low == "traffic":
                metrics["traffic"], metrics["traffic_change"] = parse_compact(value), parse_compact(delta)
            elif low == "traffic value":
                metrics["traffic_value"], metrics["traffic_value_change"] = parse_compact(value), parse_compact(delta)
            elif low == "pages":
                metrics["pages"] = parse_compact(value)
            elif low == "domain rating":
                metrics["domain_rating"] = parse_compact(value)
        cards.append({
            "domain": name, "link": link,
            "description": _clean(_text(card.select_one(".competitor-card-description"))),
            "ranks": _rank_block(card.select_one(".domain-rank-metrics")),
            **metrics, "currency": CURRENCY,
        })
    # the first card is the target itself on the pages captured 2026-11-03
    target = cards[0]["domain"] if cards else domain
    others = cards[1:] if cards and (main_first or cards[0]["domain"] == domain) else cards
    return {"domain": domain or target, "link": refs.competitors_link(domain or target) if (domain or target) else None,
            "country": country, "competitors": others}


def _list_row(row):
    """One <tr> of a ranking / trending table."""
    cells = row.find_all("td")
    if len(cells) < 4:
        return None
    rank = parse_compact(_text(cells[0]))
    if rank is None:
        return None
    domain_anchor = row.select_one("a.website-domain-link")
    category_anchor = row.select_one("a.website-category-link")
    slug = (domain_anchor.get("href") or "").split("/websites/", 1)[-1] if domain_anchor is not None else ""
    traffic, change = None, None
    seen_domain = False
    for cell in cells:
        if domain_anchor is not None and cell.find("a", class_="website-domain-link"):
            seen_domain = True
            continue
        if not seen_domain or (category_anchor is not None and cell.find("a", class_="website-category-link")):
            continue
        span = cell.find("span")
        value = parse_compact(_text(span) if span is not None else _text(cell))
        if value is None:
            continue
        if traffic is None:
            traffic = value
            hidden = cell.find("div")
            change = parse_compact(_text(hidden)) if hidden is not None else None
        elif change is None:
            change = value
            break
        else:
            break
    return {
        "rank": rank,
        "rank_change": parse_arrow(_text(cells[1])),
        "domain": _text(domain_anchor) or slug or None,
        "link": refs.website_link(slug) if slug else None,
        "category": _text(category_anchor) or None,
        # a country list links its categories as /websites/<country>/<category>
        "category_slug": ((category_anchor.get("href") or "").rstrip("/").rsplit("/", 1)[-1] or None) if category_anchor is not None else None,
        "traffic": traffic,
        "traffic_change": change,
    }


def _table_rows(table):
    rows = []
    for tr in table.find_all("tr"):
        row = _list_row(tr)
        if row:
            rows.append(row)
    return rows


def parse_top_list(html):
    """A ranking page -> {title, period, websites, trending_up, trending_down}."""
    soup = _soup(html)
    main = soup.select_one("table#websites-table")
    tables = [t for t in soup.find_all("table") if t is not main]
    up, down = [], []
    for table in tables:
        heading = ""
        prev = table.find_previous(["h3", "h2"])
        if prev is not None:
            heading = _text(prev).lower()
        rows = _table_rows(table)
        if "down" in heading:
            down = rows
        elif "up" in heading:
            up = rows
    title = _text(soup.select_one("h1"))
    intro = soup.select_one("h1")
    period = None
    if intro is not None:
        period = parse_month(_text(intro.parent))
    if period is None:
        period = parse_month(_text(soup.select_one("main")) or _text(soup))
    return {
        "title": _clean(title),
        "period": period,
        "websites": _table_rows(main) if main is not None else [],
        "trending_up": up,
        "trending_down": down,
    }
