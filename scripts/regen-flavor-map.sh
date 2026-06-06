#!/usr/bin/env bash
# Re-run UMAP + DBSCAN against the current DB state and refresh the
# host's cluster_impressions.json.
#
# Use when you tweaked a flavor profile, removed a bottle, or just want
# to re-cluster without adding anything. For add-a-bottle, use
# scripts/add-bottle.sh — it calls this same logic at the end.
#
# Prereqs:
#   - Local stack up via:
#       docker compose -f compose.yaml -f compose.build.yaml up -d
#   - Frontend container named mix-ml-frontend.
#   - jq, python3, docker on PATH.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMPRESSIONS_JSON="$REPO_ROOT/frontend/app/data/cluster_impressions.json"
FRONTEND_CONTAINER="${FRONTEND_CONTAINER:-mix-ml-frontend}"
FRONTEND_HOST="${FRONTEND_HOST:-http://127.0.0.1:3000}"

echo "→ GET $FRONTEND_HOST/inventory/flavor-map/regenerate"
curl -fsS -o /dev/null "$FRONTEND_HOST/inventory/flavor-map/regenerate" || \
    echo "  WARNING: frontend regenerate failed (continuing — calibrate still runs)" >&2

echo "→ docker exec $FRONTEND_CONTAINER python -m app._tools.calibrate --write"
docker exec --user 0 "$FRONTEND_CONTAINER" \
    python -m app._tools.calibrate \
        --backend-url http://backend:8080 \
        --write \
        --output /opt/app-root/src/app/data/cluster_impressions.json

echo "→ Clusters still flagged TODO:"
python3 - "$IMPRESSIONS_JSON" <<'PY'
import json, sys
d = json.loads(open(sys.argv[1]).read())
flagged = []
for cid, c in d.get("clusters", {}).items():
    if "TODO" in c.get("impression", ""):
        flagged.append(("cluster", cid, c["impression"].split(" · ")[0]))
for key, o in d.get("outliers", {}).items():
    if "TODO" in o.get("impression", ""):
        flagged.append(("outlier", key, o["impression"].split(" · ")[0]))
if not flagged:
    print("  (none — every cluster has a curated impression)")
else:
    for kind, cid, title in flagged:
        print(f"  {kind:8} {cid:50} {title}")
    print("\n  Edit the impression text in:")
    print(f"    {sys.argv[1]}")
    print("  Then `docker compose restart frontend` to pick up the new text.")
PY
