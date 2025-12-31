from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time
import logging
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from dotenv import load_dotenv
import re

load_dotenv()

# Configure logging (only show errors)
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = FastAPI(title="URL Resolver Service")

# -------- Environment Variables --------
# Load from environment or use defaults
# Set these in Render dashboard or .env file locally
TECH_PORTAL_DOMAIN = os.getenv("TECH_PORTAL_DOMAIN")
CDN_DOMAIN_PATTERN = os.getenv("CDN_DOMAIN_PATTERN")
ALLOWED_SOURCE_DOMAINS = os.getenv("ALLOWED_SOURCE_DOMAINS").split(",")

# -------- Request / Response Schemas --------
class ResolveRequest(BaseModel):
    source_url: str

class ResolveResponse(BaseModel):
    direct_download_url: str
    expires_at: int

# -------- Helper Functions --------
def setup_browser():
    """Setup headless browser"""
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    # Additional stealth options
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    try:
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Execute stealth script
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception as e:
        logger.error(f"Browser setup error: {e}")
        driver = webdriver.Chrome(options=chrome_options)
    
    return driver

def resolve_google_link(source_url: str) -> str:
    """Follow the chain to get Google download link"""
    logger.info(f"Starting resolution")
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
@app.post("/resolve", response_model=ResolveResponse)
async def resolve_url(payload: ResolveRequest):
    """
    Resolve an opaque source URL to a temporary Google direct-download URL.
    """
    source_url = payload.source_url
    
    if not source_url:
        raise HTTPException(status_code=400, detail="source_url is required")
    
    # Check if source URL is allowed
    allowed = False
    for domain in ALLOWED_SOURCE_DOMAINS:
        if domain in source_url:
            allowed = True
            break
    
    if not allowed:
        logger.warning(f"Unauthorized source domain")
        raise HTTPException(status_code=400, detail="Invalid source URL")
    
    try:
        # Get the direct download link
        direct_download_url = resolve_google_link(source_url)
        
        # Set expiration (5 minutes from now)
        expires_at = int(time.time()) + 300
        
        return ResolveResponse(
            direct_download_url=direct_download_url,
            expires_at=expires_at
        )
        
    except Exception as e:
        logger.error(f"Resolution failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to resolve source URL"
        )

# -------- Health Check --------
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": int(time.time())}

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "URL Resolver Service",
        "version": "2.0.0",
        "endpoint": "POST /resolve"
    }