import ipaddress
import logging
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_BYTES = 1_000_000  # 1MB
TIMEOUT = 10
MAX_REDIRECTS = 3
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_CONTENT_TYPES = {"text/html", "text/plain"}

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _PRIVATE_NETS)
    except ValueError:
        return True


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"Scheme '{parsed.scheme}' not allowed. Use http or https.")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: no hostname")
    if hostname.lower() in ("localhost",) or hostname.endswith(".local"):
        raise ValueError("Private hostnames not allowed")
    try:
        ip = socket.gethostbyname(hostname)
        if _is_private(ip):
            raise ValueError(f"Private/internal IP addresses not allowed")
    except socket.gaierror:
        raise ValueError(f"Could not resolve hostname: {hostname}")
    return url


def _extract_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    main = soup.find("main") or soup.find("article") or soup.find("body") or soup
    lines = []
    for elem in main.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = elem.get_text(separator=" ").strip()
        if text:
            lines.append(text)

    return title, "\n".join(lines)


async def fetch_url(url: str) -> dict:
    try:
        validated = _validate_url(url)
    except ValueError as e:
        return {"error": str(e)}

    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            max_redirects=MAX_REDIRECTS,
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", validated, headers={"User-Agent": "BitAgent/1.0"}) as r:
                content_type = r.headers.get("content-type", "").split(";")[0].strip()
                if content_type not in ALLOWED_CONTENT_TYPES:
                    return {"error": f"Content type '{content_type}' not supported"}

                chunks = []
                total = 0
                async for chunk in r.aiter_bytes(chunk_size=4096):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        break
                    chunks.append(chunk)

                raw = b"".join(chunks).decode("utf-8", errors="replace")

        title, text = _extract_text(raw)
        return {
            "url": str(r.url),
            "title": title,
            "text": text,
            "word_count": len(text.split()),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    except httpx.TimeoutException:
        return {"error": "Request timed out"}
    except httpx.TooManyRedirects:
        return {"error": "Too many redirects"}
    except Exception as e:
        logger.error(f"Fetch error for {url}: {e}")
        return {"error": f"Fetch failed: {str(e)}"}


class WebFetchAgent:
    name = "WebFetchAgent"
    description = "Fetch and parse web pages. Returns clean text content."
    price_sats = 25

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "price_sats": self.price_sats,
            "limits": {
                "max_size_bytes": MAX_BYTES,
                "timeout_seconds": TIMEOUT,
                "allowed_schemes": list(ALLOWED_SCHEMES),
            },
        }

    async def fetch(self, url: str) -> dict:
        return await fetch_url(url)
