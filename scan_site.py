import re
import time
import requests
import trafilatura
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse

def normalise_domain(input_url: str) -> str:
    input_url = input_url.strip()
    if not input_url.startswith(("http://", "https://")):
        input_url = "https://" + input_url
    return input_url.rstrip("/")

def safe_filename(domain: str) -> str:
    parsed = urlparse(domain)
    host = parsed.netloc or parsed.path
    return re.sub(r"[^a-zA-Z0-9.-]+", "-", host).strip("-")

domain = normalise_domain(input("Enter website URL/domain: "))
sitemap_url = domain + "/page-sitemap.xml"

print(f"\nFetching sitemap: {sitemap_url}")

r = requests.get(
    sitemap_url,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=20
)

r.raise_for_status()

root = ET.fromstring(r.text)
ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
urls = [loc.text for loc in root.findall(".//sm:loc", ns) if loc.text]

print(f"Found {len(urls)} URLs\n")

all_content = []
failed_urls = []

for index, url in enumerate(urls, start=1):
    print(f"[{index}/{len(urls)}] Scanning: {url}")

    try:
        downloaded = trafilatura.fetch_url(url)

        if not downloaded:
            print("  Failed to fetch")
            failed_urls.append(url)
            time.sleep(1)
            continue

        content = trafilatura.extract(
            downloaded,
            url=url,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
            include_links=True,
            include_images=False,
            include_formatting=True,
            favor_precision=True,
            deduplicate=True,
        )

        if content:
            all_content.append(f"# Source URL: {url}\n\n{content}")
        else:
            print("  No extractable content")
            failed_urls.append(url)

    except Exception as e:
        print(f"  Error: {e}")
        failed_urls.append(url)

    time.sleep(1)

timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
filename = f"{safe_filename(domain)}-chatbot-training-{timestamp}.txt"

combined = "\n\n---\n\n".join(all_content)

if failed_urls:
    combined += "\n\n---\n\n# Failed URLs\n\n"
    combined += "\n".join(failed_urls)

with open(filename, "w", encoding="utf-8") as f:
    f.write(combined)

print("\nDone.")
print(f"Saved file: {filename}")
print(f"Pages extracted: {len(all_content)}")
print(f"Pages failed/empty: {len(failed_urls)}")
