# Crawlbase findings (measured 29 October 2026)

All numbers below come from live calls made with `scripts/verify_assumptions.py`, `scripts/compare_tokens_md.py`, and `scripts/compare_readability.py`, using the Normal and JS tokens from the project `.env`. The raw responses are saved in this folder. Tokens were scrubbed from every file.

## 1. Response shape of `scraper=generic-extractor`

The docs list `title`, `headings`, `links`, `main_content`, `meta_description`, and `language`. The live response is different:

- The HTTP body is a JSON envelope: `original_status`, `pc_status`, `cb_status`, `url`, `domain_complexity`, `body` (and `storage_url` when `store=true`).
- `body` holds the parsed page with these keys: `alert`, `title`, `favicon`, `meta` (`description`, `keywords`), `content`, `canonical`, `images`, `videos`, `grouped_images`, `og_images`, `links`.
- The readable text is in `content`, not `main_content`. There is no `headings` or `language` key.
- `links` is a list of plain URL strings. There is no `text` or `rel` per link, so discovery can only match on the URL.

The code accepts links as strings or as `{"href": ...}` objects, so it keeps working if the shape changes to the documented one.

## 2. Absolute or relative hrefs

| Homepage | Links | Absolute | Not absolute |
| --- | --- | --- | --- |
| close.com | 90 | 89 | 1 (`tel:` link) |
| pipedrive.com | 103 | 103 | 0 |
| zendesk.com | 125 | 125 | 0 |
| basecamp.com | 52 | 51 | 1 (`mailto:` link) |
| hey.com | 54 | 54 | 0 |

Links come back already resolved to absolute URLs. `images` do keep relative paths (24 on close.com, 51 on basecamp.com, for example `/_astro/home-hero-poster.webp`). The code still runs every href through `urljoin(page_url, href)` and drops `mailto:`, `tel:`, `javascript:`, and fragments, so relative links work too.

Links also include other hosts (`app.close.com`, `help.close.com`, `chatgpt.com/?q=...team...`). Matching keywords only on the last path segment of same-host links avoids false hits in query strings and in parent folders like `/company/legal`.

## 3. `scraper=generic-extractor` and `store=true` in one call

- Yes, they combine. The call returns the parsed JSON and a `storage_url` inside the JSON envelope. The `rid` is the `rid` query parameter of `storage_url`. There is no `rid` response header for this call.
- With `format=md&store=true`, the `storage_url` comes back as a response header instead (again no separate `rid` header).
- The Storage API returns what the Crawling API returned: the parsed generic-extractor JSON for the first call, and the Markdown for the second. It does not return raw HTML in these cases.
- Each call gets its own `rid`. Two calls on the same URL produced two different rids, and both stayed readable.
- Both the Normal and the JS token can read a stored `rid`.
- The `storage_url` contains the token used for the request. The code only keeps the `rid` and never logs the URL.
- The official `crawlbase` Python SDK (1.1.0) keeps only `original_status`, `cb_status`, and `url` from the response, so it drops `storage_url`. The pipeline uses the SDK for discovery and `httpx` for `store=true` fetches and the Storage API.

## 4. Normal token or JS token

| URL | Mode | Normal | JS |
| --- | --- | --- | --- |
| notion.com/about | generic-extractor `content` chars | 3,057 | 3,092 |
| linear.app/integrations | generic-extractor `content` chars | 209 | 209 |
| monday.com/integrations | generic-extractor `content` chars | 2,550 | 2,550 |
| figma.com/about | generic-extractor `content` chars | 1,114 | 1,114 |
| linear.app/integrations | `format=md` chars | 24,218 | 24,218 |
| quotes.toscrape.com/js | `format=md` chars | 42 | 887 |

Modern company sites (Next.js, Astro, and similar) render on the server, so the Normal token returns the same content as the JS token. A page that builds its content in the browser (quotes.toscrape.com/js) returns only the nav link with the Normal token. The pipeline uses the Normal token first and retries with the JS token when the Markdown is under 300 characters. A `use_js` column in the seed CSV forces the JS token per company.

## 5. `md_readability=true` on structured pages

| URL | `md_readability=true` | plain `format=md` |
| --- | --- | --- |
| close.com/about | 469 chars (no leadership grid) | 13,722 chars (all leaders) |
| pipedrive.com/en/about | 504 chars | 11,187 chars |
| close.com/integrations | 260 chars | 41,290 chars |

Readability mode is tuned for articles. On team grids and integration directories it keeps only the intro paragraphs. The fetcher asks for `md_readability=true` first and falls back to plain `format=md` (still with `store=true`) when the result is under 1,500 characters. The `rid` of the version that was used is the one saved as provenance.

Also: `generic-extractor` `content` on linear.app/integrations was 209 characters, while Markdown had 24,218. Markdown, not `content`, feeds the extraction model.

## 6. Failures

One `format=md` call returned HTTP 520 with `cb_status: 0` and the body "Request failed ... Please try the request again, as this one is not charged" (`crawl_failure_520.json`). The same call succeeded on retry. The client retries on HTTP 429, 5xx, 520 to 525, and `cb_status: 0`, with exponential backoff.

## 7. Geo redirects

Crawlbase picks the exit country automatically. On some calls to `https://www.zendesk.com/` the request left from Germany, and Zendesk redirected to `https://www.zendesk.de/#georedirect` (German title, 116 links). The links on that page still pointed at `www.zendesk.com` (`generic_extractor_zendesk_georedirect.json`). Seven later calls (three default, four with `country=US`) all landed on `zendesk.com`.

A same-host filter keyed on the final URL dropped every link in the redirected case. Discovery now filters on the seed homepage's host and only uses the final URL to resolve relative links. The Crawling API `country` parameter can pin the exit country, but the docs say Crawlbase may override it, so the code does not depend on it.

## 8. Environment note

If your shell already has `CRAWLBASE_TOKEN` set, `python-dotenv` will not replace it by default. The project loads `.env` with `override=True`, so the values in `.env` always win.
