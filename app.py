from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
from starlette.requests import Request
import time
import logging
import os
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# -------- Environment Variables --------
TECH_PORTAL_DOMAIN = os.getenv("TECH_PORTAL_DOMAIN")
CDN_DOMAIN_PATTERN = os.getenv("CDN_DOMAIN_PATTERN")
ALLOWED_SOURCE_DOMAINS = os.getenv("ALLOWED_SOURCE_DOMAINS").split(",")

# -------- Browser Setup --------
def setup_browser():
    """Setup headless browser"""
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    
    try:
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        logger.error(f"Browser setup error: {e}")
        driver = webdriver.Chrome(options=chrome_options)
    
    return driver

def resolve_google_link(source_url: str) -> str:
    """Follow the chain to get Google download link"""
    driver = setup_browser()
    
    try:
        # 1. Start at source URL
        driver.get(source_url)
        time.sleep(2)
        
        # 2. Find target portal link
        links = driver.find_elements(By.TAG_NAME, "a")
        tech_link = None
        
        for link in links:
            href = link.get_attribute("href")
            if href and TECH_PORTAL_DOMAIN in href:
                tech_link = href
                break
        
        if not tech_link:
            raise ValueError("No portal link found")
        
        # 3. Go to portal
        driver.get(tech_link)
        time.sleep(3)
        
        # 4. Handle any forms
        page_source = driver.page_source
        if 'id="landing"' in page_source:
            try:
                driver.execute_script("document.getElementById('landing').submit();")
                time.sleep(3)
            except:
                pass
        
        # 5. Find token pattern
        page_source = driver.page_source
        pepe_pattern = r'pepe-[a-f0-9]{12,}'
        pepe_matches = re.findall(pepe_pattern, page_source, re.IGNORECASE)
        
        if not pepe_matches:
            raise ValueError("No access token found")
        
        pepe_token = pepe_matches[0]
        
        # 6. Follow token link
        pepe_url = f"https://{TECH_PORTAL_DOMAIN}/?go={pepe_token}"
        driver.get(pepe_url)
        time.sleep(3)
        
        # 7. Extract CDN link
        page_source = driver.page_source
        cdn_matches = re.findall(CDN_DOMAIN_PATTERN, page_source, re.IGNORECASE)
        
        if not cdn_matches:
            raise ValueError("No distribution link found")
        
        cdn_url = f"https://{cdn_matches[0]}"
        
        # 8. Follow CDN link
        driver.get(cdn_url)
        time.sleep(3)
        
        # 9. Extract final download link
        cdn_source = driver.page_source
        google_pattern = r'(https://video-downloads\.googleusercontent\.com/[^\s"\']+)'
        google_matches = re.findall(google_pattern, cdn_source, re.IGNORECASE)
        
        if not google_matches:
            raise ValueError("No download link found")
        
        return google_matches[0]
        
    except Exception as e:
        logger.error(f"Resolution error: {e}")
        raise
    finally:
        driver.quit()

# -------- Core Endpoint --------
async def resolve_url(request: Request):
    """
    Resolve an opaque source URL to a temporary Google direct-download URL.
    """
    try:
        data = await request.json()
        source_url = data.get('source_url')
    except:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    
    if not source_url:
        return JSONResponse({"error": "source_url is required"}, status_code=400)
    
    # Check if source URL is allowed
    allowed = False
    for domain in ALLOWED_SOURCE_DOMAINS:
        if domain in source_url:
            allowed = True
            break
    
    if not allowed:
        return JSONResponse({"error": "Invalid source URL"}, status_code=400)
    
    try:
        # Get the direct download link
        direct_download_url = resolve_google_link(source_url)
        
        # Set expiration (5 minutes from now)
        expires_at = int(time.time()) + 300
        
        return JSONResponse({
            "direct_download_url": direct_download_url,
            "expires_at": expires_at
        })
        
    except Exception as e:
        logger.error(f"Resolution failed: {e}")
        return JSONResponse({"error": "Failed to resolve source URL"}, status_code=500)

async def health_check(request: Request):
    return JSONResponse({"status": "healthy", "timestamp": int(time.time())})

async def root(request: Request):
    return JSONResponse({
        "service": "URL Resolver Service",
        "version": "2.0.0",
        "endpoint": "POST /resolve"
    })

# -------- Create App --------
app = Starlette(debug=False, routes=[
    Route("/", root),
    Route("/health", health_check),
    Route("/resolve", resolve_url, methods=["POST"]),
])