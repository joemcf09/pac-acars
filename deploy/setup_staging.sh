#!/usr/bin/env bash
# One-time setup of PAC's test copy at staging.pac-va.com. Run as root; `deploy.bat --staging` runs it for you
# the first time and passes the login name and password on standard input (two lines: name, then password).
#
#   setup_staging.sh /home/pac/pac-staging.zip  < (name and password)
#
# 1. Makes /home/pac/pac-staging (releases/, shared/data) owned by pac.
# 2. Copies the live data into it, without secrets (refresh_staging_data.sh).
# 3. Installs and enables the pac-staging service (port 5055, PAC_STAGING=1).
# 4. Adds staging.pac-va.com to Caddy behind a login, checks the config and reloads Caddy. The live site's
#    blocks are left exactly as they are; a broken config is put back before anything reloads.
# 5. Builds the first release from the zip with the normal update script (health-checked).
# The live site keeps running throughout and is only read.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZIP="${1:?Usage: setup_staging.sh /path/to/pac-acars.zip}"
DOMAIN="${PAC_STAGING_DOMAIN:-staging.pac-va.com}"
CADDYFILE="${PAC_CADDYFILE:-/etc/caddy/Caddyfile}"
ROOT=/home/pac/pac-staging

[ "$(id -u)" = 0 ] || { echo "Run this as root."; exit 1; }
[ -f "$ZIP" ] || { echo "zip not found: $ZIP"; exit 1; }
command -v caddy >/dev/null || { echo "Caddy isn't installed here."; exit 1; }
command -v rsync >/dev/null || apt-get install -y -qq rsync

read -r LOGIN_NAME || true
read -r LOGIN_PASS || true
# Windows sends lines ending in CR LF; the CR is not part of the name or password
LOGIN_NAME="${LOGIN_NAME%$'\r'}"; LOGIN_PASS="${LOGIN_PASS%$'\r'}"
LOGIN_NAME="${LOGIN_NAME:-pac}"
[ -n "${LOGIN_PASS:-}" ] || { echo "No password given for the test site's login."; exit 1; }
case "$LOGIN_NAME" in *[!A-Za-z0-9._-]*) echo "The login name may only use letters, numbers, dot, dash and underscore."; exit 1;; esac

echo "[1] Folders"
mkdir -p "$ROOT/releases" "$ROOT/shared/data" /home/pac/backups-staging
chown -R pac:pac "$ROOT" /home/pac/backups-staging

echo "[2] Copying the live data (without secrets)"
PAC_STAGING_RESTART=0 "$HERE/refresh_staging_data.sh"

echo "[3] Installing the pac-staging service"
cp "$HERE/pac-staging.service" /etc/systemd/system/pac-staging.service
systemctl daemon-reload
systemctl enable pac-staging >/dev/null

echo "[4] Adding $DOMAIN to Caddy behind a login"
if grep -q "^$DOMAIN " "$CADDYFILE"; then
  echo "  $DOMAIN is already in $CADDYFILE; leaving it as it is"
else
  HASH="$(printf '%s\n' "$LOGIN_PASS" | caddy hash-password 2>/dev/null | tail -n1)"
  case "$HASH" in '$2'*) ;; *) HASH="$(caddy hash-password --plaintext "$LOGIN_PASS" | tail -n1)";; esac
  # basic_auth is Caddy 2.8's name; older Caddy calls it basicauth
  AUTH=basic_auth
  caddy version 2>/dev/null | grep -Eq '^v2\.[0-7]\.' && AUTH=basicauth
  cp "$CADDYFILE" "$CADDYFILE.before-staging"
  cat >> "$CADDYFILE" <<CADDY

# PAC's test copy: same program, copy of the live data, sends nothing out. Added by deploy/setup_staging.sh.
# The login is checked here, before PAC sees the request; certificate renewals are not affected by it.
$DOMAIN {
	encode zstd gzip
	$AUTH {
		$LOGIN_NAME $HASH
	}
	reverse_proxy 127.0.0.1:5055
	request_body {
		max_size 2GB
	}
	header X-Robots-Tag "noindex, nofollow"
}
CADDY
  if ! caddy validate --config "$CADDYFILE" --adapter caddyfile >/tmp/caddy-validate.log 2>&1; then
    cp "$CADDYFILE.before-staging" "$CADDYFILE"
    cat /tmp/caddy-validate.log
    echo "Caddy didn't accept the new block, so the Caddyfile was put back unchanged. The live site is unaffected."
    exit 1
  fi
  systemctl reload caddy
  echo "  added; the previous Caddyfile is kept at $CADDYFILE.before-staging"
fi

echo "[5] Building the first release"
"$HERE/update_staging.sh" "$ZIP"
chown -R pac:pac "$ROOT" 2>/dev/null || true
echo
echo "The test copy is running. Open https://$DOMAIN and sign in as '$LOGIN_NAME' with the password you chose."
