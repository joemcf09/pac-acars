#!/usr/bin/env bash
# Update the test copy from an uploaded zip. Same steps as the live update (backup, new release, health check,
# automatic rollback), pointed at /home/pac/pac-staging and the pac-staging service. The live site is not touched.
#   deploy.bat --staging     runs this for you
#
# The settings live here, in a .sh file, on purpose: .sh files always reach the server with Linux line endings.
# (A separate settings file picked up Windows line endings, and a hidden \r at the end of every path sent the
# first setup to "/home/pac/pac-staging\r".)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PAC_DEPLOY_ROOT=/home/pac/pac-staging
export PAC_HEALTH_URL=http://127.0.0.1:5055/up
export PAC_SVC_RESTART="sudo systemctl restart pac-staging"
export PAC_SVC_STOP="sudo systemctl stop pac-staging"
export PAC_SVC_ISACTIVE="systemctl is-active --quiet pac-staging"
export PAC_SVC_DISCORD_RESTART=""          # the test copy has no Discord bot
export PAC_BACKUP_DIR=/home/pac/backups-staging
export PAC_BACKUP_KEEP_DAYS=7
export PAC_KEEP_RELEASES=3
exec "$HERE/update.sh" "$@"
