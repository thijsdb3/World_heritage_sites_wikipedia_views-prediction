
import time
from urllib.parse import unquote, urlparse

import pandas as pd
import requests



INPUT_PATH = "../../data/raw/whc001.csv"
OUTPUT_PATH = "../../data/raw/wikipedia_articles.csv"

WIKIDATA_URL = "https://query.wikidata.org/sparql"

BATCH_SIZE = 100
BATCH_DELAY = 2
MAX_RETRIES = 8

LANGUAGES = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "ar": "Arabic",
    "zh": "Chinese",
    "ru": "Russian",
}

session = requests.Session()
session.headers.update({
    "User-Agent": "UNESCOResearch/1.0 (educational data science project)",
    "Accept": "application/sparql-results+json",
})


def query_wikidata(query):
    """Query Wikidata with retries for temporary errors."""

    for attempt in range(MAX_RETRIES):
        try:
            response = session.post(
                WIKIDATA_URL,
                data={"query": query},
                timeout=120,
            )

            if response.status_code == 429 or response.status_code >= 500:
                if attempt == MAX_RETRIES - 1:
                    response.raise_for_status()

                retry_after = response.headers.get("Retry-After")

                try:
                    wait = (
                        max(1, int(retry_after))
                        if retry_after
                        else min(5 * (2 ** attempt), 120)
                    )
                except ValueError:
                    wait = min(5 * (2 ** attempt), 120)

                print(f"HTTP {response.status_code}; retrying in {wait}s")
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response.json()

        except requests.RequestException:
            if attempt == MAX_RETRIES - 1:
                raise

            wait = min(5 * (2 ** attempt), 120)
            print(f"Request failed; retrying in {wait}s")
            time.sleep(wait)


# LOAD UNESCO IDS

sites = pd.read_csv(INPUT_PATH, dtype={"ID": "string"})

site_ids = (
    sites["ID"]
    .dropna()
    .drop_duplicates()
    .tolist()
)

print(f"UNESCO sites to query: {len(site_ids)}")


# FIND WIKIPEDIA ARTICLES

wiki_values = "\n".join(
    f'("{lang}" <https://{lang}.wikipedia.org/>)'
    for lang in LANGUAGES
)

records = []

for start in range(0, len(site_ids), BATCH_SIZE):
    batch = site_ids[start:start + BATCH_SIZE]
    ids = " ".join(f'"{site_id}"' for site_id in batch)

    query = f"""
    SELECT DISTINCT ?siteId ?site ?lang ?article WHERE {{
        VALUES ?siteId {{ {ids} }}
        VALUES (?lang ?wiki) {{ {wiki_values} }}

        ?site wdt:P757 ?siteId .

        ?article schema:about ?site ;
                 schema:isPartOf ?wiki .
    }}
    """

    result = query_wikidata(query)
    bindings = result["results"]["bindings"]

    for item in bindings:
        site_id = item["siteId"]["value"]
        lang = item["lang"]["value"]
        article_url = item["article"]["value"]

        title = unquote(
            urlparse(article_url).path.split("/wiki/", 1)[-1]
        ).replace("_", " ")

        records.append({
            "ID": site_id,
            "wikidata_id": item["site"]["value"].rstrip("/").split("/")[-1],
            "language": lang,
            "language_name": LANGUAGES[lang],
            "article_title": title,
            "article_url": article_url,
        })

    checked = min(start + len(batch), len(site_ids))
    print(f"Wikidata: {checked}/{len(site_ids)} UNESCO IDs checked")

    time.sleep(BATCH_DELAY)


# SAVE RESULTS

columns = [
    "ID", "wikidata_id", "language",
    "language_name", "article_title", "article_url",
]

articles = pd.DataFrame(records, columns=columns)

articles = articles.drop_duplicates(
    subset=["ID", "language", "article_url"]
)

articles.to_csv(OUTPUT_PATH, index=False)

print(f"\nArticle mappings found: {len(articles)}")
print(f"Unique UNESCO sites matched: {articles['ID'].nunique()}")

print("\nUnique sites per language:")
print(articles.groupby("language_name")["ID"].nunique())

print(f"\nSaved to: {OUTPUT_PATH}")
