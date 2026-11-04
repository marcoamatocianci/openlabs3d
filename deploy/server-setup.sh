#!/usr/bin/env bash
# One-time preparation of a fresh Ubuntu Server LTS machine (VPS or physical) for OpenLabs3D. Run as root:
#
#   DEPLOY_SSH_KEY="ssh-ed25519 AAAA... you@laptop" bash deploy/server-setup.sh
#
# Idempotent. What it does (docs/deployment/PRODUCTION.md, "Server"):
#   - security updates installed automatically (unattended-upgrades; no automatic reboots);
#   - a `deploy` user with your SSH key; SSH by key only, no root or password login (checked before reload);
#   - firewall: only SSH, HTTP and HTTPS (HTTP/3) inbound;
#   - Docker Engine + Compose from Docker's repository, with log rotation and no-new-privileges by default;
#   - fail2ban for SSH, a swap file (Blender's peaks), journald size limits, the backup timers.
# Note: membership of the docker group is equivalent to root on this machine; only `deploy` has it.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run as root." >&2; exit 1; }
. /etc/os-release
[ "$ID" = ubuntu ] || { echo "Written for Ubuntu Server LTS; this is $PRETTY_NAME." >&2; exit 1; }
KEY=${DEPLOY_SSH_KEY:-}
APP_DIR=/srv/openlabs3d

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl git ufw unattended-upgrades fail2ban zstd restic jq

echo "== automatic security updates"
cat > /etc/apt/apt.conf.d/52openlabs3d-unattended <<'EOF'
Unattended-Upgrade::Allowed-Origins { "${distro_id}:${distro_codename}-security"; "${distro_id}ESMApps:${distro_codename}-apps-security"; };
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

echo "== deploy user"
id deploy >/dev/null 2>&1 || adduser --disabled-password --gecos "OpenLabs3D deploy" deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
if [ -n "$KEY" ]; then
  grep -qxF "$KEY" /home/deploy/.ssh/authorized_keys 2>/dev/null || echo "$KEY" >> /home/deploy/.ssh/authorized_keys
fi
[ -f /root/.ssh/authorized_keys ] && [ ! -s /home/deploy/.ssh/authorized_keys ] && cp /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys 2>/dev/null || true
chmod 600 /home/deploy/.ssh/authorized_keys 2>/dev/null || true

echo "== SSH: keys only"
if [ -s /home/deploy/.ssh/authorized_keys ]; then
  cat > /etc/ssh/sshd_config.d/10-openlabs3d.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowUsers deploy
EOF
  sshd -t && systemctl reload ssh
else
  echo "WARNING: deploy has no SSH key yet; SSH login was NOT restricted. Re-run with DEPLOY_SSH_KEY." >&2
fi

echo "== firewall"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable
# Docker publishes ports through its own iptables rules, past ufw: only Caddy publishes any (80/443), and
# compose.production.yaml publishes nothing else. Never add "ports:" to db, backend or worker.

echo "== fail2ban (SSH)"
cat > /etc/fail2ban/jail.d/openlabs3d.local <<'EOF'
[sshd]
enabled = true
maxretry = 5
bantime = 1h
EOF
systemctl enable --now fail2ban

echo "== Docker Engine"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -q && apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "5"},
  "live-restore": true,
  "no-new-privileges": true,
  "userland-proxy": false
}
EOF
systemctl restart docker
usermod -aG docker deploy

echo "== swap (2 GB) and journald limits"
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=10 >/dev/null && echo 'vm.swappiness=10' > /etc/sysctl.d/90-openlabs3d.conf
fi
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=500M\n' > /etc/systemd/journald.conf.d/openlabs3d.conf
systemctl restart systemd-journald

echo "== application directory and backups"
install -d -o deploy -g deploy "$APP_DIR"
install -d -m 700 -o deploy -g deploy /var/backups/openlabs3d
if [ -d "$APP_DIR/deploy/systemd" ]; then
  cp "$APP_DIR"/deploy/systemd/*.service "$APP_DIR"/deploy/systemd/*.timer /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now openlabs3d-backup.timer openlabs3d-verify-backup.timer
else
  echo "Clone the repository into $APP_DIR as deploy, then re-run this script to install the backup timers."
fi
echo "Server prepared. Next: deploy/README.md, 'First installation'."
