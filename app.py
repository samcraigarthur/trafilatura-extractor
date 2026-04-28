from fastapi import FastAPI, Query, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import trafilatura
import requests
import xml.etree.ElementTree as ET
import asyncio
import json
import re
import ipaddress
import socket
import os
from datetime import datetime
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")

app = FastAPI(docs_url=None, redoc_url=None)  # disable public API docs

# scan_id -> asyncio.Event; set the event to cancel that scan
_active_scans: dict[str, asyncio.Event] = {}


# ── Auth ────────────────────────────────────────────────────────────────────

def verify_token(request: Request):
    """If AUTH_TOKEN is set in .env, every request must supply it as
    ?token=... or Authorization: Bearer <token>."""
    if not AUTH_TOKEN:
        return  # auth disabled — open access
    supplied = request.query_params.get("token") or ""
    if not supplied:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            supplied = auth_header[7:]
    if supplied != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorised")


# ── SSRF protection ─────────────────────────────────────────────────────────

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # GCP/AWS metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _PRIVATE_NETS)
    except ValueError:
        return True  # unparseable — block it

def assert_safe_url(url: str):
    """Raise ValueError if the URL targets a private/internal address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are allowed.")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("Invalid URL — no host.")
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        raise ValueError(f"Could not resolve host: {host}")
    if _is_private(ip):
        raise ValueError("Requests to private/internal addresses are not allowed.")


# ── Helpers ──────────────────────────────────────────────────────────────────

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
async def home(_: None = Depends(verify_token)):
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/extract")
def extract(url: str = Query(...), _: None = Depends(verify_token)):
    try:
        assert_safe_url(url)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
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
async def scan(url: str = Query(...), scan_id: str = Query(...), _: None = Depends(verify_token)):
    cancel_event = asyncio.Event()
    _active_scans[scan_id] = cancel_event

    async def event_stream():
        try:
            domain = normalise_domain(url)

            try:
                assert_safe_url(domain)
            except ValueError as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                return

            try:
                urls = await asyncio.to_thread(fetch_sitemap, domain)
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Could not fetch sitemap: {e}'})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'found', 'total': len(urls)})}\n\n"

            all_content = []
            failed_urls = []

            for index, page_url in enumerate(urls, start=1):
                if cancel_event.is_set():
                    yield f"data: {json.dumps({'type': 'cancelled', 'extracted': len(all_content), 'failed': len(failed_urls)})}\n\n"
                    return

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
        finally:
            _active_scans.pop(scan_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/cancel/{scan_id}")
async def cancel(scan_id: str, _: None = Depends(verify_token)):
    event = _active_scans.get(scan_id)
    if event:
        event.set()
        return {"cancelled": True}
    return {"cancelled": False}
