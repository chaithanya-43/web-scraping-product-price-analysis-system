# PriceLens · Web Scraping and Product Price Analysis

PriceLens is a Flask application for comparing publicly available product data from product pages and listings. It uses structured product data where available, enriches incomplete listings from same-site product pages, summarizes prices, and saves analyses to a per-account history.

## What it supports

- Generic public HTTP(S) product and listing pages, including schema.org `Product`, `ItemList`, `ListItem`, arrays, `@graph`, nested offers and price specifications.
- Open Graph metadata and common HTML fallbacks for pages without usable JSON-LD.
- Product name, price, currency, rating, availability, category, discount, product URL, and scrape time when published by the page.
- Same-host detail-page enrichment for up to 160 incomplete listing entries, subject to the same access rules and request pacing. HTTP connections are reused per worker thread while the one-second host pacing remains in place.
- Price summaries, currency-aware comparisons, charts, filtering, sortable product results, and account-scoped analysis history that can be reopened.
- Account registration, login, password hashing, profile management, and password recovery with email OTP.
- CSV and Excel (.xlsx) import/export through the existing cleaning and statistics pipeline.
- Optional JavaScript-rendered page fallback when static HTML does not expose product details; browser requests remain subject to URL, robots.txt, response-size, timeout, and per-host pacing checks.
- The command-line workflow for CSV and chart output.

Extraction depends on the source publishing readable HTML or structured metadata. Unknown sites may use markup this parser cannot recognize; Pages that require JavaScript may still be unsupported when Chromium is unavailable or the rendered markup is unrecognized. When prices use different or missing currencies, PriceLens shows products without combining unlike amounts into a misleading summary.

## Responsible access

Every fetch checks the host's `robots.txt` for `PriceAnalyzerBot/1.0`, waits at least one second between requests to the same host, limits pagination to 20 pages, and revalidates redirects. Private/local network targets are rejected. A denied or unavailable robots policy (except a clear 404), rate limit, or access challenge stops the scrape with an explanation. PriceLens does not sign in, solve CAPTCHAs, evade access controls, or use proxies. JavaScript rendering is only attempted after a permitted static fetch returns no usable products; each browser request is revalidated and paced under the same robots policy. Respect each site's terms and only analyze sources you are allowed to access.

## Setup

Requires Python 3.10 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Set a private Flask session key before using accounts beyond local development. PriceLens refuses to start in production if `PRICE_ANALYZER_SECRET_KEY` is missing or still has the example placeholder. In production, use HTTPS and set `FLASK_ENV=production` so session cookies are marked secure. The SQLite database is stored at `data/users.db`.

```powershell
$env:PRICE_ANALYZER_SECRET_KEY = "replace-with-a-long-random-secret"
```

For local development, copy `.env.example` to `.env` and fill in local-only values using `KEY=VALUE` lines. PriceLens loads this file at startup without overriding environment variables already supplied by the process. `.env` is ignored by Git; do not commit it.

### Password recovery email

Recovery codes are delivered by SMTP. Configure these environment variables in the app's runtime environment; credentials are not stored in the repository. SMTP delivery must be configured for recovery codes to arrive. The endpoint intentionally returns the same response for known and unknown email addresses.

```powershell
$env:PRICE_LENS_SMTP_HOST = "smtp.gmail.com"
$env:PRICE_LENS_SMTP_PORT = "587"
$env:PRICE_LENS_SMTP_FROM = "your-address@gmail.com"
$env:PRICE_LENS_SMTP_USER = "your-address@gmail.com"
$env:PRICE_LENS_SMTP_PASSWORD = "your-gmail-app-password"
$env:PRICE_LENS_SMTP_STARTTLS = "true"
$env:PRICE_LENS_SMTP_SSL = "false"
$env:PRICE_LENS_OTP_SECRET = "another-long-random-secret"
```

For Gmail, create and use a Google App Password; never use your normal Google account password. Use port 587 with STARTTLS. `PRICE_LENS_OTP_SECRET` should be stable across restarts so active recovery records remain verifiable. The recovery endpoint returns a configuration error if SMTP is not configured and records a server-side diagnostic if delivery fails; it never returns an OTP.

## Run the web app

```powershell
python -m flask --app web.app run
```

The Playwright Chromium install enables the JavaScript fallback. If the browser binary is unavailable, static HTML scraping continues.

Open `http://127.0.0.1:5000`, create an account, and sign in. The dashboard accepts a product or listing URL and a page limit from 1 to 20. Supported public demonstration sources include [Books to Scrape](https://books.toscrape.com/) and the [TestingURL.dev laptop listing](https://testingurl.dev/scraping/ecommerce/category/laptops). Other public URLs are handled by the generic parser when their access policy permits fetching.

Useful endpoints:

- `GET /api/health` — service health.
- `POST /api/analyze` — authenticated analysis; JSON body: `{"url":"https://example.com/product","pages":1}`.
- `POST /api/import` — authenticated CSV or `.xlsx` import, cleaned and analyzed using the same pipeline.
- `GET /api/history/<id>/export/csv` or `/xlsx` — download a saved analysis.
- `GET /api/history` — authenticated list of saved analyses.
- `GET /api/history/<id>` — authenticated saved result and product details.
- `POST /api/auth/forgot-password`, `/api/auth/verify-otp`, `/api/auth/reset-password` — password recovery flow.

## Run the command-line workflow

```powershell
python main.py
```

Enter a public URL and page count when prompted. Raw product rows and cleaned products are written to `data/raw/products_raw.csv` and `data/processed/products.csv`; charts are written to `data/processed/`.

## Production deployment preparation

A `Procfile` starts the app with Gunicorn. Set `FLASK_ENV=production`, a unique `PRICE_ANALYZER_SECRET_KEY`, HTTPS, and the SMTP settings before deployment. Install Chromium with `python -m playwright install chromium` where JavaScript fallback is needed. The current history store is SQLite in `data/users.db`; use a persistent disk and a single application instance unless the database layer is migrated to a shared production database. Configure a persistent volume before relying on saved accounts or analysis history in a hosted environment.

## Tests

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=".pytest_tmp"
```

Tests use local fixtures and mocked HTTP responses for parser, robots-policy, authentication, history, and recovery coverage. They do not make live requests to ecommerce sites.

## Project layout

```text
analysis/                 Cleaning, statistics, and insights
scraper/fetcher.py        URL validation, robots, pacing, and HTTP
scraper/parsers/          Source-specific and generic parsers
scraper/scraper.py        Pagination, enrichment, and normalization
web/app.py                Flask pages and JSON API
web/auth/                 Accounts, sessions, and SQLite history
web/templates/            PriceLens pages
web/static/               Responsive interface and charts
tests/                    Offline unit and integration tests
```
