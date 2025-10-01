# Paths
SERVICE_NAME = docker-nginx-daemon
SCRIPT_SRC = $(shell pwd)/docker_nginx_daemon.py
SCRIPT_DST = /usr/local/bin/docker_nginx_daemon.py
UNIT_SRC = $(shell pwd)/docker_nginx_daemon.service
UNIT_DST = /etc/systemd/system/$(SERVICE_NAME).service
TEMPLATE_DIR = /etc/docker-nginx-daemon
TEMPLATE_FILE = $(TEMPLATE_DIR)/site-template.conf

.PHONY: all install uninstall help install-deps 

all: help

help:
	@echo "Usage:"
	@echo "  sudo make install   - install and start the daemon"
	@echo "  sudo make uninstall - stop and remove the daemon"
	@echo "  sudo make install-deps  - install required system dependencies"

install-deps:
	@echo "📦 Installing dependencies..."
	apt update
	apt install -y python3 python3-pip nginx certbot python3-certbot-nginx docker.io
	pip3 install --upgrade pip
	pip3 install docker
	@echo "✅ Dependencies installed"

install:
	@echo "📦 Installing $(SERVICE_NAME)..."

	# Copy Python daemon
	cp $(SCRIPT_SRC) $(SCRIPT_DST)
	chmod +x $(SCRIPT_DST)
	@echo "✅ Copied Python script to $(SCRIPT_DST)"

	# Ensure template directory exists
	mkdir -p $(TEMPLATE_DIR)

	# Create default template if missing
	if [ ! -f $(TEMPLATE_FILE) ]; then \
		echo "server {" > $(TEMPLATE_FILE); \
		echo "    listen 80;" >> $(TEMPLATE_FILE); \
		echo "    server_name {server_name};" >> $(TEMPLATE_FILE); \
		echo "    location / {" >> $(TEMPLATE_FILE); \
		echo "        proxy_pass http://{container_ip}:{container_port};" >> $(TEMPLATE_FILE); \
		echo "        proxy_set_header Host $$host;" >> $(TEMPLATE_FILE); \
		echo "        proxy_set_header X-Real-IP $$remote_addr;" >> $(TEMPLATE_FILE); \
		echo "        proxy_set_header X-Forwarded-For $$proxy_add_x_forwarded_for;" >> $(TEMPLATE_FILE); \
		echo "        proxy_set_header X-Forwarded-Proto $$scheme;" >> $(TEMPLATE_FILE); \
		echo "    }" >> $(TEMPLATE_FILE); \
		echo "}" >> $(TEMPLATE_FILE); \
		echo "✅ Created default Nginx template at $(TEMPLATE_FILE)"; \
	else \
		echo "⏩ Nginx template already exists, skipping"; \
	fi

	# Install systemd unit file
	sed "s|__SCRIPT_PATH__|$(SCRIPT_DST)|" $(UNIT_SRC) > /tmp/$(SERVICE_NAME).service
	cp /tmp/$(SERVICE_NAME).service $(UNIT_DST)
	rm -f /tmp/$(SERVICE_NAME).service
	@echo "✅ Installed systemd unit file"

	# Reload systemd and start service
	systemctl daemon-reload
	systemctl enable --now $(SERVICE_NAME)
	@echo "✅ Service installed and started"

uninstall:
	@echo "🛑 Uninstalling $(SERVICE_NAME)..."
	systemctl stop $(SERVICE_NAME) || true
	systemctl disable $(SERVICE_NAME) || true
	rm -f $(UNIT_DST)
	rm -f $(SCRIPT_DST)
	systemctl daemon-reload
	@echo "✅ Service removed"
