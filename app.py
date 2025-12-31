from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.requests import Request
import time
import logging
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import re
from dotenv import load_dotenv
import traceback

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# -------- Environment Variables --------
TECH_PORTAL_DOMAIN = os.getenv("TECH_PORTAL_DOMAIN")
CDN_DOMAIN_PATTERN = os.getenv("CDN_DOMAIN_PATTERN")
ALLOWED_SOURCE_DOMAINS = os.getenv("ALLOWED_SOURCE_DOMAINS").split(",")

# -------- Browser Setup --------
def setup_browser():
    """Setup headless browser for Render"""
    chrome_options = Options()
    
    # Essential options for headless
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    
    # Additional options for stability
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Set user agent
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        # For Render - use ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Hide webdriver
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    except Exception as e:
        logger.error(f"ChromeDriverManager failed: {e}")
        # Fallback
        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            raise Exception(f"Failed to setup browser: {e2}")
    
    # Set reasonable timeouts
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)
    
    return driver

def resolve_google_link(source_url: str) -> str:
    """Follow the chain to get Google download link"""
    logger.info(f"Starting resolution for: {source_url}")
    driver = setup_browser()
    
    try:
        # 1. Start at source URL
        logger.info("Step 1: Accessing source URL")
        driver.get(source_url)
        time.sleep(3)
        
        # 2. Find target portal link
        logger.info("Step 2: Finding portal link")
        links = driver.find_elements(By.TAG_NAME, "a")
        tech_link = None
        
        for link in links:
            href = link.get_attribute("href")
            if href and TECH_PORTAL_DOMAIN in href:
                tech_link = href
                logger.info(f"Found tech link")
                break
        
        if not tech_link:
            raise ValueError("No portal link found")
        
        # 3. Go to portal
        logger.info("Step 3: Accessing portal")
        driver.get(tech_link)
        time.sleep(4)
        
        # 4. Handle any forms
        page_source = driver.page_source
        if 'id="landing"' in page_source:
            try:
                logger.info("Step 4: Handling form")
                driver.execute_script("document.getElementById('landing').submit();")
                time.sleep(3)
            except Exception as e:
                logger.warning(f"Form submission failed: {e}")
        
        # 5. Find token pattern
        logger.info("Step 5: Finding token")
        page_source = driver.page_source
        pepe_pattern = r'pepe-[a-f0-9]{12,}'
        pepe_matches = re.findall(pepe_pattern, page_source, re.IGNORECASE)
        
        if not pepe_matches:
            # Try alternative patterns
            pepe_pattern2 = r'[a-f0-9]{24,}'
            pepe_matches = re.findall(pepe_pattern2, page_source, re.IGNORECASE)
            
        if not pepe_matches:
            raise ValueError("No access token found")
        
        pepe_token = pepe_matches[0]
        logger.info(f"Found token: {pepe_token[:20]}...")
        
        # 6. Follow token link
        logger.info("Step 6: Following token link")
        pepe_url = f"https://{TECH_PORTAL_DOMAIN}/?go={pepe_token}"
        driver.get(pepe_url)
        time.sleep(4)
        
        # 7. Extract CDN link
        logger.info("Step 7: Extracting CDN link")
        page_source = driver.page_source
        cdn_matches = re.findall(CDN_DOMAIN_PATTERN, page_source, re.IGNORECASE)
        
        if not cdn_matches:
            # Try alternative CDN patterns
            cdn_pattern2 = r'cdn[^\s"\']+'
            cdn_matches = re.findall(cdn_pattern2, page_source, re.IGNORECASE)
        
        if not cdn_matches:
            raise ValueError("No distribution link found")
        
        cdn_url = f"https://{cdn_matches[0]}"
        logger.info(f"Found CDN URL")
        
        # 8. Follow CDN link
        logger.info("Step 8: Accessing CDN")
        driver.get(cdn_url)
        time.sleep(4)
        
        # 9. Extract final download link
        logger.info("Step 9: Extracting download link")
        cdn_source = driver.page_source
        
        # Multiple patterns for Google link
        google_patterns = [
            r'(https://video-downloads\.googleusercontent\.com/[^\s"\']+)',
            r'(https://[^\s"\']*googleusercontent[^\s"\']*)',
            r'(https://[^\s"\']*google[^\s"\']*download[^\s"\']*)'
        ]
        
        google_matches = []
        for pattern in google_patterns:
            matches = re.findall(pattern, cdn_source, re.IGNORECASE)
            if matches:
                google_matches = matches
                break
        
        if not google_matches:
            # Try to find any download link
            download_pattern = r'(https://[^\s"\']*\.(mp4|mkv|avi|mov|wmv|flv|webm)[^\s"\']*)'
            google_matches = re.findall(download_pattern, cdn_source, re.IGNORECASE)
            if google_matches:
                google_matches = [google_matches[0][0]]
        
        if not google_matches:
            raise ValueError("No download link found")
        
        google_url = google_matches[0]
        logger.info(f"Successfully resolved to Google URL")
        
        return google_url
        
    except Exception as e:
        logger.error(f"Resolution error: {str(e)[:100]}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise
    finally:
        try:
            driver.quit()
        except:
            pass

# -------- Core Endpoint --------
async def resolve_url(request: Request):
    """
    Resolve an opaque source URL to a temporary Google direct-download URL.
    """
    try:
        data = await request.json()
        source_url = data.get('source_url')
    except Exception as e:
        logger.error(f"JSON parse error: {e}")
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
        logger.warning(f"Unauthorized source domain attempt: {source_url}")
        return JSONResponse({"error": "Invalid source URL"}, status_code=400)
    
    try:
        logger.info(f"Processing request for: {source_url}")
        # Get the direct download link
        direct_download_url = resolve_google_link(source_url)
        
        # Set expiration (5 minutes from now)
        expires_at = int(time.time()) + 300
        
        logger.info(f"Successfully resolved URL, expires at: {expires_at}")
        
        return JSONResponse({
            "direct_download_url": direct_download_url,
            "expires_at": expires_at
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Resolution failed: {error_msg}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Return more helpful error
        return JSONResponse({
            "error": "Failed to resolve source URL",
            "details": error_msg[:100] if len(error_msg) > 100 else error_msg
        }, status_code=500)

async def health_check(request: Request):
    """Health check endpoint"""
    return JSONResponse({
        "status": "healthy", 
        "timestamp": int(time.time()),
        "service": "URL Resolver"
    })

async def root(request: Request):
    """Root endpoint"""
    return JSONResponse({
        "service": "URL Resolver Service",
        "version": "2.0.0",
        "endpoint": "POST /resolve",
        "docs": "Send POST request to /resolve with JSON: {\"source_url\": \"https://...\"}"
    })

# -------- Create App --------
app = Starlette(
    debug=False, 
    routes=[
        Route("/", root),
        Route("/health", health_check),
        Route("/resolve", resolve_url, methods=["POST"]),
    ]
)