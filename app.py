from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="URL Resolver Service")

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
    
    try:
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        logger.error(f"Failed to install ChromeDriver: {e}")
        driver = webdriver.Chrome(options=chrome_options)
    
    return driver

def resolve_google_link(source_url: str) -> str:
    """Follow the chain to get Google download link"""
    logger.info(f"Starting resolution for: {source_url}")
    driver = setup_browser()
    
    try:
        # 1. Start at modpro.blog
        logger.info("Step 1: Accessing modpro.blog")
        driver.get(source_url)
        time.sleep(2)
        
        # 2. Find and click tech.unblockedgames.world link
        logger.info("Step 2: Finding tech.unblockedgames.world link")
        links = driver.find_elements(By.TAG_NAME, "a")
        tech_link = None
        
        for link in links:
            href = link.get_attribute("href")
            if href and "tech.unblockedgames.world" in href:
                tech_link = href
                logger.info(f"Found tech link: {tech_link}")
                break
        
        if not tech_link:
            raise ValueError("No tech.unblockedgames.world link found")
        
        # 3. Go to tech portal
        logger.info("Step 3: Accessing tech portal")
        driver.get(tech_link)
        time.sleep(3)
        
        # 4. Find and submit verification form
        page_source = driver.page_source
        if 'id="landing"' in page_source:
            try:
                logger.info("Step 4: Submitting verification form")
                driver.execute_script("document.getElementById('landing').submit();")
                time.sleep(3)
            except Exception as e:
                logger.warning(f"Could not submit form: {e}")
        
        # 5. Find pepe- link
        logger.info("Step 5: Finding pepe- token")
        page_source = driver.page_source
        pepe_pattern = r'pepe-[a-f0-9]{12,}'
        pepe_matches = re.findall(pepe_pattern, page_source, re.IGNORECASE)
        
        if not pepe_matches:
            raise ValueError("No pepe- token found")
        
        pepe_token = pepe_matches[0]
        logger.info(f"Found pepe token: {pepe_token}")
        
        # 6. Follow pepe- link (to driveseed)
        logger.info("Step 6: Following pepe- link")
        pepe_url = f"https://tech.unblockedgames.world/?go={pepe_token}"
        driver.get(pepe_url)
        time.sleep(3)
        
        # 7. Extract CDN link from driveseed page
        logger.info("Step 7: Extracting CDN link")
        page_source = driver.page_source
        cdn_pattern = r'(cdn\.video-leech\.pro/[a-f0-9:]+)'
        cdn_matches = re.findall(cdn_pattern, page_source, re.IGNORECASE)
        
        if not cdn_matches:
            raise ValueError("No CDN link found")
        
        cdn_url = f"https://{cdn_matches[0]}"
        logger.info(f"Found CDN URL: {cdn_url}")
        
        # 8. Follow CDN link
        logger.info("Step 8: Accessing CDN")
        driver.get(cdn_url)
        time.sleep(3)
        
        # 9. Extract Google download link from CDN page
        logger.info("Step 9: Extracting Google download link")
        cdn_source = driver.page_source
        
        google_pattern = r'(https://video-downloads\.googleusercontent\.com/[^\s"\']+)'
        google_matches = re.findall(google_pattern, cdn_source, re.IGNORECASE)
        
        if not google_matches:
            raise ValueError("No Google download link found")
        
        google_url = google_matches[0]
        logger.info(f"Successfully resolved to: {google_url[:50]}...")
        
        return google_url
        
    except Exception as e:
        logger.error(f"Error during chain resolution: {e}")
        raise
    finally:
        driver.quit()

# -------- Core Endpoint --------
@app.post("/resolve", response_model=ResolveResponse)
async def resolve_url(payload: ResolveRequest):
    """
    Resolve an opaque source URL to a temporary Google direct-download URL.
    
    Example request:
    {
        "source_url": "https://links.modpro.blog/archives/146649"
    }
    """
    source_url = payload.source_url
    
    if not source_url:
        raise HTTPException(status_code=400, detail="source_url is required")
    
    if not source_url.startswith("https://links.modpro.blog"):
        logger.warning(f"Unexpected source URL pattern: {source_url}")
    
    try:
        # Use your Selenium resolver to get the actual Google link
        direct_download_url = resolve_google_link(source_url)
        
        # Set expiration (5 minutes from now)
        expires_at = int(time.time()) + 300
        
        logger.info(f"Successfully resolved {source_url} -> {direct_download_url[:50]}...")
        
        return ResolveResponse(
            direct_download_url=direct_download_url,
            expires_at=expires_at
        )
        
    except Exception as e:
        logger.error(f"Failed to resolve URL {source_url}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resolve source URL: {str(e)}"
        )

# -------- Health Check --------
@app.get("/health")
async def health_check():
    """Health check endpoint for Render"""
    return {"status": "healthy", "timestamp": int(time.time())}

@app.get("/")
async def root():
    """Root endpoint with service info"""
    return {
        "service": "URL Resolver Service",
        "version": "1.0.0",
        "endpoint": "POST /resolve",
        "description": "Resolves opaque URLs to Google direct-download links"
    }