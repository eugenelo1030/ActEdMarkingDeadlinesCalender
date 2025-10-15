# Security Configuration for Windows Server 2019

## Overview
This document provides Windows-specific security configuration for deploying the calendar server on Windows Server 2019 Datacenter.

## Prerequisites
- Windows Server 2019 Datacenter
- Python 3.8+ installed
- HTTPS/TLS configured on your web server (IIS/reverse proxy)
- Dedicated port for calendar service (default: 8081)

---

## 1. Create Dedicated Service Account

Run PowerShell as Administrator:

```powershell
# Create a dedicated user account for the calendar service
New-LocalUser -Name "CalendarService" -Description "Calendar Server Service Account" -NoPassword
Set-LocalUser -Name "CalendarService" -PasswordNeverExpires $true -UserMayNotChangePassword $true

# Add to Users group (minimal permissions)
Add-LocalGroupMember -Group "Users" -Member "CalendarService"
```

---

## 2. Set File Permissions

```powershell
# Navigate to application directory
cd "C:\Path\To\ActEdMarkingDeadlinesCalender"

# Set ownership to CalendarService account
icacls . /setowner "CalendarService" /T

# Remove inherited permissions and set strict access
icacls . /inheritance:r

# Grant CalendarService full control
icacls . /grant "CalendarService:(OI)(CI)F"

# Grant Administrators full control (for management)
icacls . /grant "Administrators:(OI)(CI)F"

# Deny network access to prevent remote file access
icacls . /deny "Network:(OI)(CI)F"

# Specifically lock down database file
icacls deadlines.db /grant "CalendarService:RW"
icacls deadlines.db /grant "Administrators:F"
icacls deadlines.db /inheritance:r
```

---

## 3. Environment Configuration

Create `.env` file (copy from `.env.example`):

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```ini
# Server settings
CALENDAR_PORT=8081
CALENDAR_HOST=0.0.0.0

# Database path (MUST be within application directory)
DB_PATH=deadlines.db

# Rate limiting - adjust based on expected traffic
RATE_LIMIT_ENABLED=true
RATE_LIMIT_MAX_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60

# Logging
LOG_LEVEL=INFO
```

**Security Note:** The `.env` file should NEVER be committed to version control. Add it to `.gitignore`.

---

## 4. Windows Firewall Configuration

```powershell
# Allow inbound traffic on calendar port (8081) - only from specific IPs if possible
New-NetFirewallRule -DisplayName "Calendar Server" `
    -Direction Inbound `
    -LocalPort 8081 `
    -Protocol TCP `
    -Action Allow `
    -Profile Domain,Private

# Optional: Restrict to specific IP ranges (recommended)
# New-NetFirewallRule -DisplayName "Calendar Server - Internal Only" `
#     -Direction Inbound `
#     -LocalPort 8081 `
#     -Protocol TCP `
#     -Action Allow `
#     -RemoteAddress 192.168.1.0/24,10.0.0.0/8

# Block all other access to this port from outside
New-NetFirewallRule -DisplayName "Calendar Server - Block External" `
    -Direction Inbound `
    -LocalPort 8081 `
    -Protocol TCP `
    -Action Block `
    -Profile Public
```

---

## 5. Create Windows Service

### Option A: Using NSSM (Non-Sucking Service Manager)

Download NSSM from https://nssm.cc/download

```powershell
# Install the service
nssm install CalendarService "C:\Python39\python.exe" "C:\Path\To\ActEdMarkingDeadlinesCalender\calendar_server.py"

# Configure service
nssm set CalendarService AppDirectory "C:\Path\To\ActEdMarkingDeadlinesCalender"
nssm set CalendarService DisplayName "ActEd Calendar Subscription Service"
nssm set CalendarService Description "Provides ICS calendar subscriptions for assignment deadlines"
nssm set CalendarService Start SERVICE_AUTO_START

# Set service to run as CalendarService user
nssm set CalendarService ObjectName ".\CalendarService" "password"

# Configure logging
nssm set CalendarService AppStdout "C:\Path\To\Logs\calendar-stdout.log"
nssm set CalendarService AppStderr "C:\Path\To\Logs\calendar-stderr.log"

# Start the service
nssm start CalendarService
```

### Option B: Using Python Script as Service

Create `calendar_service.py` wrapper (if needed).

---

## 6. IIS Reverse Proxy Configuration (Recommended)

Instead of exposing Python directly, use IIS with URL Rewrite and Application Request Routing:

### Install IIS Modules:
1. URL Rewrite: https://www.iis.net/downloads/microsoft/url-rewrite
2. Application Request Routing: https://www.iis.net/downloads/microsoft/application-request-routing

### Configure IIS:

```xml
<!-- web.config in your IIS site root -->
<configuration>
    <system.webServer>
        <rewrite>
            <rules>
                <rule name="Calendar Proxy" stopProcessing="true">
                    <match url="^calendar/(.*)" />
                    <action type="Rewrite" url="http://localhost:8081/calendar/{R:1}" />
                </rule>
            </rules>
        </rewrite>
    </system.webServer>
</configuration>
```

### Benefits:
- HTTPS termination at IIS level
- Additional security headers
- Better logging
- DDoS protection
- No direct exposure of Python port

---

## 7. Additional Security Hardening

### A. Prevent Directory Traversal
✅ Already implemented in code via `validate_db_path()`

### B. Rate Limiting
✅ Already implemented in code
- Default: 100 requests per IP per minute
- Adjust in `.env` file based on your needs

### C. Security Headers (if using IIS)

Add to IIS HTTP Response Headers:

```xml
<system.webServer>
    <httpProtocol>
        <customHeaders>
            <add name="X-Content-Type-Options" value="nosniff" />
            <add name="X-Frame-Options" value="DENY" />
            <add name="X-XSS-Protection" value="1; mode=block" />
            <add name="Referrer-Policy" value="strict-origin-when-cross-origin" />
            <add name="Content-Security-Policy" value="default-src 'self'" />
        </customHeaders>
    </httpProtocol>
</system.webServer>
```

### D. Database Backups

```powershell
# Create scheduled task for daily backups
$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' `
    -Argument '-Command "Copy-Item C:\Path\To\deadlines.db C:\Backups\deadlines_$(Get-Date -Format yyyyMMdd).db"'

$trigger = New-ScheduledTaskTrigger -Daily -At 2am

Register-ScheduledTask -Action $action -Trigger $trigger `
    -TaskName "Calendar DB Backup" -Description "Daily backup of calendar database"
```

---

## 8. Monitoring and Logging

### Windows Event Log Integration

Create event source:

```powershell
New-EventLog -LogName Application -Source "CalendarService"
```

### Monitor Rate Limiting

Check logs for 429 (Too Many Requests) responses to identify potential attacks.

### Regular Security Checks

```powershell
# Check service status
Get-Service | Where-Object {$_.Name -eq "CalendarService"}

# Check listening ports
Get-NetTCPConnection -LocalPort 8081

# Check firewall rules
Get-NetFirewallRule -DisplayName "*Calendar*"

# Review file permissions
icacls C:\Path\To\ActEdMarkingDeadlinesCalender
```

---

## 9. Deployment Checklist

- [ ] Create dedicated service account (CalendarService)
- [ ] Set restrictive file permissions on application directory
- [ ] Set restrictive permissions on deadlines.db (600 equivalent)
- [ ] Configure `.env` file with appropriate rate limits
- [ ] Add `.env` to `.gitignore`
- [ ] Configure Windows Firewall rules
- [ ] Install application as Windows Service
- [ ] Configure IIS reverse proxy (recommended)
- [ ] Add security headers in IIS
- [ ] Set up automated database backups
- [ ] Configure monitoring/logging
- [ ] Test rate limiting functionality
- [ ] Verify HTTPS/TLS is working correctly
- [ ] Test calendar subscriptions from various clients

---

## 10. Testing Security

### Test Rate Limiting

```powershell
# Install if needed: Install-Module -Name PSWebRequest

# Test from PowerShell
1..150 | ForEach-Object {
    Invoke-WebRequest -Uri "http://localhost:8081/" -UseBasicParsing
    Start-Sleep -Milliseconds 100
}
# Should get 429 errors after 100 requests
```

### Test Path Traversal Protection

```bash
# These should fail with error messages:
python calendar_server.py --db ../../../other-app/data.db
python calendar_server.py --db C:\Windows\System32\config.db
python calendar_server.py --db ../../passwords.txt
```

### Verify File Permissions

```powershell
# Try accessing database as different user - should fail
runas /user:SomeOtherUser "type C:\Path\To\deadlines.db"
```

---

## 11. Incident Response

If you suspect a security breach:

1. **Immediately stop the service:**
   ```powershell
   Stop-Service CalendarService
   ```

2. **Check access logs for suspicious activity**

3. **Review database for unauthorized modifications:**
   ```bash
   python view_database.py
   ```

4. **Check firewall logs:**
   ```powershell
   Get-WinEvent -FilterHashtable @{LogName='Security'; ID=5157}
   ```

5. **Restore from backup if needed**

6. **Review and tighten security settings**

---

## Summary of Security Measures

| Vulnerability | Status | Implementation |
|--------------|--------|----------------|
| Path Traversal | ✅ Fixed | `validate_db_path()` function |
| Rate Limiting | ✅ Fixed | `RateLimiter` class with IP-based limits |
| File Permissions | ⚠️ Manual | Set via PowerShell commands above |
| Service Account | ⚠️ Manual | Create dedicated Windows user |
| HTTPS/TLS | ✅ Server-level | Already configured on web server |
| SQL Injection | ✅ Protected | Parameterized queries used |
| XSS | ✅ Fixed | Fixed per git history |
| Authentication | N/A | Public service by design |

---

## Contact

For security concerns or questions, contact your system administrator.

**Last Updated:** 2025-10-03
