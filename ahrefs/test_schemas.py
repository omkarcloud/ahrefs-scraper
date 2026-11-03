"""Offline tests for the /ahrefs/* request schemas.

    python -m pytest ahrefs/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ahrefs import schemas  # noqa: E402


def _error(schema, data):
    with pytest.raises(ValidationError) as info:
        schema().load(data)
    return info.value.normalized_messages()


def test_target_schema_accepts_domain_page_and_links():
    assert schemas.TargetSchema().load({"target": "omkar.cloud"}) == {"target": "omkar.cloud"}
    assert schemas.TargetSchema().load({"target": " https://www.omkar.cloud/botasaurus/ "}) == \
        {"target": "www.omkar.cloud/botasaurus"}
    assert schemas.TargetSchema().load({"target": "https://ahrefs.com/websites/youtube.com"}) == {"target": "youtube.com"}
    assert schemas.TargetSchema().load({"target": "https://ahrefs.com/backlink-checker/?input=moz.com&mode=exact"}) == \
        {"target": "moz.com"}


@pytest.mark.parametrize("value", ["", "not a site", "http://", "spaced out.com"])
def test_target_schema_rejects(value):
    errors = _error(schemas.TargetSchema, {"target": value})
    assert "target" in errors


def test_target_schema_rejects_sibling_params():
    errors = _error(schemas.TargetSchema, {"target": "omkar.cloud", "url": "omkar.cloud"})
    assert "url" in errors
    assert "target" in _error(schemas.TargetSchema, {})


def test_mode_schema():
    assert schemas.TargetModeSchema().load({"target": "omkar.cloud"}) == {"target": "omkar.cloud", "mode": "subdomains"}
    assert schemas.TargetModeSchema().load({"target": "omkar.cloud", "mode": "Exact"})["mode"] == "exact"
    errors = _error(schemas.TargetModeSchema, {"target": "omkar.cloud", "mode": "everything"})
    assert "subdomains, exact, prefix, domain" in " ".join(errors["mode"])


def test_traffic_schema_country():
    loaded = schemas.TrafficSchema().load({"target": "omkar.cloud", "country": "US"})
    assert loaded == {"target": "omkar.cloud", "mode": "subdomains", "country": "us"}
    assert schemas.TrafficSchema().load({"target": "omkar.cloud"})["country"] is None
    errors = _error(schemas.TrafficSchema, {"target": "omkar.cloud", "country": "usa"})
    assert "country" in errors


def test_top_websites_schema():
    assert schemas.TopWebsitesSchema().load({}) == {"country": None, "category": None, "page": 1}
    loaded = schemas.TopWebsitesSchema().load({"country": "IN", "category": "Shopping", "page": "1"})
    assert loaded == {"country": "india", "category": "shopping", "page": 1}
    assert schemas.TopWebsitesSchema().load({"country": "United Kingdom"})["country"] == "united-kingdom"
    assert "page" in _error(schemas.TopWebsitesSchema, {"page": "11"})
    assert "category" in _error(schemas.TopWebsitesSchema, {"category": "cars"})
    errors = _error(schemas.TopWebsitesSchema, {"country": "atlantis"})
    assert "not a country" in " ".join(errors["country"])


def test_trending_schema():
    assert schemas.TrendingSchema().load({"direction": "UP"}) == {"country": None, "category": None, "direction": "up"}
    assert "direction" in _error(schemas.TrendingSchema, {"direction": "sideways"})


def test_keyword_schemas():
    assert schemas.KeywordSchema().load({"keyword": " seo tools "}) == {"keyword": "seo tools", "country": "us"}
    assert schemas.KeywordSchema().load({"keyword": "x", "country": "IN"})["country"] == "in"
    assert "keyword" in _error(schemas.KeywordSchema, {})
    assert "keyword" in _error(schemas.KeywordSchema, {"keyword": "   "})
    ideas = schemas.KeywordIdeasSchema().load({"keyword": "seo tools"})
    assert ideas == {"keyword": "seo tools", "country": "us", "search_engine": "Google", "questions": True}
    ideas = schemas.KeywordIdeasSchema().load({"keyword": "seo tools", "search_engine": "google-ai-mode", "questions": "no"})
    assert ideas["search_engine"] == "GoogleAIMode" and ideas["questions"] is False
    assert "search_engine" in _error(schemas.KeywordIdeasSchema, {"keyword": "x", "search_engine": "duckduckgo"})
    rank = schemas.KeywordRankSchema().load({"keyword": "seo tools", "target": "https://ahrefs.com/websites/ahrefs.com"})
    assert rank == {"keyword": "seo tools", "country": "us", "target": "ahrefs.com"}
    assert "target" in _error(schemas.KeywordRankSchema, {"keyword": "seo tools"})


def test_brand_schema():
    assert schemas.BrandSchema().load({"brand": " Ahrefs "}) == {"brand": "Ahrefs"}
    assert "brand" in _error(schemas.BrandSchema, {})
    assert "brand" in _error(schemas.BrandSchema, {"brand": "x" * 101})
    assert "name" in _error(schemas.BrandSchema, {"brand": "nike", "name": "nike"})
