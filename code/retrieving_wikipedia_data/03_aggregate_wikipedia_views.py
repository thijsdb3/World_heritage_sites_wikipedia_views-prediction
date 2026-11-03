import pandas as pd

wikipedia_articles = pd.read_csv("../data/raw/wikipedia_views.csv")
world_heritage_sites = pd.read_csv("../data/raw/whc001.csv")

# Filter for January 2026
january_2026_wikipedia_views = wikipedia_articles[
    wikipedia_articles["month"] == 202601
].copy()

# Sum pageviews across languages for each UNESCO site
january_2026_wikipedia_views = (
    january_2026_wikipedia_views
    .groupby("ID", as_index=False)["views"]
    .sum()
    .rename(columns={"views": "total_views"})
)

# Merge pageviews into the World Heritage dataset
final_heritage_jan_2026 = world_heritage_sites.merge(
    january_2026_wikipedia_views,
    on="ID",
    how="left"
)

# Save the final dataset
final_heritage_jan_2026.to_csv(
    "../data/processed/final_heritage_jan_2026.csv",
    index=False
)

# Check the results
print(final_heritage_jan_2026.head())
print(f"Total UNESCO sites: {len(final_heritage_jan_2026)}")
print(f"Sites with pageview data: {final_heritage_jan_2026['total_views'].notna().sum()}")
print(f"Sites without pageview data: {final_heritage_jan_2026['total_views'].isna().sum()}")