from fastapi import FastAPI, Query
import trafilatura

app = FastAPI()

@app.get("/")
def home():
    return {"status": "Trafilatura extractor running"}

@app.get("/extract")
def extract(url: str = Query(...)):
    downloaded = trafilatura.fetch_url(url)

    if not downloaded:
        return {
            "ok": False,
            "error": "Could not fetch URL"
        }

    content = trafilatura.extract(
    downloaded,
    url=url,
    output_format="markdown",

    # Content inclusion
    include_comments=False,
    include_tables=True,
    include_links=True,
    include_images=False,
    include_formatting=True,

    # Extraction behaviour
    favor_recall=True,
    favor_precision=False,
    deduplicate=True,

    # Metadata
    with_metadata=True,
)

    return {
        "ok": bool(content),
        "url": url,
        "content": content or ""
    }
