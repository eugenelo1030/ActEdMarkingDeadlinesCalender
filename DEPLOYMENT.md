# Quick Deployment Guide

## Step 1: Install Dependencies

```bash
pip install ics python-dotenv
```

## Step 2: Create Environment Configuration

```bash
# Copy example environment file
copy .env.example .env

# Edit .env with your settings
notepad .env
```

## Step 3: Start the Server

```bash
# Method 1: Using default settings from .env
python calendar_server.py

# Method 2: With command line arguments
python calendar_server.py --port 8081 --host 0.0.0.0

# Method 3: Import data and start
python calendar_server.py --import deadlines26A.txt --port 8081
```

## Step 4: Test the Server

Open browser and navigate to:
```
http://localhost:8081/
```

You should see the calendar subscription page.

## Step 5: Production Deployment

See `SECURITY.md` for complete Windows Server 2019 deployment instructions including:
- Service account creation
- File permissions
- Windows Service installation
- IIS reverse proxy setup
- Firewall configuration
- Security hardening

## Rate Limiting Configuration

Edit `.env` to adjust rate limits:

```ini
# Allow 100 requests per IP per minute
RATE_LIMIT_ENABLED=true
RATE_LIMIT_MAX_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60
```

For high-traffic scenarios:
- Increase `RATE_LIMIT_MAX_REQUESTS` (e.g., 500)
- Adjust `RATE_LIMIT_WINDOW_SECONDS` (e.g., 300 for 5 minutes)

For testing/development:
- Set `RATE_LIMIT_ENABLED=false`

## Monitoring

Watch for rate-limited requests (HTTP 429) in logs:
```
[2025-10-03 10:15:23] 429 - Rate limit exceeded
```

If you see many 429 errors:
1. Check if it's legitimate traffic or attack
2. Adjust rate limits in `.env`
3. Restart the service

## Troubleshooting

### Database locked error
- Ensure only one instance is running
- Check file permissions

### Port already in use
- Change port in `.env` or use `--port` argument
- Check: `netstat -ano | findstr :8081`

### Calendar not updating
- Verify database has correct data: `python view_database.py`
- Check calendar app refresh settings (usually updates hourly)
