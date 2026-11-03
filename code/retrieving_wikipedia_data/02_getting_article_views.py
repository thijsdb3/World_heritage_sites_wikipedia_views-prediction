
import time
from urllib.parse import quote

import pandas as pd
import requests



ARTICLES_PATH = "../../data/raw/wikipedia_articles.csv"
VIEWS_PATH = "../../data/raw/wikipedia_views.csv"

# Separate cache files for unique article requests
CACHE_PATH = "../../data/raw/wikipedia_unique_article_views.csv"
PROGRESS_PATH = "../../data/raw/wikipedia_unique_article_progress.csv"

START_DATE = "2016010100"
END_DATE = "2026020100"

API_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
)

PAGEVIEW_DELAY = 2
RETRY_BASE_DELAY = 5
MAX_RETRY_DELAY = 120
MAX_RETRIES = 8
BATCH_SAVE = 20

session = requests.Session()
session.headers.update({
    "User-Agent": "UNESCOResearch/1.0 (educational data science project)"
})


def get_pageviews(url):
    """Download pageviews, retrying temporary failures."""

    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, timeout=120)

        except requests.RequestException as exc:
            if attempt == MAX_RETRIES - 1:
                raise

            wait = min(
                RETRY_BASE_DELAY * (2 ** attempt),
                MAX_RETRY_DELAY,
            )
            print(f"Connection error; retrying in {wait}s: {exc}")
            time.sleep(wait)
            continue

        if response.status_code == 404:
            return None

        if response.status_code == 429 or response.status_code >= 500:
            if attempt == MAX_RETRIES - 1:
                response.raise_for_status()

            retry_after = response.headers.get("Retry-After")

            try:
                wait = (
                    max(1, int(retry_after))
                    if retry_after
                    else min(
                        RETRY_BASE_DELAY * (2 ** attempt),
                        MAX_RETRY_DELAY,
                    )
                )
            except ValueError:
                wait = min(
                    RETRY_BASE_DELAY * (2 ** attempt),
                    MAX_RETRY_DELAY,
                )

            print(f"HTTP {response.status_code}; retrying in {wait}s")
            time.sleep(wait)
            continue

        response.raise_for_status()
        return response

    return None


# LOAD ARTICLE MAPPINGS

articles = pd.read_csv(
    ARTICLES_PATH,
    dtype={"ID": "string"},
)

# One request for each unique language + article URL.
unique_articles = articles.drop_duplicates(
    subset=["language", "article_url"]
).copy()

print(f"Article mappings: {len(articles)}")
print(f"Unique articles to request: {len(unique_articles)}")
print(
    "Potential duplicate requests avoided:",
    len(articles) - len(unique_articles),
)


# LOAD SAVED PROGRESS AND RESULTS

try:
    progress = pd.read_csv(PROGRESS_PATH)
    completed = set(
        zip(progress["language"], progress["article_url"])
    )
except FileNotFoundError:
    completed = set()

try:
    cache = pd.read_csv(CACHE_PATH)
    cache_records = cache.to_dict("records")
except FileNotFoundError:
    cache_records = []

remaining = unique_articles[
    ~unique_articles.apply(
        lambda row: (row["language"], row["article_url"]) in completed,
        axis=1,
    )
].copy()

print(f"Already completed: {len(completed)}")
print(f"Remaining requests: {len(remaining)}")


def save_progress():
    pd.DataFrame(
        cache_records,
        columns=["language", "article_url", "month", "views"],
    ).to_csv(CACHE_PATH, index=False)

    pd.DataFrame(
        list(completed),
        columns=["language", "article_url"],
    ).to_csv(PROGRESS_PATH, index=False)


# DOWNLOAD PAGEVIEWS

processed = 0

for _, row in remaining.iterrows():
    lang = row["language"]
    title = row["article_title"]
    article_url = row["article_url"]

    encoded_title = quote(title.replace(" ", "_"), safe="()")

    url = (
        f"{API_URL}/{lang}.wikipedia.org/all-access/all-agents/"
        f"{encoded_title}/monthly/{START_DATE}/{END_DATE}"
    )

    try:
        response = get_pageviews(url)

        if response is None:
            print(f"No pageview data: [{lang}] {title}")
        else:
            for item in response.json().get("items", []):
                cache_records.append({
                    "language": lang,
                    "article_url": article_url,
                    "month": item["timestamp"][:6],
                    "views": item["views"],
                })

        # A successful response or 404 is considered completed.
        completed.add((lang, article_url))
        processed += 1

    except Exception:
        # Preserve all completed work before stopping on an error.
        save_progress()
        raise

    if processed % BATCH_SAVE == 0:
        save_progress()
        print(
            f"Unique articles completed: "
            f"{len(completed)}/{len(unique_articles)}"
        )

    time.sleep(PAGEVIEW_DELAY)

save_progress()


# EXPAND RESULTS BACK TO UNESCO SITE MAPPINGS

cache = pd.DataFrame(
    cache_records,
    columns=["language", "article_url", "month", "views"],
)

if cache.empty:
    views = pd.DataFrame(
        columns=[
            "ID", "language", "article_title",
            "article_url", "month", "views",
        ]
    )
else:
    views = articles.merge(
        cache,
        on=["language", "article_url"],
        how="inner",
    )

    views = views[
        [
            "ID", "language", "article_title",
            "article_url", "month", "views",
        ]
    ]

views.to_csv(VIEWS_PATH, index=False)

print(f"\nMonthly pageview records: {len(views)}")
print(f"UNESCO sites with pageviews: {views['ID'].nunique()}")

if not views.empty:
    print("\nUnique sites with pageviews per language:")
    print(views.groupby("language")["ID"].nunique())

print(f"\nSaved pageviews to: {VIEWS_PATH}")
