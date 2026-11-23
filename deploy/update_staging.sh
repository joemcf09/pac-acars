#!/usr/bin/env bash
# Update the test copy from an uploaded zip. Same steps as the live update (backup, new release, health check,
# automatic rollback), pointed at /home/pac/pac-staging and the pac-staging service. The live site is not touched.
#   deploy.bat --staging     runs this for you
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/staging.env"
exec "$HERE/update.sh" "$@"
