#!/usr/bin/env python3
"""
SAM.gov Scraper — Pulls solicitations and downloads attachments.

Extracted from srt-fbo-scraper/get_opps.py and sam_utils.py.
Same SAM.gov API, same filters, same attachment download logic.
"""

import datetime
import errno
import hashlib
import logging
import os
import re
import shutil
import ssl
import urllib.parse
from pathlib import Path
from typing import List, Optional

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ── NAICS code prefixes that indicate ICT solicitations ───────────────────────
# Same list as srt-fbo-scraper/sam_utils.py
NAICS_ICT_PREFIXES = (
    "334111",  # Electronic computer manufacturing
    "334118",  # Computer terminal and other computer peripheral equipment
    "3343",    # Audio and video equipment
    "33451",   # Navigational, measuring, electromedical instruments
    "334516",  # Analytical laboratory instrument manufacturing
    "334614",  # Software and other prerecorded compact disc, tape, and record reproducing
    "5112",    # Software publishers
    "518",     # Data processing, hosting, and related services
    "54169",   # Other scientific and technical consulting services
    "54121",   # Computer systems design and related services
    "5415",    # Computer systems design and related services
    "61142",   # Computer training
)

# Non-ICT NAICS prefixes to skip entirely (same as srt-fbo-scraper/get_opps.py)
NON_ICT_NAICS_PREFIXES = [
    "23", "111", "112", "113", "114", "115", "212", "213", "221",
    "236", "237", "238", "311", "312", "321", "327", "331", "332",
]

SAM_API_URI = "https://api.sam.gov/opportunities/v2/search"


# ── SSL / Retry session (same as srt-fbo-scraper) ────────────────────────────

class SAMHttpAdapter(HTTPAdapter):
    """Transport adapter with custom SSL context for SAM.gov API."""
    def __init__(self, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = PoolManager(
            num_pools=connections, maxsize=maxsize,
            block=block, ssl_context=self.ssl_context)


def _retry_session(retries=3, backoff=0.3):
    session = requests.Session()
    retry = Retry(total=retries, read=retries, connect=retries,
                  backoff_factor=backoff, status_forcelist=(500, 502, 503, 504))
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.options |= 0x4  # Workaround for legacy SSL renegotiation
    adapter = SAMHttpAdapter(ctx, max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# ── SAM.gov API ───────────────────────────────────────────────────────────────

def _format_date(d):
    """Format a date for SAM.gov API (MM/DD/YYYY)."""
    if isinstance(d, str) and d == "yesterday":
        d = datetime.date.today() - datetime.timedelta(days=1)
    elif isinstance(d, str):
        d = datetime.datetime.strptime(d, "%Y-%m-%d").date()
    return d.strftime("%m/%d/%Y")


def fetch_opportunities(
    api_key: str,
    from_date="yesterday",
    to_date="yesterday",
    sol_types="o,k",
    limit: Optional[int] = None,
) -> List[dict]:
    """
    Fetch solicitations from SAM.gov API.

    Args:
        api_key: SAM.gov API key
        from_date: Start date ("yesterday" or "YYYY-MM-DD")
        to_date: End date ("yesterday" or "YYYY-MM-DD")
        sol_types: Solicitation types (o=solicitation, k=combined synopsis/solicitation)
        limit: Max opportunities to return (None = all)

    Returns:
        List of opportunity dicts from SAM.gov
    """
    base_uri = os.getenv("SAM_API_URI", SAM_API_URI)
    params = {
        "api_key": api_key,
        "limit": 500,
        "postedFrom": _format_date(from_date),
        "postedTo": _format_date(to_date),
        "ptype": sol_types,
    }
    url = f"{base_uri}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

    logger.info(f"[SAM] Fetching opportunities: {_format_date(from_date)} to {_format_date(to_date)}")

    session = _retry_session()
    opps = []
    offset = 0
    total = 999999

    while offset < total and (not limit or len(opps) < limit):
        r = session.get(f"{url}&offset={offset}", timeout=100)
        data = r.json()

        if r.status_code != 200:
            err = data.get("error", {}).get("message", r.text[:200])
            raise RuntimeError(f"SAM.gov API error: {err}")

        total = data.get("totalRecords", 0)
        batch = data.get("opportunitiesData", [])
        offset += len(batch)

        # Filter to ICT-relevant NAICS codes (same logic as old scraper)
        for opp in batch:
            naics = opp.get("naicsCode", "")

            # Skip known non-ICT
            if naics and any(naics.startswith(p) for p in NON_ICT_NAICS_PREFIXES):
                continue

            # Accept if NAICS matches ICT prefixes
            naics_match = any(naics.startswith(p) for p in NAICS_ICT_PREFIXES)
            if naics_match:
                opps.append(opp)

        logger.info(f"[SAM] Fetched {offset}/{total} total, {len(opps)} ICT matches so far")

    session.close()

    if limit and len(opps) > limit:
        opps = opps[:limit]

    logger.info(f"[SAM] Done: {len(opps)} ICT solicitations found")
    return opps


# ── Attachment download ───────────────────────────────────────────────────────

def download_attachments(opp: dict, out_dir: str) -> List[str]:
    """
    Download all attachments for a solicitation into a per-solicitation folder.

    Args:
        opp: SAM.gov opportunity dict (must have solicitationNumber and resourceLinks)
        out_dir: Base attachments directory

    Returns:
        List of downloaded file paths
    """
    sol_num = opp.get("solicitationNumber", "unknown")
    resource_links = opp.get("resourceLinks") or []

    if not resource_links:
        logger.info(f"[SAM] {sol_num}: no attachments")
        return []

    sol_dir = os.path.join(out_dir, f"{sol_num}_attachments")
    os.makedirs(sol_dir, exist_ok=True)

    http = urllib3.PoolManager()
    downloaded = []

    for file_url in resource_links:
        try:
            # Use SHA1 hash as temp filename (same as old scraper)
            temp_name = os.path.join(sol_dir, hashlib.sha1(file_url.encode("utf-8")).hexdigest())

            r = http.request("GET", file_url, preload_content=False)
            if r is None:
                continue

            # Try beta.sam.gov → sam.gov fallback
            if r.status != 200 and "beta.sam.gov" in file_url:
                new_url = file_url.replace("beta.sam.gov", "sam.gov")
                logger.info(f"[SAM] Retrying: {new_url}")
                r = http.request("GET", new_url, preload_content=False)

            if "Content-Disposition" not in r.headers:
                logger.warning(f"[SAM] No Content-Disposition for {file_url[:80]}")
                continue

            with open(temp_name, "wb") as f:
                shutil.copyfileobj(r, f)

            # Rename to real filename from Content-Disposition header
            cd = r.headers["Content-Disposition"]
            match = re.search(r"filename=(.*)", cd)
            if match:
                real_name = urllib.parse.unquote(match.group(1)).replace("+", " ").strip()
                real_path = os.path.join(sol_dir, real_name)
                try:
                    os.rename(temp_name, real_path)
                except OSError as e:
                    if e.errno == errno.ENAMETOOLONG:
                        # Truncate filename but keep extension
                        ext = Path(real_name).suffix
                        real_path = os.path.join(sol_dir, real_name[:100] + ext)
                        os.rename(temp_name, real_path)
                    else:
                        raise
                downloaded.append(real_path)
                logger.info(f"[SAM] Downloaded: {real_name}")
            else:
                downloaded.append(temp_name)

        except Exception as e:
            logger.error(f"[SAM] Download error for {file_url[:80]}: {e}")

    http.clear()
    logger.info(f"[SAM] {sol_num}: {len(downloaded)} files downloaded")
    return downloaded


# ── Full scrape pipeline ──────────────────────────────────────────────────────

def scrape_sam(
    api_key: str,
    attachments_dir: str,
    from_date="yesterday",
    to_date="yesterday",
    limit: Optional[int] = None,
) -> List[dict]:
    """
    Full scrape: fetch opportunities from SAM.gov and download their attachments.

    Args:
        api_key: SAM.gov API key
        attachments_dir: Directory to store per-solicitation attachment folders
        from_date: Start date
        to_date: End date
        limit: Max solicitations to process

    Returns:
        List of opportunity dicts with 'attachment_folder' and 'downloaded_files' added
    """
    os.makedirs(attachments_dir, exist_ok=True)

    opps = fetch_opportunities(api_key, from_date, to_date, limit=limit)
    logger.info(f"[SAM] Downloading attachments for {len(opps)} solicitations...")

    results = []
    for i, opp in enumerate(opps):
        sol_num = opp.get("solicitationNumber", "unknown")
        logger.info(f"[SAM] [{i+1}/{len(opps)}] {sol_num}")

        files = download_attachments(opp, attachments_dir)
        opp["attachment_folder"] = os.path.join(attachments_dir, f"{sol_num}_attachments")
        opp["downloaded_files"] = files

        # Extract metadata we'll need later
        hierarchy = opp.get("fullParentPathName", "").split(".")
        opp["agency"] = hierarchy[0] if hierarchy else ""
        opp["office"] = hierarchy[1] if len(hierarchy) > 1 else ""

        results.append(opp)

    with_files = sum(1 for o in results if o["downloaded_files"])
    logger.info(f"[SAM] Scrape complete: {len(results)} solicitations, "
                f"{with_files} with attachments, "
                f"{sum(len(o['downloaded_files']) for o in results)} total files")

    return results


def scrape_sam_streaming(
    api_key: str,
    attachments_dir: str,
    from_date="yesterday",
    to_date="yesterday",
    limit: Optional[int] = None,
):
    """
    Generator that yields one solicitation at a time.
    Downloads attachments for each solicitation, yields it, then the caller
    can process and delete before the next one is downloaded.

    Yields:
        dict with opportunity data + 'attachment_folder' and 'downloaded_files'
    """
    os.makedirs(attachments_dir, exist_ok=True)

    opps = fetch_opportunities(api_key, from_date, to_date, limit=limit)
    logger.info(f"[SAM] Streaming {len(opps)} solicitations one at a time...")

    for i, opp in enumerate(opps):
        sol_num = opp.get("solicitationNumber", "unknown")
        logger.info(f"[SAM] [{i+1}/{len(opps)}] Downloading: {sol_num}")

        files = download_attachments(opp, attachments_dir)
        opp["attachment_folder"] = os.path.join(attachments_dir, f"{sol_num}_attachments")
        opp["downloaded_files"] = files

        hierarchy = opp.get("fullParentPathName", "").split(".")
        opp["agency"] = hierarchy[0] if hierarchy else ""
        opp["office"] = hierarchy[1] if len(hierarchy) > 1 else ""
        opp["_index"] = i + 1
        opp["_total"] = len(opps)

        yield opp
