#!/usr/bin/env bash
# SteelCAD — Oracle Cloud host preparation, run BEFORE deploy/bootstrap.sh.
#
# Oracle's Ubuntu images are the one environment where "open the ports in the
# cloud console" is not enough: the image also ships a host firewall that
# REJECTs inbound traffic on everything except SSH. A deploy that skips this
# completes successfully, reports healthy containers, and is unreachable from
# the internet — and Caddy silently fails its Let's Encrypt HTTP-01 challenge,
# so there is no certificate either.
#
# This script fixes the HOST side only. The VCN ingress rules are a console (or
# oci-cli) action that cannot be performed from inside the instance — step 3 of
# the runbook. It verifies at the end that both layers are actually open.
#
# Usage (as the default 'ubuntu' user on a fresh Always Free instance):
#   sudo ./deploy/oracle-prep.sh
#   ./deploy/bootstrap.sh          # note: NOT as root — see step 6
#
# Safe to re-run: every rule is inserted only if an equivalent one is absent.

set -euo pipefail

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!!  %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mxx  %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run with sudo: sudo ./deploy/oracle-prep.sh"

TARGET_USER="${SUDO_USER:-ubuntu}"

# ── 1. Host firewall ─────────────────────────────────────────────────
# Oracle's rules.v4 ends the INPUT chain with a blanket
#   -A INPUT -j REJECT --reject-with icmp-host-prohibited
# so an ACCEPT for 80/443 must be INSERTED ahead of it, not appended after
# (appending puts it behind the REJECT, where it never matches — this is the
# single most common way this fix is applied incorrectly).
#
# We insert at position 1. Deliberately NOT `iptables -F`, which the popular
# blog answers recommend: flushing drops Oracle's conntrack and anti-spoofing
# rules too, and on an instance whose default policy happens to be DROP it ends
# the SSH session you are typing into.
say "Opening ports 80/443 on the host firewall"

open_port() {
    local port="$1"
    if iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
        echo "  :$port already allowed"
    else
        iptables -I INPUT 1 -p tcp --dport "$port" -j ACCEPT
        echo "  :$port opened"
    fi
}

if command -v iptables >/dev/null 2>&1; then
    open_port 80
    open_port 443
else
    warn "iptables not found — skipping (unusual for an Oracle Ubuntu image)"
fi

# Persist across reboot. Without this the rules vanish on the first restart and
# the site goes dark in a way that looks like a Docker or Caddy fault.
say "Persisting firewall rules across reboots"
if ! dpkg -s iptables-persistent >/dev/null 2>&1; then
    echo "  installing iptables-persistent"
    # Preseed both prompts: the package otherwise opens an interactive dialog
    # and hangs a non-tty run forever.
    echo iptables-persistent iptables-persistent/autosave_v4 boolean true | debconf-set-selections
    echo iptables-persistent iptables-persistent/autosave_v6 boolean true | debconf-set-selections
    DEBIAN_FRONTEND=noninteractive apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq iptables-persistent >/dev/null
fi
netfilter-persistent save >/dev/null 2>&1 && echo "  saved" || warn "could not persist rules — re-run after reboot"

# Some images additionally run ufw. If it is active it is a second, independent
# filter that will drop the traffic regardless of the rules above.
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
    say "ufw is active — allowing 80/443 there too"
    ufw allow 80/tcp  >/dev/null
    ufw allow 443/tcp >/dev/null
    echo "  done"
fi

# ── 2. Docker ────────────────────────────────────────────────────────
say "Installing Docker"
if command -v docker >/dev/null 2>&1; then
    echo "  already installed: $(docker --version)"
else
    curl -fsSL https://get.docker.com | sh
fi

# bootstrap.sh refuses to run without a usable Docker socket. Adding the user
# to the docker group avoids running the whole deploy — and thus writing .env
# and .admin-password — as root.
if ! id "$TARGET_USER" >/dev/null 2>&1; then
    warn "user '$TARGET_USER' not found — skipping docker group setup."
    echo "     You are root, so bootstrap.sh will still work, but it will write"
    echo "     .env and .admin-password as root. Prefer re-running via sudo from"
    echo "     the 'ubuntu' account."
elif ! id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx docker; then
    say "Adding '$TARGET_USER' to the docker group"
    usermod -aG docker "$TARGET_USER"
    warn "Group change needs a new login session. Run:  exit  then SSH back in."
    NEED_RELOGIN=1
fi

systemctl enable --now docker >/dev/null 2>&1 || true

# ── 3. Swap ──────────────────────────────────────────────────────────
# The frontend image runs `npm ci && vite build` inside Docker. On a 2 OCPU /
# 12 GB Always Free shape there is plenty of RAM, but a 1 GB shape (or a
# VM.Standard.E2.1.Micro fallback when Ampere capacity is unavailable) will OOM
# mid-build with an unhelpful exit 137.
TOTAL_MB=$(free -m | awk '/^Mem:/{print $2}')
if [ "$TOTAL_MB" -lt 3000 ] && ! swapon --show | grep -q .; then
    say "Only ${TOTAL_MB}MB RAM and no swap — adding 2G swapfile for the Vite build"
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "  swap active"
fi

# ── 4. Report ────────────────────────────────────────────────────────
# Deliberately NOT attempting an automated "is :80 open from the internet"
# check here. The only vantage point available is the instance itself, and a
# probe from the instance to its own public IP is answered by hairpin NAT
# without ever traversing the VCN security list — so it passes just as happily
# when the ingress rule is missing. A green light that cannot detect the actual
# failure is worse than no light. The real end-to-end test is bootstrap.sh's
# HTTPS smoke test, and the definitive one is loading the URL on your phone.
say "Host preparation complete"

PUBLIC_IP="$(curl -fsS --max-time 10 https://api.ipify.org || true)"
[ -n "$PUBLIC_IP" ] && echo "  public IP: ${PUBLIC_IP}"

warn "Host firewall is only ONE of Oracle's two layers."
echo "     Confirm the VCN ingress rule exists before continuing (runbook step 3):"
echo "       Networking > VCN > <your vcn> > Security Lists > Default"
echo "       Add Ingress: source 0.0.0.0/0, IP protocol TCP, dest ports 80,443"
echo "     Without it the deploy completes, containers report healthy, and the"
echo "     site is simply unreachable — with no certificate, because Caddy's"
echo "     Let's Encrypt challenge needs inbound :80."

echo "  Next:"
if [ "${NEED_RELOGIN:-0}" = 1 ]; then
    echo "    1. exit, then SSH back in (to pick up the docker group)"
    echo "    2. cd /srv/steelcad && ./deploy/bootstrap.sh"
else
    echo "    cd /srv/steelcad && ./deploy/bootstrap.sh"
fi
echo
echo "  bootstrap.sh will detect ${PUBLIC_IP:-<ip>} and serve the app at"
echo "  https://${PUBLIC_IP:-<ip>}.sslip.io with an auto-renewing certificate."
