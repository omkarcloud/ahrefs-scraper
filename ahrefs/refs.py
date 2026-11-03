"""Reference resolvers + the slug tables for /ahrefs/*.

ONE param per input (tripadvisor QueryOrIdField convention):

  target    a domain ("omkar.cloud"), a page ("www.omkar.cloud/botasaurus",
            with or without a scheme), an ahrefs.com / ahrefstop.com
            /websites/<domain> link, or one of ahrefs.com's own free-tool
            links (…/backlink-checker/?input=youtube.com&mode=subdomains)
            -> the protocol-less target string Ahrefs' v4 RPCs take
  country   (top-websites lists) an ISO-2 code ("in"), an ahrefstop slug
            ("india") or the plain name -> the slug
  category  an ahrefstop category slug ("shopping", "jobs-and-education")

Resolvers raise ValueError with a user-facing message (RefField turns it
into a 400).

Tables captured 2026-11-03 from https://ahrefstop.com/sitemap-index-pages.xml
(183 country lists + 25 category lists) and from the free-tool bundles'
InvalidInput messages (search engines, modes).
"""
import re
from urllib.parse import parse_qs, unquote, urlencode, urlparse

SITE = "https://ahrefs.com"
RPC_BASE = SITE + "/v4/"
TOP_SITE = "https://ahrefstop.com"

# Backlink / traffic / broken-link scope, as the free tools name it
# (upstream answers Mode.UnknownMode otherwise).
MODES = ("subdomains", "exact", "prefix", "domain")

# Keyword-ideas engines: public value -> the v4 token (CamelCase; a
# lower-case value answers InvalidInput). Amazon / YouTube returned no
# ideas on 2026-11-03 but are accepted by the RPC, so they stay listed.
SEARCH_ENGINES = {
    "google": "Google", "bing": "Bing", "yahoo": "Yahoo", "yandex": "Yandex",
    "baidu": "Baidu", "naver": "Naver", "seznam": "Seznam", "daum": "Daum", "yep": "Yep",
    "youtube": "YouTube", "amazon": "Amazon",
    "google-images": "GoogleImages", "google-news": "GoogleNews", "google-videos": "GoogleVideos",
    "google-ai-mode": "GoogleAIMode", "chatgpt": "ChatGPT", "gemini": "Gemini",
    "perplexity": "Perplexity", "copilot": "Copilot", "grok": "Grok", "claude": "Claude",
}

# The v4 model tokens -> public names (AI visibility / overviews / mode).
AI_MODELS = {
    "Chatgpt": "chatgpt", "Gemini": "gemini", "Perplexity": "perplexity", "Copilot": "copilot",
    "Grok": "grok", "Claude": "claude", "GoogleAIOverviews": "google_ai_overviews",
    "GoogleAIMode": "google_ai_mode", "GoogleAIOverviews_Keywords": "google_ai_overviews_keywords",
    "GoogleAIMode_Keywords": "google_ai_mode_keywords",
}

CATEGORIES = (
    "arts-and-entertainment", "autos-and-vehicles", "beauty-and-fitness", "books-and-literature",
    "business", "computers-and-electronics", "finance", "food-and-drink", "games", "health",
    "hobbies-and-leisure", "home-and-garden", "internet-and-telecom", "jobs-and-education",
    "law-and-government", "news", "people-and-society", "pets-and-animals", "real-estate",
    "reference", "science", "shopping", "social-networks", "sports", "travel-and-transportation",
)

# ahrefstop country slug -> ISO-2. Generated 2026-11-03 from the sitemap's
# 183 /websites/<country> pages against the ISO 3166 names (pycountry
# 24.6.1), the odd ones matched by hand (korea = KR, congo = CG, ...).
COUNTRY_SLUGS = {
    'andorra': 'AD', 'united-arab-emirates': 'AE', 'afghanistan': 'AF', 'antigua-and-barbuda': 'AG',
    'anguilla': 'AI', 'albania': 'AL', 'armenia': 'AM', 'angola': 'AO', 'argentina': 'AR',
    'american-samoa': 'AS', 'austria': 'AT', 'australia': 'AU', 'azerbaijan': 'AZ',
    'bosnia-and-herzegovina': 'BA', 'bangladesh': 'BD', 'belgium': 'BE', 'burkina-faso': 'BF',
    'bulgaria': 'BG', 'bahrain': 'BH', 'burundi': 'BI', 'benin': 'BJ', 'brunei-darussalam': 'BN',
    'bolivia': 'BO', 'brazil': 'BR', 'bahamas': 'BS', 'bhutan': 'BT', 'botswana': 'BW',
    'belarus': 'BY', 'belize': 'BZ', 'canada': 'CA', 'congo-democratic-republic': 'CD',
    'central-african-republic': 'CF', 'congo': 'CG', 'switzerland': 'CH', 'cote-divoire': 'CI',
    'cook-islands': 'CK', 'chile': 'CL', 'cameroon': 'CM', 'colombia': 'CO', 'costa-rica': 'CR',
    'cape-verde': 'CV', 'cyprus': 'CY', 'czech-republic': 'CZ', 'germany': 'DE', 'djibouti': 'DJ',
    'denmark': 'DK', 'dominica': 'DM', 'dominican-republic': 'DO', 'algeria': 'DZ', 'ecuador': 'EC',
    'estonia': 'EE', 'egypt': 'EG', 'spain': 'ES', 'ethiopia': 'ET', 'finland': 'FI', 'fiji': 'FJ',
    'micronesia': 'FM', 'france': 'FR', 'gabon': 'GA', 'united-kingdom': 'GB', 'georgia': 'GE',
    'guernsey': 'GG', 'ghana': 'GH', 'gibraltar': 'GI', 'greenland': 'GL', 'gambia': 'GM',
    'guadeloupe': 'GP', 'greece': 'GR', 'guatemala': 'GT', 'guyana': 'GY', 'hong-kong': 'HK',
    'honduras': 'HN', 'croatia': 'HR', 'haiti': 'HT', 'hungary': 'HU', 'indonesia': 'ID',
    'ireland': 'IE', 'israel': 'IL', 'isle-of-man': 'IM', 'india': 'IN', 'iraq': 'IQ',
    'iceland': 'IS', 'italy': 'IT', 'jersey': 'JE', 'jamaica': 'JM', 'jordan': 'JO', 'japan': 'JP',
    'kenya': 'KE', 'kyrgyzstan': 'KG', 'cambodia': 'KH', 'kiribati': 'KI', 'korea': 'KR',
    'kuwait': 'KW', 'kazakhstan': 'KZ', 'lao-peoples-democratic-republic': 'LA', 'lebanon': 'LB',
    'liechtenstein': 'LI', 'sri-lanka': 'LK', 'lesotho': 'LS', 'lithuania': 'LT', 'luxembourg': 'LU',
    'latvia': 'LV', 'libyan-arab-jamahiriya': 'LY', 'morocco': 'MA', 'moldova': 'MD',
    'montenegro': 'ME', 'madagascar': 'MG', 'north-macedonia': 'MK', 'mali': 'ML', 'myanmar': 'MM',
    'mongolia': 'MN', 'malta': 'MT', 'mauritius': 'MU', 'maldives': 'MV', 'malawi': 'MW',
    'mexico': 'MX', 'malaysia': 'MY', 'mozambique': 'MZ', 'namibia': 'NA', 'niger': 'NE',
    'nigeria': 'NG', 'nicaragua': 'NI', 'netherlands': 'NL', 'norway': 'NO', 'nepal': 'NP',
    'new-zealand': 'NZ', 'oman': 'OM', 'panama': 'PA', 'peru': 'PE', 'papua-new-guinea': 'PG',
    'philippines': 'PH', 'pakistan': 'PK', 'poland': 'PL', 'puerto-rico': 'PR', 'palestine': 'PS',
    'portugal': 'PT', 'paraguay': 'PY', 'qatar': 'QA', 'romania': 'RO', 'serbia': 'RS',
    'russian-federation': 'RU', 'rwanda': 'RW', 'saudi-arabia': 'SA', 'solomon-islands': 'SB',
    'seychelles': 'SC', 'sweden': 'SE', 'singapore': 'SG', 'slovenia': 'SI', 'slovakia': 'SK',
    'sierra-leone': 'SL', 'san-marino': 'SM', 'senegal': 'SN', 'somalia': 'SO', 'suriname': 'SR',
    'sao-tome-and-principe': 'ST', 'el-salvador': 'SV', 'chad': 'TD', 'togo': 'TG', 'thailand': 'TH',
    'tajikistan': 'TJ', 'timor-leste': 'TL', 'turkmenistan': 'TM', 'tunisia': 'TN', 'tonga': 'TO',
    'turkey': 'TR', 'trinidad-and-tobago': 'TT', 'taiwan': 'TW', 'tanzania': 'TZ', 'ukraine': 'UA',
    'uganda': 'UG', 'united-states': 'US', 'uruguay': 'UY', 'uzbekistan': 'UZ',
    'saint-vincent-and-grenadines': 'VC', 'venezuela': 'VE', 'virgin-islands-british': 'VG',
    'virgin-islands-us': 'VI', 'vietnam': 'VN', 'vanuatu': 'VU', 'samoa': 'WS', 'south-africa': 'ZA',
    'zambia': 'ZM', 'zimbabwe': 'ZW',
}
COUNTRY_CODE_TO_SLUG = {code: slug for slug, code in COUNTRY_SLUGS.items()}

_HOST_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _is_ahrefs_host(host):
    return host in ("ahrefs.com", "ahrefstop.com") or host.endswith((".ahrefs.com", ".ahrefstop.com"))


def _from_ahrefs_link(url):
    """An ahrefs.com / ahrefstop.com link -> the target it is about, or None
    when the link names none (the homepage, a blog post)."""
    parsed = urlparse(url)
    # /websites/<domain>[/competitors] on either host
    match = re.match(r"^/websites/([^/]+)", parsed.path or "")
    if match:
        candidate = unquote(match.group(1)).strip().lower()
        if candidate and candidate not in COUNTRY_SLUGS and candidate not in CATEGORIES \
                and not candidate.isdigit() and "." in candidate:
            return candidate
        return None
    # the free tools link to each other as ?input=<target>&mode=...
    query = parse_qs(parsed.query or "")
    for key in ("input", "target", "url"):
        values = query.get(key)
        if values and values[0].strip():
            return values[0].strip()
    return None


def resolve_target(value, _unwrap=True):
    """Domain / page / ahrefs link -> protocol-less target ("www.omkar.cloud/botasaurus").
    An ahrefs.com / ahrefstop.com link that names another site (a
    /websites/<domain> page, a tool's ?input=) is unwrapped once; any other
    ahrefs.com URL is a target like any other page (ahrefs.com/blog/x)."""
    value = (value or "").strip()
    if not value or any(ch.isspace() for ch in value):
        raise ValueError("Must be a domain (omkar.cloud), a page link, or an ahrefs.com link.")
    url = value if value.lower().startswith(("http://", "https://")) else ("https:" + value if value.startswith("//") else "https://" + value)
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if _unwrap and _is_ahrefs_host(host):
        inner = _from_ahrefs_link(url)
        if inner is not None:
            return resolve_target(inner, _unwrap=False)
    if not _HOST_RE.match(host):
        raise ValueError(f"'{value}' is not a domain or page link (try omkar.cloud or https://www.omkar.cloud/botasaurus).")
    if parsed.port:
        host = f"{host}:{parsed.port}"
    path = parsed.path or ""
    if parsed.query:
        path += "?" + parsed.query
    return host + path.rstrip("/") if path not in ("", "/") else host


def target_host(target):
    """The host of a resolved target ("www.omkar.cloud/x" -> "www.omkar.cloud")."""
    return target.split("/", 1)[0].split("?", 1)[0].split(":", 1)[0].lower()


def resolve_country_slug(value):
    """ISO-2 code / ahrefstop slug / country name -> the ahrefstop slug."""
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Must be a country code (in), an ahrefstop slug (india) or a name.")
    code = raw.upper()
    if code in COUNTRY_CODE_TO_SLUG:
        return COUNTRY_CODE_TO_SLUG[code]
    slug = _SLUG_RE.sub("-", raw.lower().replace("&", "and")).strip("-")
    if slug in COUNTRY_SLUGS:
        return slug
    aliases = {"uk": "united-kingdom", "usa": "united-states", "us": "united-states",
               "south-korea": "korea", "russia": "russian-federation", "czechia": "czech-republic",
               "laos": "lao-peoples-democratic-republic", "libya": "libyan-arab-jamahiriya",
               "ivory-coast": "cote-divoire", "uae": "united-arab-emirates", "vietnam": "vietnam",
               "viet-nam": "vietnam", "macedonia": "north-macedonia", "drc": "congo-democratic-republic"}
    if slug in aliases:
        return aliases[slug]
    raise ValueError(f"'{value}' is not a country ahrefstop.com lists (use an ISO-2 code like "
                     "in / us / gb, or a slug like india).")


def country_code_for_slug(slug):
    return COUNTRY_SLUGS.get(slug)


def website_link(domain):
    return f"{TOP_SITE}/websites/{domain}"


def competitors_link(domain):
    return f"{TOP_SITE}/websites/{domain}/competitors"


def top_list_path(country_slug=None, category=None, page=1):
    """/websites[/<page>] (worldwide), /websites/<country>[/<category>],
    /websites/<category>. Only the worldwide list has pages (1-10)."""
    if not country_slug and not category:
        return "/websites" if page <= 1 else f"/websites/{page}"
    segments = [s for s in (country_slug, category) if s]
    return "/websites/" + "/".join(segments)


def tool_link(tool, target, mode=None, **params):
    """The free tool's own page for a report (the public `link` of a
    response): /<tool>?input=<target>[&mode=..][&country=..]."""
    query = {"input": target}
    if mode:
        query["mode"] = mode
    query.update({k: v for k, v in params.items() if v})
    return f"{SITE}/{tool}?" + urlencode(query)
