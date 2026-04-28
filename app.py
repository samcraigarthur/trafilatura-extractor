from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, StreamingResponse
import trafilatura
import requests
import xml.etree.ElementTree as ET
import asyncio
import json
import re
from datetime import datetime
from urllib.parse import urlparse

app = FastAPI()


def normalise_domain(input_url: str) -> str:
    input_url = input_url.strip()
    if not input_url.startswith(("http://", "https://")):
        input_url = "https://" + input_url
    return input_url.rstrip("/")


def safe_filename(domain: str) -> str:
    parsed = urlparse(domain)
    host = parsed.netloc or parsed.path
    return re.sub(r"[^a-zA-Z0-9.-]+", "-", host).strip("-")


def fetch_sitemap(domain: str) -> list:
    sitemap_url = domain + "/page-sitemap.xml"
    r = requests.get(
        sitemap_url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    r.raise_for_status()
    root = ET.fromstring(r.text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text for loc in root.findall(".//sm:loc", ns) if loc.text]


def extract_page(url: str):
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None
    return trafilatura.extract(
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


@app.get("/", response_class=HTMLResponse)
async def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/extract")
def extract(url: str = Query(...)):
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return {"ok": False, "error": "Could not fetch URL"}
    content = trafilatura.extract(
        downloaded,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        include_links=True,
        include_images=False,
        include_formatting=True,
        favor_recall=True,
        favor_precision=False,
        deduplicate=True,
        with_metadata=True,
    )
    return {"ok": bool(content), "url": url, "content": content or ""}


@app.get("/scan")
async def scan(url: str = Query(...)):
    async def event_stream():
        try:
            domain = normalise_domain(url)

            try:
                urls = await asyncio.to_thread(fetch_sitemap, domain)
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Could not fetch sitemap: {e}'})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'found', 'total': len(urls)})}\n\n"

            all_content = []
            failed_urls = []

            for index, page_url in enumerate(urls, start=1):
                yield f"data: {json.dumps({'type': 'progress', 'index': index, 'total': len(urls), 'url': page_url})}\n\n"

                try:
                    content = await asyncio.to_thread(extract_page, page_url)
                    if content:
                        all_content.append(f"# Source URL: {page_url}\n\n{content}")
                    else:
                        failed_urls.append(page_url)
                except Exception:
                    failed_urls.append(page_url)

                await asyncio.sleep(1)

            combined = "\n\n---\n\n".join(all_content)
            if failed_urls:
                combined += "\n\n---\n\n# Failed URLs\n\n" + "\n".join(failed_urls)

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"{safe_filename(domain)}-chatbot-training-{timestamp}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(combined)

            yield f"data: {json.dumps({'type': 'done', 'content': combined, 'filename': filename, 'extracted': len(all_content), 'failed': len(failed_urls)})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
