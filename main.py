from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time
import logging
import os
import re
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import asyncio
import sys

# ---------------- WINDOWS FIX ----------------
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("resolver")

# ---------------- APP ----------------
app = FastAPI(title="URL Resolver Service")

# ---------------- ENV ----------------
TECH_PORTAL_DOMAIN = os.getenv("TECH_PORTAL_DOMAIN")
CDN_DOMAIN_PATTERN = os.getenv("CDN_DOMAIN_PATTERN")
ALLOWED_SOURCE_DOMAINS = os.getenv("ALLOWED_SOURCE_DOMAINS", "").split(",")

# ---------------- SCHEMAS ----------------
class ResolveRequest(BaseModel):
    source_url: str

class ResolveResponse(BaseModel):
    direct_download_url: str
    expires_at: int

# ---------------- RESOLVER ----------------
async def resolve_google_link(source_url: str) -> str:
    logger.info("STEP 0: Starting Playwright async resolution")
    logger.info(f"Source URL: {source_url}")

    async with async_playwright() as p:
        logger.info("STEP 0.1: Launching Chromium")

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            viewport={"width": 1920, "height": 1080}
        )

        page = await context.new_page()

        try:
            # 1️⃣ Open source page
            logger.info("STEP 1: Opening source page")
            await page.goto(source_url, timeout=30_000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # 2️⃣ Find portal link
            logger.info("STEP 2: Searching for portal link")
            anchors = await page.query_selector_all("a[href]")

            tech_link = None
            for a in anchors:
                href = await a.get_attribute("href")
                if href and TECH_PORTAL_DOMAIN in href:
                    tech_link = href
                    break

            if not tech_link:
                logger.error("STEP 2 FAILED: Portal link not found")
                raise ValueError("No portal link found")

            logger.info(f"STEP 2 SUCCESS: Found portal link → {tech_link}")

            # 3️⃣ Open portal
            logger.info("STEP 3: Opening portal page")
            await page.goto(tech_link, timeout=30_000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # 4️⃣ Handle form auto-submit
            logger.info("STEP 4: Checking for landing form")
            landing = await page.query_selector("#landing")
            if landing:
                logger.info("STEP 4: Submitting landing form")
                await page.evaluate("document.getElementById('landing').submit()")
                await page.wait_for_timeout(3000)
            else:
                logger.info("STEP 4: No landing form found")

            # 5️⃣ Extract token
            logger.info("STEP 5: Extracting access token")
            html = await page.content()

            pepe_match = re.search(r'pepe-[a-f0-9]{12,}', html, re.IGNORECASE)
            if not pepe_match:
                logger.error("STEP 5 FAILED: No access token found")
                raise ValueError("No access token found")

            pepe_token = pepe_match.group(0)
            logger.info(f"STEP 5 SUCCESS: Token → {pepe_token[:20]}...")

            # 6️⃣ Follow token URL
            pepe_url = f"https://{TECH_PORTAL_DOMAIN}/?go={pepe_token}"
            logger.info(f"STEP 6: Opening token URL → {pepe_url}")

            await page.goto(pepe_url, timeout=30_000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # 7️⃣ Extract CDN link
            logger.info("STEP 7: Extracting CDN link")
            html = await page.content()

            cdn_match = re.search(CDN_DOMAIN_PATTERN, html, re.IGNORECASE)
            if not cdn_match:
                logger.error("STEP 7 FAILED: CDN link not found")
                raise ValueError("No distribution link found")

            cdn_url = f"https://{cdn_match.group(0)}"
            logger.info(f"STEP 7 SUCCESS: CDN URL → {cdn_url}")

            # 8️⃣ Open CDN page
            logger.info("STEP 8: Opening CDN page")
            await page.goto(cdn_url, timeout=30_000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # 9️⃣ Extract Google download link
            logger.info("STEP 9: Extracting Google download link")
            html = await page.content()

            google_match = re.search(
                r'(https://video-downloads\.googleusercontent\.com/[^\s"\']+)',
                html,
                re.IGNORECASE
            )

            if not google_match:
                logger.error("STEP 9 FAILED: Google download link not found")
                raise ValueError("No Google download link found")

            final_url = google_match.group(1)
            logger.info(f"STEP 9 SUCCESS: Final URL extracted (len={len(final_url)})")

            return final_url

        except PlaywrightTimeout:
            logger.error("TIMEOUT: Playwright navigation timed out")
            raise

        except Exception as e:
            logger.exception(f"RESOLUTION ERROR: {e}")
            raise

        finally:
            logger.info("CLEANUP: Closing browser")
            await context.close()
            await browser.close()

# ---------------- API ----------------
@app.post("/resolve", response_model=ResolveResponse)
async def resolve_url(payload: ResolveRequest):
    source_url = payload.source_url

    logger.info("API CALL: /resolve")

    if not source_url:
        raise HTTPException(status_code=400, detail="source_url is required")

    if not any(domain in source_url for domain in ALLOWED_SOURCE_DOMAINS):
        logger.warning("Blocked source domain")
        raise HTTPException(status_code=400, detail="Invalid source URL")

    try:
        url = await resolve_google_link(source_url)
        return ResolveResponse(
            direct_download_url=url,
            expires_at=int(time.time()) + 300
        )

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to resolve source URL")

# ---------------- HEALTH ----------------
@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": int(time.time())}

@app.get("/")
async def root():
    return {
        "service": "URL Resolver Service",
        "engine": "playwright-async",
        "logging": "step-by-step"
    }
