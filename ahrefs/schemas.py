"""Marshmallow request schemas for every /ahrefs/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    target    a domain, a page link, an ahrefs.com / ahrefstop.com
              /websites/<domain> link or one of ahrefs.com's own free-tool
              links (…?input=<target>) — ahrefs/refs.resolve_target
    keyword   the search query (free text)
    brand     the brand name the AI trackers look for (free text)
    country   ISO-2; for the top-websites lists also an ahrefstop slug or
              a country name ("india")
    category  an ahrefstop category slug (refs.CATEGORIES)
    mode      backlink / traffic scope: subdomains (default), exact, prefix, domain
"""
from marshmallow import validate

from schema_fields import BaseSchema, ChoiceField, CountryCodeField, Flag, PageField, QueryField, RefField, StrippedString
from ahrefs import refs

TOP_LIST_PAGES = 10      # the worldwide list is 10 pages of 100 (top 1000)


class TargetField(RefField):
    resolver = staticmethod(refs.resolve_target)


class CountrySlugField(RefField):
    """ISO-2 / slug / name -> the ahrefstop country slug (optional)."""
    resolver = staticmethod(refs.resolve_country_slug)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class LowerCountryField(CountryCodeField):
    """The free tools take lower-case ISO-2 ("us")."""

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        return value.lower() if value else None


def _target_field(description=None):
    return TargetField(metadata={"description": description or (
        "domain (omkar.cloud), page link (https://www.omkar.cloud/botasaurus), "
        "or an ahrefs.com / ahrefstop.com /websites/<domain> link")})


def _mode_field():
    return ChoiceField(list(refs.MODES), load_default="subdomains", metadata={
        "description": "scope: subdomains (default, the whole site), exact (that URL only), "
                       "prefix (URLs starting with it), domain (the domain without subdomains)"})


class TargetSchema(BaseSchema):
    target = _target_field()


class TargetModeSchema(BaseSchema):
    target = _target_field()
    mode = _mode_field()


class TrafficSchema(BaseSchema):
    target = _target_field()
    mode = _mode_field()
    country = LowerCountryField(metadata={
        "description": "ISO-2 country whose top pages / keywords to report (default: worldwide)"})


class TopWebsitesSchema(BaseSchema):
    country = CountrySlugField(metadata={
        "description": "country of the ranking: ISO-2 code (in), ahrefstop slug (india) or name; "
                       "default worldwide"})
    category = ChoiceField(list(refs.CATEGORIES), metadata={
        "description": "category slug: " + ", ".join(refs.CATEGORIES)})
    page = PageField(max_page=TOP_LIST_PAGES, metadata={
        "description": f"page of 100 (worldwide list: 1-{TOP_LIST_PAGES} = top 1000; "
                       "country / category lists have one page)"})


class TrendingSchema(BaseSchema):
    country = CountrySlugField(metadata={
        "description": "country of the ranking: ISO-2 code (in), ahrefstop slug (india) or name; "
                       "default worldwide"})
    category = ChoiceField(list(refs.CATEGORIES), metadata={
        "description": "category slug: " + ", ".join(refs.CATEGORIES)})
    direction = ChoiceField(["up", "down"], metadata={
        "description": "only the sites trending up / down (default: both lists)"})


class KeywordSchema(BaseSchema):
    keyword = QueryField(metadata={"description": "the search query"})
    country = LowerCountryField(load_default="us", metadata={
        "description": "ISO-2 country of the Google SERP (default us)"})


class KeywordIdeasSchema(KeywordSchema):
    search_engine = ChoiceField(dict(refs.SEARCH_ENGINES), load_default="Google", metadata={
        "description": "engine: " + ", ".join(refs.SEARCH_ENGINES) + " (default google)"})
    questions = Flag(load_default=True, metadata={
        "description": "also return question-form ideas (default true)"})


class KeywordRankSchema(KeywordSchema):
    target = _target_field("the domain or page whose ranking to check")


class BrandSchema(BaseSchema):
    brand = StrippedString(required=True, validate=validate.Length(min=1, max=100), metadata={
        "description": "brand name to look for in AI answers (ahrefs, nike)"})
