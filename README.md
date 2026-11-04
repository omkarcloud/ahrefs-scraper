# 📈 Ahrefs Scraper

Ahrefs Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Ahrefs data for free.

## ✨ What Can I Get?

- 📈 **Traffic since 2015 for 190,000+ top websites** — monthly visits & value, ranks, top countries, keywords & competitors
- 🔗 **Domain Rating & backlinks for any website** — DR, backlinks, referring domains, top 20 backlinks with anchors & broken links
- 🔑 **Keyword research on 21 search engines** — keyword & question ideas, Keyword Difficulty, the Google top 10 & rank checks
- 🤖 **AI visibility for any brand** — citations in ChatGPT, Gemini, Perplexity, Copilot, Google AI Overviews & AI Mode

## 🎥 Example: A Full Ahrefs Website Profile

```json
{
  "domain": "tesla.com",
  "name": "Tesla | Electric Cars, Solar & Clean Energy",
  "link": "https://ahrefstop.com/websites/tesla.com",
  "period": "2026-10",
  "ranks": {
    "worldwide": { "rank": 637, "rank_change": -256 },
    "category": { "category": "autos-and-vehicles", "name": "Vehicles", "rank": 19, "rank_change": -7 }
  },
  "search_traffic": { "traffic": 8600000, "traffic_change": -4900000, "traffic_value": 4600000, "keywords": 511500, "currency": "USD" },
  "traffic_history": [
    { "month": "2024-01", "organic_traffic": 19476348, "traffic_value": 7907971 },
    { "month": "2026-10", "organic_traffic": 8639513, "traffic_value": 4635832 }
  ],
  "traffic_by_country": [
    { "country": "US", "traffic": 2680347, "previous_traffic": 5830973, "share_percent": 31.0 },
    { "country": "FR", "traffic": 766677, "previous_traffic": 926090, "share_percent": 8.8 }
  ],
  "top_keywords": {
    "country": "United States",
    "keywords": [{ "keyword": "tesla model 3", "volume": 917000, "traffic": 594300, "position": 1 }]
  },
  "competitors": { "websites": [{ "domain": "teslarati.com", "traffic": 143800, "pages": 3600 }] },
  "backlink_profile": { "domain_rating": 90, "linking_websites": 89400, "linking_websites_change": 322 }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Ahrefs Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/ahrefs-scraper
cd ahrefs-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/domains/overview?target=tesla.com"
```

```json
{
  "domain": "tesla.com",
  "name": "Tesla | Electric Cars, Solar & Clean Energy",
  "period": "2026-10",
  "ranks": {
    "worldwide": { "rank": 637, "rank_change": -256 },
    "category": { "category": "autos-and-vehicles", "name": "Vehicles", "rank": 19, "rank_change": -7 }
  },
  "search_traffic": { "traffic": 8600000, "traffic_value": 4600000, "keywords": 511500, "currency": "USD" },
  "traffic_by_country": [
    { "country": "US", "traffic": 2680347, "share_percent": 31.0 }
  ],
  "top_keywords": {
    "country": "United States",
    "keywords": [{ "keyword": "tesla", "volume": 2700000, "traffic": 1800000, "position": 1 }]
  },
  "backlink_profile": { "domain_rating": 90, "linking_websites": 89400 },
  "updated_at": "2026-10-01"
}
```

All 16 endpoints are now live at `http://localhost:8000`. The website overview, competitors, top websites and trending websites work straight away.

### 🔓 Unlock Domain Rating, Backlinks, Keywords & AI Visibility

The other 12 endpoints run on Ahrefs' free SEO tools, and Ahrefs puts a Cloudflare Turnstile check on every one of those calls. The scraper solves it for you with CapSolver in about 3 seconds, no browser needed:

1. Get a [CapSolver](https://dashboard.capsolver.com/passport/register?inviteCode=lvdYBC4sYKRm) API key. One solve covers one call, about $1.20 per 1,000 calls.
2. Start the API with it:
   ```bash
   CAPSOLVER_API_KEY=CAP-... python run.py
   ```

Answers are cached in memory for hours, so asking for the same report twice costs one solve. See [config.py](config.py) for every option.

## 📚 Endpoints

16 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Website Overview | `/domains/overview` | Traffic since 2015, ranks, countries, keywords, competitors and DR |
| Domain Rating | `/domains/authority` | DR, backlinks, referring domains and dofollow share for any site |
| Backlinks | `/domains/backlinks` | Backlink totals plus the top 20 backlinks with anchors |
| Organic Traffic | `/domains/traffic` | Monthly visits and value, top pages, countries and keywords |
| Competitors | `/domains/competitors` | Sites fighting for the same keywords, with traffic and DR |
| Broken Links | `/domains/broken-links` | Broken backlinks to win back and broken links to fix |
| Sitemap | `/domains/sitemap` | Up to 1,000 crawled URLs with last-modified dates |
| Keyword Ideas | `/keywords/ideas` | Keyword and question ideas on 21 search engines |
| Keyword Difficulty | `/keywords/difficulty` | KD score plus the referring domains you need to rank |
| SERP Overview | `/keywords/serp` | Google top 10 with DR, backlinks and traffic per result |
| Keyword Rank | `/keywords/rank` | Where any site ranks on Google for a keyword |
| AI Visibility | `/brands/ai-visibility` | Brand citations in ChatGPT, Gemini, Perplexity, Copilot and Google AI |
| AI Overviews / AI Mode | `/brands/ai-overviews`, `/brands/ai-mode` | Brand mentions, topics and cited pages in Google's AI answers |
| Top / Trending Websites | `/websites/top`, `/websites/trending` | The most visited sites by country and category, plus the fastest movers |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-ahrefs-scraper-free-200-calls/pricing) — 200 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-ahrefs-scraper-free-200-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-ahrefs-scraper-free-200-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/domains/overview",
    params={"target": "tesla.com"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Ahrefs Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/ahrefs-scraper-github-whatsapp)

[![Ask Us by Email about Ahrefs Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](https://www.omkar.cloud/l/ahrefs-scraper-github-email)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**Semrush Scraper**](https://www.omkar.cloud/tools/semrush-scraper) — Semrush website traffic, keywords, backlinks & competitors
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/ahrefs-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/ahrefs-scraper)

*Disclosure: the CapSolver link above is a referral link. CapSolver pays us a small commission for those solves. It costs you nothing extra. This helps support the project.*
