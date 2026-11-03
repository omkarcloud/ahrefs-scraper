"""Offline tests for the Ahrefs parsers, reference resolvers and value
helpers.

    python -m pytest ahrefs/test_parsers.py -q

Fixtures are real payloads / pages captured 2026-11-03 (ahrefs/fixtures/):
every free-tool RPC for omkar.cloud (the sitemap for paulgraham.com, a
capped 1,000-URL crawl), "seo tools" (us) and brand "ahrefs",
the empty / unknown variants, the ahrefstop worldwide pages 1-2, the India
and India+Shopping lists, two website pages, a competitors page and the
ahrefstop 404 page. No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ahrefs import parsers as P, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


def payload(name):
    """The `Ok` body of a captured RPC envelope."""
    envelope = fixture(name)
    assert envelope[0] == "Ok"
    return envelope[1]


# ---- refs -------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("omkar.cloud", "omkar.cloud"),
    ("OMKAR.cloud/", "omkar.cloud"),
    ("https://www.omkar.cloud/botasaurus/", "www.omkar.cloud/botasaurus"),
    ("www.omkar.cloud/botasaurus?x=1", "www.omkar.cloud/botasaurus?x=1"),
    ("https://ahrefs.com/websites/youtube.com", "youtube.com"),
    ("https://ahrefstop.com/websites/www.nhs.uk/competitors", "www.nhs.uk"),
    ("https://ahrefs.com/backlink-checker/?input=youtube.com&mode=subdomains", "youtube.com"),
    ("https://ahrefs.com/traffic-checker?input=https%3A%2F%2Fmoz.com%2Fblog", "moz.com/blog"),
    ("//example.org", "example.org"),
    ("HTTPS://Example.com/Path/", "example.com/Path"),
    ("https://ahrefs.com/", "ahrefs.com"),
    ("ahrefs.com/blog/seo-tools/", "ahrefs.com/blog/seo-tools"),
    ("https://ahrefstop.com/websites/india", "ahrefstop.com/websites/india"),
])
def test_resolve_target(value, expected):
    assert refs.resolve_target(value) == expected


@pytest.mark.parametrize("value", [
    "", "   ", "not a domain", "localhost", "no spaces here.com", "http://",
])
def test_resolve_target_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_target(value)


def test_target_host():
    assert refs.target_host("www.omkar.cloud/botasaurus?x=1") == "www.omkar.cloud"
    assert refs.target_host("omkar.cloud") == "omkar.cloud"


@pytest.mark.parametrize("value,expected", [
    ("in", "india"), ("IN", "india"), ("india", "india"), ("India", "india"),
    ("gb", "united-kingdom"), ("uk", "united-kingdom"), ("United Kingdom", "united-kingdom"),
    ("us", "united-states"), ("kr", "korea"), ("South Korea", "korea"), ("Russia", "russian-federation"),
])
def test_resolve_country_slug(value, expected):
    assert refs.resolve_country_slug(value) == expected


@pytest.mark.parametrize("value", ["", "zz", "atlantis", "shopping"])
def test_resolve_country_slug_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_country_slug(value)


def test_country_tables_are_consistent():
    assert len(refs.COUNTRY_SLUGS) == 183
    assert len(set(refs.COUNTRY_SLUGS.values())) == 183
    assert refs.country_code_for_slug("india") == "IN"
    assert len(refs.CATEGORIES) == 25
    assert not set(refs.CATEGORIES) & set(refs.COUNTRY_SLUGS)


def test_top_list_path():
    assert refs.top_list_path() == "/websites"
    assert refs.top_list_path(page=3) == "/websites/3"
    assert refs.top_list_path("india") == "/websites/india"
    assert refs.top_list_path("india", "shopping") == "/websites/india/shopping"
    assert refs.top_list_path(None, "shopping") == "/websites/shopping"


# ---- value helpers -------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("3.5B", 3500000000), ("121M", 121000000), ("$563.4M", 563400000), ("+1.7B", 1700000000),
    ("-15.2M", -15200000), ("−129.7M", -129700000), ("+$335.4M", 335400000), ("99", 99),
    ("7.5%", 7.5), ("12.7M", 12700000), ("9K", 9000), ("", None), (None, None), ("Watch", None),
])
def test_parse_compact(value, expected):
    assert P.parse_compact(value) == expected


@pytest.mark.parametrize("value,expected", [("↑2", 2), ("↓433", -433), ("", None), ("+2", None)])
def test_parse_arrow(value, expected):
    assert P.parse_arrow(value) == expected


def test_parse_month():
    assert P.parse_month("October 2026") == "2026-10"
    assert P.parse_month("Websites that changed positions in October 2026.") == "2026-10"
    assert P.parse_month("no month here") is None


# ---- free-tool payloads ------------------------------------------------------------------

def test_parse_authority():
    assert P.parse_authority(payload("website_overview.json")) == {
        "domain_rating": 37.0, "backlinks": 2239, "referring_domains": 746,
        "dofollow_backlinks_percent": 24.0, "dofollow_referring_domains_percent": 19.0}
    assert P.parse_authority(None) == {
        "domain_rating": None, "backlinks": None, "referring_domains": None,
        "dofollow_backlinks_percent": None, "dofollow_referring_domains_percent": None}


def test_parse_backlinks_overview_and_list():
    overview = payload("backlinks_overview.json")
    assert P.parse_authority(overview["data"])["referring_domains"] == 746
    assert overview["signedInput"]["input"]["mode"] == "subdomains"
    envelope = fixture("backlinks_list.json")
    assert envelope[0] == "TopBacklinks"
    rows = P.parse_backlinks_list(envelope[1])
    assert len(rows) == 20
    first = rows[0]
    assert first["source_link"] == "https://github.com/omkarcloud/ebay-scraper"
    assert first["target_link"] == "https://www.omkar.cloud/auth/sign-up?redirect=/api-key"
    assert first["source_domain_rating"] == 97.0
    assert first["anchor"] == "omkar.cloud"
    assert first["text_before"] == "Create an account at"
    assert first["is_in_raw_html"] is True and first["is_in_rendered_html"] is False
    with_redirect = [r for r in rows if r["redirect_chain"]]
    assert with_redirect and with_redirect[0]["redirect_chain"][0] == {"link": "https://omkar.cloud/", "http_code": 301}
    assert P.parse_backlinks_list(None) == []


def test_parse_traffic():
    out = P.parse_traffic(payload("traffic_overview.json"))
    assert out["monthly_organic_traffic"] == 164
    assert out["monthly_traffic_value"] == 26.83 and out["currency"] == "USD"   # upstream reports cents
    assert out["traffic_history"][0] == {"month": "2026-06", "organic_traffic": 73}
    assert len(out["traffic_history"]) == 6
    assert out["top_pages"][0] == {"link": "https://www.omkar.cloud/tools/google-maps-extractor",
                                   "traffic": 44, "share_percent": 78.57}
    assert out["top_countries"][0] == {"country": "IN", "share_percent": 34.98}
    assert out["top_keywords"][0] == {"keyword": "google map extractor", "position": 9, "traffic": 900}
    us = P.parse_traffic(payload("traffic_overview_us.json"))
    assert us["top_keywords"][0]["keyword"] == "ocr invoice processing open source"


def test_parse_broken_links():
    out = P.parse_broken_links(payload("broken_links.json"))
    assert out["inbound"]["total_backlinks"] == 22
    assert out["inbound"]["dofollow_backlinks_percent"] == 50.0
    assert len(out["inbound"]["broken_links"]) == 10
    first = out["inbound"]["broken_links"][0]
    assert first["http_code"] == 404
    assert first["target_link"] == "https://www.omkar.cloud/devtools/"
    assert "is_in_raw_html" not in first
    assert out["outbound"] == {"total_links": 0, "dofollow_links_percent": 0.0, "broken_links": []}
    assert P.parse_broken_links({})["inbound"]["broken_links"] == []


def test_parse_sitemap():
    out = P.parse_sitemap(payload("sitemap.json"))
    assert out["host"] == "paulgraham.com" and out["url_count"] == 1000
    assert out["crawled_count"] == 5939 and out["excluded_count"] == 4045
    assert out["is_capped"] is True and out["cap"] == 1000
    assert len(out["entries"]) == 1000
    assert out["entries"][0] == {"link": "https://21.paulgraham.com/04magnum.html", "last_modified": "2026-10-21"}


def test_parse_keyword_ideas():
    out = P.parse_keyword_ideas(payload("keyword_ideas.json"))
    assert out["total_ideas"] == 10186 and len(out["ideas"]) == 20
    assert out["total_questions"] == 1171 and len(out["questions"]) == 20
    assert out["ideas"][0] == {"keyword": "seo tools", "country": "US", "difficulty": "hard",
                               "volume_at_least": 100000, "updated_at": "2026-11-01"}
    unknown = [i for i in out["ideas"] if i["updated_at"] is None][0]
    assert unknown["difficulty"] is None
    assert {i["volume_at_least"] for i in out["ideas"]} <= {1000, 10000, 100000, 1000000, None}
    empty = P.parse_keyword_ideas(payload("keyword_ideas_amazon.json"))
    assert empty == {"total_ideas": 0, "ideas": [], "total_questions": None, "questions": []}


def test_volume_floor():
    assert P._volume_floor("MoreThanOneThousand") == 1000
    assert P._volume_floor("MoreThanTenThousand") == 10000
    assert P._volume_floor("MoreThanHundredThousand") == 100000
    assert P._volume_floor("MoreThanOneMillion") == 1000000
    assert P._volume_floor("MoreThanTen") == 10
    assert P._volume_floor("Unknown") is None


def test_parse_serp_difficulty():
    out = P.parse_serp(payload("kd_checker.json"))
    assert out["difficulty"] == 82 and out["referring_domains_needed"] == 399
    assert out["last_updated"] == "2026-11-01"
    assert [r["type"] for r in out["results"]] == ["ai_overview", "organic", "questions"] + ["organic"] * 7
    ai = out["results"][0]
    assert ai["position"] == 1 and ai["description"].startswith("Search Engine Optimization")
    organic = out["results"][1]
    assert organic["organic_position"] == 1
    assert organic["link"] == "https://smallseotools.com/"
    assert organic["display_link"] == "https://smallseotools.com"
    assert organic["metrics"]["domain_rating"] == 81.0
    assert organic["metrics"]["traffic_value"] == 224349.24   # upstream `cost` is in cents
    assert organic["metrics"]["top_keyword"] == "seo tools"
    assert organic["metrics"]["word_count"] == 981
    questions = out["results"][2]["questions"]
    assert questions[0] == {"question": "What are the SEO tools?", "link": None}
    plain = P.parse_serp(payload("serp_overview.json"))
    assert plain["difficulty"] is None and len(plain["results"]) == 10
    # "None" sitelink options are placeholders, not rows
    mixed = P.parse_serp_result({"content": ["organic", {"link": "None", "siteLinks": [
        "None", ["Some", {"title": "t", "url": ["Url", {"url": "https://a.b/"}]}]]}], "pos": 1})
    assert [s["link"] for s in mixed["sitelinks"]] == ["https://a.b/"]


def test_parse_rank():
    out = P.parse_rank(payload("rank_checker.json"))
    assert out["position"] == 11
    assert out["result"]["link"] == "https://ahrefs.com/free-seo-tools"
    assert out["result"]["metrics"]["domain_rating"] == 91.0
    assert "difficulty" not in out
    assert len(out["results"]) == 10
    not_ranking = dict(payload("rank_checker.json"), topPosition=None)
    assert P.parse_rank(not_ranking)["position"] is None
    assert P.parse_rank(not_ranking)["result"] is None
    # the OCaml option spelling of "absent"
    none_encoded = P.parse_rank(dict(payload("rank_checker.json"), topPosition="None"))
    assert none_encoded["position"] is None and none_encoded["result"] is None


def test_serp_nonsense_is_null_payload():
    assert fixture("serp_nonsense.json") == ["Ok", None]


def test_parse_ai_visibility():
    out = P.parse_ai_visibility(payload("ai_visibility.json"))
    assert out["total_citations"] == 674599
    assert out["citations_by_model"][0] == {"model": "chatgpt", "citations": 28937}
    assert {m["model"] for m in out["citations_by_model"]} >= {"google_ai_overviews", "google_ai_mode_keywords"}
    assert out["monthly_citations_by_model"][0]["model"] == "chatgpt"
    assert out["monthly_citations_by_model"][0]["timeline"][0] == {"month": "2026-05", "citations": 174}
    assert out["top_cited_domains"][0] == {"domain": "ahrefs.com", "mentions": 42510}
    assert out["top_cited_pages"][0]["link"] == "https://ahrefs.com/backlink-checker"
    assert out["top_cited_pages"][0]["mentions"] == 4128
    assert out["top_topics"][0]["ai_responses"] > 0
    assert "faviconUrl" not in json.dumps(out)
    empty = P.parse_ai_visibility(payload("ai_visibility_unknown.json"))
    assert empty["total_citations"] == 0 and empty["citations_by_model"] == []


def test_parse_ai_trackers():
    out = P.parse_ai_tracker(payload("ai_overviews.json"), "totalAiOverviewsMentions")
    assert out["total_mentions"] == 331607 and out["new_mentions_this_cycle"] == 13017
    assert out["total_topics"] == 58025 and out["total_domains"] == 93283
    assert out["top_topics"][0] == {"topic": "seo", "ai_responses": 8059}
    assert out["top_cited_domains"][0]["domain"] == "www.youtube.com"
    assert out["ai_overviews_timeline"][0] == {"month": "2026-05", "citations": 6585}
    assert out["ai_mode_timeline"][0]["citations"] == 109
    mode = P.parse_ai_tracker(payload("ai_mode.json"), "totalAiModeMentions")
    assert mode["total_mentions"] == 20695
    assert mode["top_topics"][0]["topic"] == "backlink checker"


def test_parsers_survive_garbage():
    for fn in (P.parse_authority, P.parse_backlinks_list, P.parse_traffic, P.parse_broken_links,
               P.parse_sitemap, P.parse_keyword_ideas, P.parse_serp, P.parse_rank, P.parse_ai_visibility):
        for junk in (None, {}, [], "x", {"serp": "nope", "results": 3}):
            fn(junk)
    P.parse_ai_tracker(None, "x")
    P.parse_serp_result({"content": ["video", {"title": "t", "url": "u", "nested": {"a": 1}}], "pos": 4})


# ---- ahrefstop pages -----------------------------------------------------------------------

@pytest.fixture(scope="module")
def youtube():
    return P.parse_website(fixture("website_youtube.html"), "youtube.com")


@pytest.fixture(scope="module")
def bulbagarden():
    return P.parse_website(fixture("website_bulbagarden.html"), "bulbagarden.net")


def test_website_identity(youtube):
    assert youtube["domain"] == "youtube.com"
    assert youtube["name"] == "YouTube"
    assert youtube["link"] == "https://ahrefstop.com/websites/youtube.com"
    assert youtube["description"].startswith("YouTube is a video sharing platform")
    assert youtube["period"] == "2026-10"
    assert youtube["updated_at"] == "2026-10-01"


def test_website_ranks(youtube, bulbagarden):
    assert youtube["ranks"] == {
        "worldwide": {"rank": 1, "rank_change": 2},
        "country": {"country": "US", "name": "United States", "rank": 2, "rank_change": 2},
        "category": {"category": "arts-and-entertainment", "name": "Entertainment", "rank": 1, "rank_change": None},
    }
    assert bulbagarden["ranks"]["worldwide"] == {"rank": 747, "rank_change": -433}
    assert bulbagarden["ranks"]["country"] is None
    assert bulbagarden["ranks"]["category"] == {"category": "games", "name": "Games", "rank": 21, "rank_change": -9}


def test_website_search_traffic(youtube):
    assert youtube["search_traffic"] == {
        "traffic": 3500000000, "traffic_change": 1700000000, "traffic_value": 563400000,
        "traffic_value_change": 335400000, "keywords": 121000000, "currency": "USD"}
    history = youtube["traffic_history"]
    assert history[0]["month"] == "2015-06"
    assert history[-1] == {"month": "2026-10", "organic_traffic": 3472781366, "traffic_value": 563440144}
    assert len(history) > 100


def test_website_countries(youtube):
    countries = youtube["traffic_by_country"]
    assert [c["country"] for c in countries] == ["US", "IN", "BR", "TR", "ID"]
    assert countries[0] == {"country": "US", "traffic": 763233570, "previous_traffic": 356256888,
                            "traffic_change": 406976682, "share_percent": 21.9}


def test_website_keywords(youtube):
    keywords = youtube["top_keywords"]
    assert keywords["country"] == "United States"
    assert len(keywords["keywords"]) == 5
    assert keywords["keywords"][0] == {"keyword": "youtube", "volume": 99600000, "volume_change": -2100000,
                                       "traffic": 90400000, "traffic_change": 2500000,
                                       "position": 1, "position_change": None}
    assert keywords["keywords"][2]["position_change"] == -1


def test_website_competitors_and_similar(youtube):
    competitors = youtube["competitors"]
    assert competitors["country"] == "United States"
    assert competitors["websites"][0] == {"domain": "wikipedia.org", "link": "https://ahrefstop.com/websites/wikipedia.org",
                                          "traffic": 4200000000, "traffic_change": -129700000, "pages": 2400000}
    assert len(competitors["websites"]) == 5
    similar = youtube["similarly_ranked"]
    assert len(similar) == 5
    assert similar[0]["domain"] == "youtube.com" and similar[0]["is_target"] is True
    assert similar[1] == {"domain": "wikipedia.org", "link": "https://ahrefstop.com/websites/wikipedia.org",
                          "is_target": False, "traffic": 2600000000, "traffic_change": -1100000000,
                          "rank": 2, "rank_change": -1}


def test_website_backlink_profile(youtube, bulbagarden):
    profile = youtube["backlink_profile"]
    assert profile["domain_rating"] == 99
    assert profile["linking_websites"] == 12700000 and profile["linking_websites_change"] == 107500
    assert profile["period"] == "2026-10"
    assert profile["linking_websites_history"][0] == {"month": "2015-04", "linking_websites": 6048933}
    assert len(profile["linking_websites_history"]) > 100
    assert bulbagarden["backlink_profile"]["domain_rating"] is not None


def test_website_sparse_and_garbage(bulbagarden):
    assert bulbagarden["search_traffic"]["traffic"] == 7500000
    assert bulbagarden["search_traffic"]["traffic_change"] == -8000000
    assert len(bulbagarden["top_keywords"]["keywords"]) == 5
    empty = P.parse_website("<html><body></body></html>", "x.com")
    assert empty["domain"] == "x.com" and empty["traffic_history"] == [] and empty["ranks"]["worldwide"] is None
    not_found = P.parse_website(fixture("website_not_found.html"), "omkar.cloud")
    assert not_found["search_traffic"]["traffic"] is None and not_found["top_keywords"]["keywords"] == []


def test_parse_competitors():
    out = P.parse_competitors(fixture("website_youtube_competitors.html"), "youtube.com")
    assert out["domain"] == "youtube.com"
    assert out["link"] == "https://ahrefstop.com/websites/youtube.com/competitors"
    assert out["country"] == "United States"
    assert len(out["competitors"]) == 10
    first = out["competitors"][0]
    assert first["domain"] == "wikipedia.org"
    assert first["description"].startswith("Wikipedia.org is a multilingual")
    assert first["ranks"]["worldwide"] == {"rank": 1, "rank_change": None}
    assert first["ranks"]["country"]["country"] == "US"
    assert first["traffic"] == 4200000000 and first["traffic_change"] == -129700000
    assert first["traffic_value"] == 504200000 and first["traffic_value_change"] == -39800000
    assert first["pages"] == 2400000 and first["domain_rating"] == 97
    assert P.parse_competitors("<html></html>", "x.com")["competitors"] == []
    # only the page's own main card (competitor-card--main, or the target's domain) is dropped
    assert len(P.parse_competitors(fixture("website_youtube_competitors.html"), "other.com")["competitors"]) == 10
    no_main = fixture("website_youtube_competitors.html").replace(" competitor-card--main", "")
    assert len(P.parse_competitors(no_main, "youtube.com")["competitors"]) == 10
    assert len(P.parse_competitors(no_main, "other.com")["competitors"]) == 11


def test_top_list_worldwide():
    out = P.parse_top_list(fixture("top_websites_page1.html"))
    assert out["title"] == "Top Websites" and out["period"] == "2026-10"
    assert len(out["websites"]) == 100
    assert out["websites"][0] == {"rank": 1, "rank_change": 2, "domain": "youtube.com",
                                  "link": "https://ahrefstop.com/websites/youtube.com",
                                  "category": "Entertainment", "category_slug": "arts-and-entertainment",
                                  "traffic": 3500000000, "traffic_change": 1700000000}
    assert out["websites"][-1]["rank"] == 100
    assert len(out["trending_up"]) == 10 and len(out["trending_down"]) == 10
    assert out["trending_up"][0]["domain"] == "mashable.com" and out["trending_up"][0]["rank_change"] == 909
    assert out["trending_down"][0]["rank_change"] < 0
    page2 = P.parse_top_list(fixture("top_websites_page2.html"))
    assert page2["websites"][0]["rank"] == 101 and page2["websites"][-1]["rank"] == 200


def test_top_list_country_and_category():
    india = P.parse_top_list(fixture("top_websites_india.html"))
    assert india["title"] == "Top Websites in India"
    assert len(india["websites"]) == 100
    assert india["websites"][0]["category_slug"] == "arts-and-entertainment"
    shopping = P.parse_top_list(fixture("top_websites_india_shopping.html"))
    assert shopping["title"] == "Top Shopping Websites in India"
    assert [w["domain"] for w in shopping["websites"]][:2] == ["amazon.in", "flipkart.com"] or len(shopping["websites"]) == 5
    assert len(shopping["websites"]) == 5
    assert shopping["websites"][-1]["rank"] == 5
    empty = P.parse_top_list(fixture("website_not_found.html"))
    assert empty["websites"] == [] and empty["trending_up"] == []
