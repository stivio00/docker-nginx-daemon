#!/usr/bin/env python3
import docker
import subprocess
from pathlib import Path
import signal
import ssl
import datetime
import os
import click

# -----------------------------
# Configuration from environment
# -----------------------------
NGINX_SITES_DIR = os.environ.get("NGINX_SITES_DIR", "/etc/nginx/sites-enabled")
CERTBOT_CERT_DIR = os.environ.get("CERTBOT_CERT_DIR", "/etc/letsencrypt/live")
TEMPLATE_PATH = os.environ.get(
    "NGINX_TEMPLATE_PATH", "/etc/docker-nginx-daemon/site-template.conf"
)
LABEL_NAME = "export-host"

# Load Nginx template
if Path(TEMPLATE_PATH).exists():
    NGINX_TEMPLATE = Path(TEMPLATE_PATH).read_text()
else:
    NGINX_TEMPLATE = """
server {
    listen 80;
    server_name {server_name};

    location / {
        proxy_pass http://{container_ip}:{container_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
"""

# -----------------------------
# Docker client
# -----------------------------
client = docker.from_env()
running = True


def signal_handler(sig, frame):
    global running
    print("🛑 Stopping daemon...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# -----------------------------
# Helpers
# -----------------------------
def collect_hosts():
    """Collect all containers with export-host label."""
    exported = []
    for container in client.containers.list(all=True):
        labels = container.attrs.get("Config", {}).get("Labels", {})
        host = labels.get(LABEL_NAME)
        if not host:
            continue

        ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
        container_port = None
        container_ip = container.attrs.get("NetworkSettings", {}).get("IPAddress")
        if ports:
            first_port = next(iter(ports.keys()))
            container_port = first_port.split("/")[0]

        exported.append(
            {
                "name": container.name,
                "host": host,
                "status": container.status,
                "ip": container_ip,
                "port": container_port,
            }
        )
    return exported


def conf_exists(host):
    return (Path(NGINX_SITES_DIR) / f"{host}.conf").exists()


def ssl_exists(host):
    return (Path(CERTBOT_CERT_DIR) / host / "cert.pem").exists()


def conf_needs_update(host, expected_content):
    """Check if the nginx conf exists and matches expected content."""
    conf_path = Path(NGINX_SITES_DIR) / f"{host}.conf"
    if not conf_path.exists():
        return True
    current = conf_path.read_text()
    return current.strip() != expected_content.strip()


def generate_nginx_conf(exported_hosts):
    Path(NGINX_SITES_DIR).mkdir(parents=True, exist_ok=True)
    for entry in exported_hosts:
        conf_content = NGINX_TEMPLATE.format(
            server_name=entry["host"],
            container_ip=entry["ip"],
            container_port=entry["port"] or "80",
        )
        conf_path = Path(NGINX_SITES_DIR) / f"{entry['host']}.conf"
        if conf_needs_update(entry["host"], conf_content):
            conf_path.write_text(conf_content)
            print(f"✅ Updated {conf_path}")
        else:
            print(f"⏩ Config for {entry['host']} up to date, skipping")


def reload_nginx():
    try:
        subprocess.run(["systemctl", "reload", "nginx"], check=True)
        print("🔄 Nginx reloaded via systemctl")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to reload Nginx: {e}")


def cert_is_valid(domain):
    cert_path = Path(CERTBOT_CERT_DIR) / domain / "cert.pem"
    if not cert_path.exists():
        return False
    try:
        cert = ssl._ssl._test_decode_cert(str(cert_path))
        expiry = datetime.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
        return expiry > datetime.datetime.utcnow()
    except Exception:
        return False


def obtain_certificates(exported_hosts):
    for entry in exported_hosts:
        domain = entry["host"]
        if cert_is_valid(domain):
            print(f"⏩ Certificate for {domain} still valid, skipping")
            continue
        print(f"🔑 Requesting certificate for {domain}...")
        subprocess.run(
            [
                "certbot",
                "--nginx",
                "-d",
                domain,
                "--non-interactive",
                "--agree-tos",
                "-m",
                f"admin@{domain}",
            ],
            check=True,
        )


def reconcile():
    hosts = collect_hosts()
    if not hosts:
        print("⚠️ No containers with export-host label found")
        return
    generate_nginx_conf(hosts)
    reload_nginx()
    obtain_certificates(hosts)


def check_dependencies():
    """Check if required dependencies are installed and usable."""
    deps = {
        "docker": ["docker", "--version"],
        "nginx": ["systemctl", "is-active", "nginx"],
        "certbot": ["certbot", "--version"],
        "python3": ["python3", "--version"],
    }

    for name, cmd in deps.items():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if name == "nginx":
                status = "✅ active" if result.stdout.strip() == "active" else "❌ inactive"
            else:
                status = "✅"
        except (subprocess.CalledProcessError, FileNotFoundError):
            status = "❌"
        print(f"{name}: {status}")


def list_containers():
    containers = collect_hosts()
    if not containers:
        print("⚠️ No containers found with export-host label")
        return
    print(f"{'CONTAINER':20} {'HOST':30} {'NGINX':6} {'SSL':6} {'STATUS':10}")
    print("-" * 80)
    for c in containers:
        nginx_enabled = "✅" if conf_exists(c["host"]) else "❌"
        ssl_enabled = "✅" if ssl_exists(c["host"]) else "❌"
        print(
            f"{c['name']:20} {c['host']:30} {nginx_enabled:6} {ssl_enabled:6} {c['status']:10}"
        )


# -----------------------------
# CLI with Click
# -----------------------------
@click.group()
def cli():
    pass


@cli.command()
def daemon():
    """Run the daemon to watch Docker events and update Nginx/Certs."""
    print("📡 Docker Nginx daemon started...")
    reconcile()
    global running
    for event in client.events(decode=True):
        if not running:
            break
        if event["Type"] != "container":
            continue
        action = event["Action"]
        attrs = event.get("Actor", {}).get("Attributes", {})
        if LABEL_NAME not in attrs:
            continue
        if action in ["start", "stop", "die", "destroy"]:
            print(f"⚡ Container {action} detected for host {attrs[LABEL_NAME]}")
            reconcile()
    print("👋 Exiting daemon")


@cli.command()
def ls():
    """List all containers with export-host label and check Nginx/SSL."""
    list_containers()


@cli.command()
def doctor():
    """Check if required dependencies are installed."""
    check_dependencies()


if __name__ == "__main__":
    cli()
