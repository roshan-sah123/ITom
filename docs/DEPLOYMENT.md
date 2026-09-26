# ITOM Operations Analytics — Production Deployment Runbook

This runbook describes the deployment architectures, procedures, security hardening, and operational management for hosting the ITOM Operations Analytics portal across on-premise Windows servers, Linux virtual machines, containerized environments, and cloud CDNs.

---

## 1. Deployment Architecture Options

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           PRODUCTION DEPLOYMENT MODES                           │
├──────────────────────┬──────────────────────┬───────────────────────────────────┤
│ Model 1: Windows 24/7│ Model 2: Linux VM    │ Model 3: Docker Container         │
│ • Task Scheduler     │ • systemd daemon     │ • Python 3.12-slim base           │
│ • start_itom_service │ • scripts/deploy_to  │ • docker-compose.yml              │
│ • Port 8080 / IIS    │ • Port 8080 / Nginx  │ • Port 8080 isolation             │
└──────────────────────┴──────────────────────┴───────────────────────────────────┘
```

---

## 2. Model 1: Windows Server / Workstation Deployment

### 2.1 Quick Interactive Launch
For ad-hoc or development use, start the foreground supervisor:
```cmd
start_itom_service.bat --open-browser
```

### 2.2 Background Service Supervisor (`start_itom_service.bat`)
To run the server in the background as a detached process:
```cmd
:: Start in background
start_itom_service.bat --background

:: Check API, database, frontend, and data freshness
start_itom_service.bat --status

:: Stop background server
start_itom_service.bat --stop

:: Restart background server
start_itom_service.bat --restart
```

### 2.3 Local Windows Scheduled Task (`register_startup_service.ps1`)
To start the local FastAPI, SQLite, and frontend supervisor when the signed-in user logs on:
```powershell
# Open PowerShell as Administrator and run:
powershell -ExecutionPolicy Bypass -File .\register_startup_service.ps1

# Verify task status:
powershell -ExecutionPolicy Bypass -File .\register_startup_service.ps1 -Status

# To remove the task:
powershell -ExecutionPolicy Bypass -File .\register_startup_service.ps1 -Uninstall
```

---

## 3. Model 2: Linux Production VM (systemd)

### 3.1 Automated Deployment Engine (`scripts/deploy_to_vm.py`)
To deploy from your workstation to a remote Linux host over SSH:
```bash
python scripts/deploy_to_vm.py --host <YOUR_SERVER_IP> --user <YOUR_SSH_USER> --port 8080
```

This script:
1. Validates SSH connectivity.
2. Synchronizes required directories (`data/`, `src/`, `scripts/`, `systemd/`, HTML/CSS/JS assets).
3. Installs `systemd/itom.service` to `/etc/systemd/system/itom.service`.
4. Executes `systemctl daemon-reload` and `systemctl enable --now itom.service`.

### 3.2 Manual Linux systemd Setup
If configuring manually on the target Linux host:

1. **Clone repository and set up virtual environment**:
   ```bash
   cd /home/roshan/itom-portal
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   chmod 600 .env
   ```

2. **Copy systemd service unit**:
   ```bash
   sudo cp systemd/itom.service /etc/systemd/system/itom.service
   sudo chown root:root /etc/systemd/system/itom.service
   sudo chmod 644 /etc/systemd/system/itom.service
   ```

3. **Enable and Start Service**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable itom.service
   sudo systemctl start itom.service
   ```

4. **Monitor Service Health**:
   ```bash
   # Check active service status
   sudo systemctl status itom.service

   # View real-time logs via journalctl
   sudo journalctl -u itom.service -f -n 50
   ```

---

## 4. Model 3: Containerized Docker Deployment

### 4.1 Build Docker Container
The repository includes an optimized `Dockerfile` and `.dockerignore`:
```bash
docker build -t itom-portal:latest .
```

### 4.2 Run via Docker Compose
```bash
docker compose up -d
```

Verify running container:
```bash
docker compose ps
docker compose logs -f
```

### 4.3 Container Security & Isolation
- Non-root user execution inside container.
- `.dockerignore` guarantees `.env`, private keys, local test caches, and Git history are never baked into container layers.
- Runtime secrets should be mounted as environment variables:
  ```bash
  docker run -d --name itom-portal -p 8080:8080 --env-file .env itom-portal:latest
  ```

---

## 5. Reverse Proxy & SSL/TLS Termination

For enterprise production environments, front the Python HTTP daemon with an Nginx reverse proxy providing TLS 1.3 encryption and gzip compression.

### 5.1 Nginx Configuration (`/etc/nginx/sites-available/itom-portal`)
```nginx
server {
    listen 80;
    server_name itom.internal.corp;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name itom.internal.corp;

    ssl_certificate /etc/ssl/certs/itom-portal.crt;
    ssl_certificate_key /etc/ssl/private/itom-portal.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Anti-caching for dynamic JSON telemetry payloads
    location ~* \.json$ {
        proxy_pass http://127.0.0.1:8080;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        expires 0;
    }

    # Static assets and REST API routing
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for long paginated queries
        proxy_connect_timeout 15s;
        proxy_read_timeout 60s;
    }

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
}
```

---

## 6. Security Hardening Checklist

| Security Control | Implementation | Verification |
| :--- | :--- | :--- |
| **Credential Protection** | Credentials stored exclusively in `.env` | Run `python -m unittest tests.verify_adversarial_security` |
| **File Permissions** | Set `.env` file permissions to `chmod 600` | Verify only service user can read `.env` |
| **Firewall Rules** | Allow inbound on port `8080` (or `443` for TLS reverse proxy) | `ufw allow 8080/tcp` or Windows Advanced Firewall |
| **XSS Defense** | Strict `escapeHtml()` sanitization across all DOM insertions | Automated XSS attack matrix test passing |
| **Read-Only API** | Mutating HTTP methods (`POST`, `PUT`, `DELETE`, `PATCH`) blocked | Verify curl returns `405 Method Not Allowed` |

---

## 7. Backup & Disaster Recovery

1. **Snapshot Backups**: The authoritative JSON datasets (`data/intune_ops_analytics.json`, `data/solarwinds_nodes.json`) should be backed up daily to cold storage or backup shares.
2. **CSV Audit Archives**: Historical CSV exports in `exports/` can be archived into dated tarballs:
   ```bash
   tar -czf /backup/itom_exports_$(date +%Y%m%d).tar.gz exports/*.csv
   ```
