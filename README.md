# Docker Nginx Auto-Config Daemon

This Python daemon automatically monitors Docker containers for a specific label (export-host) and generates Nginx configuration for reverse proxying. It can also manage TLS certificates using Certbot for HTTPS.

## Features

- Event-driven: Listens to Docker events (start, stop, create, die) — no polling required.
- Automatic Nginx config generation: Creates a reverse proxy config for containers with the export-host label.
- Smart updates: Only rewrites configs if needed.
- TLS support: Checks for existing certificates and requests new ones using Certbot when required.
- Systemd daemon: Can run continuously in the background.

# Requirements

- Python 3
- Docker & Docker SDK for Python (pip install docker)
- python-click
- Nginx
- Certbot & Certbot Nginx plugin (optional for HTTPS)
- Root privileges for installing systemd service

# Installation

Place the following files in the same directory:

- docker_nginx_daemon.py
- docker_nginx_daemon.service
- Makefile


## Install the service:
```bash
sudo make install
```

## Verify the service is running:
```bash
systemctl status docker-nginx-daemon
```

# Usage
Labeling containers

Add the export-host label to any Docker container you want to expose via Nginx:
```bash
docker run -d \
  --name myapp \
  --label "export-host=example.host.com" \
  nginx
```

The daemon will automatically:
- Generate Nginx reverse proxy config for example.host.com.
- Reload Nginx.
- Request a TLS certificate with Certbot (if enabled and needed).

An example using docker compose:
```yaml
services:
  webapp1:
    image: nginx:latest
    container_name: webapp1
    labels:
      export-host: webapp1.example.com # Important! use by the daemon
    ports:
      - "8081:80" # Important! use by the daemon

  webapp2:
    image: nginx:latest
    container_name: webapp2
    labels:
      export-host: webapp2.example.com # Important! use by the daemon
    ports:
      - "8082:80" # Important! use by the daemon

  # Optional: a dummy service that shows no label (ignored by the daemon)
  db:
    image: postgres:17
    container_name: db
    environment:
      POSTGRES_PASSWORD: example

```


## Utils

List all conatines with the label and status:

```bash
/usr/local/bin/docker_nginx_daemon.py list
```

Check dependencies and overall health:

```bash
/usr/local/bin/docker_nginx_daemon.py doctor
```

## Stopping the daemon

To stop and remove the service:
```bash
sudo make uninstall
```

## Nginx Configuration

Configs are generated in /etc/nginx/sites-enabled/ (or as specified in docker_nginx_daemon.py).

Only containers with the export-host label are included.

Configs are only updated if changed.

## TLS / HTTPS

TLS certificates are managed by Certbot (--nginx plugin).

Certificates are only requested if not present or expired.

Supports automatic renewal through Certbot.

## Logging

By default, logs appear in journalctl for the service:

```bash
journalctl -u docker-nginx-daemon -f
```

You can optionally redirect logs in the Python script to a file for easier debugging.

# Development / Testing

You can run the daemon manually without installing:
```bash
python3 docker_nginx_daemon.py daemon
```

Changes to Nginx template or script will take effect on the next container event or manual reconcile.

# Notes / Best Practices

Run sudo make install to install and start the service.

Ensure Nginx and Docker are installed and running.

For HTTPS, make sure port 80 and 443 are open and accessible for Certbot.

For production setups, consider using Traefik or Caddy if you need a more dynamic or large-scale reverse proxy solution.