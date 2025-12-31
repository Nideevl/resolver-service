# URL Resolver Service

Resolves opaque source URLs to temporary Google direct-download URLs.

## Deployment on Render

1. **Create a new Web Service** on Render
2. **Connect your GitHub repository**
3. **Configure settings:**
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port 10000`

4. **Important:** Render's free tier has limitations:
   - Service spins down after 15 minutes of inactivity
   - First request after spin-down takes ~30-60 seconds
   - Consider Render's $7/month plan for always-on service

## API Usage

### Resolve Endpoint
```bash
curl -X POST https://your-service.onrender.com/resolve \
  -H "Content-Type: application/json" \
  -d '{"source_url": "https://links.modpro.blog/archives/146649"}'