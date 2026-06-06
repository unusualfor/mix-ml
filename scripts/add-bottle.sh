#!/usr/bin/env bash
# Add one bottle end-to-end against the running local stack.
#
# Pipeline:
#   1. Validate the input JSON file (single bottle object, same shape as
#      one element of scripts/data/bottles_seed.json).
#   2. Append to scripts/data/bottles_seed.json (source of truth).
#   3. POST the full bottles_seed.json to /api/bottles/_bulk on the
#      running backend — idempotent upsert by (brand, label).
#   4. Trigger /inventory/flavor-map/regenerate so the frontend
#      re-runs UMAP + DBSCAN against the new DB state.
#   5. Run `python -m app._tools.calibrate --write` inside the running
#      frontend container against the running backend — produces a fresh
#      cluster_impressions.json on the bind-mounted host path.
#   6. Print which clusters are still flagged TODO so the user knows
#      what to hand-curate before committing.
#   7. Print the suggested `git add` / `git commit` lines. Never auto-
#      commits.
#
# Optional flag:
#   --regen-seed   Also rewrite scripts/seed.sql and db/seed.sql from the
#                  updated bottles_seed.json + iba_cocktails_normalized.json.
#                  Only needed if you care about cold-start parity (the
#                  running DB is already up-to-date via the API call).
#
# Prereqs:
#   - Local stack up via:
#       docker compose -f compose.yaml -f compose.build.yaml up -d
#     (compose.build.yaml exposes backend on 127.0.0.1:8080.)
#   - Frontend container named mix-ml-frontend, backend reachable inside
#     the docker network as http://backend:8080.
#   - python3, curl, jq, docker on PATH.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEED_JSON="$REPO_ROOT/scripts/data/bottles_seed.json"
IMPRESSIONS_JSON="$REPO_ROOT/frontend/app/data/cluster_impressions.json"
BACKEND_HOST="${BACKEND_HOST:-http://127.0.0.1:8080}"
FRONTEND_CONTAINER="${FRONTEND_CONTAINER:-mix-ml-frontend}"

REGEN_SEED=0
INPUT=""
for arg in "$@"; do
    case "$arg" in
        --regen-seed) REGEN_SEED=1 ;;
        -h|--help)
            sed -n '2,33p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        -*)
            echo "Unknown flag: $arg" >&2
            exit 2
            ;;
        *)
            if [[ -n "$INPUT" ]]; then
                echo "Multiple input files given; only one allowed." >&2
                exit 2
            fi
            INPUT="$arg"
            ;;
    esac
done

if [[ -z "$INPUT" ]]; then
    echo "Usage: $0 [--regen-seed] <new_bottle.json>" >&2
    exit 2
fi
if [[ ! -f "$INPUT" ]]; then
    echo "File not found: $INPUT" >&2
    exit 2
fi

# 1. validate JSON shape (class_name resolution happens server-side via _bulk)
python3 - "$INPUT" <<'PY'
import json, sys
path = sys.argv[1]
b = json.loads(open(path).read())
required = {"class_name", "brand", "flavor_profile"}
missing = required - set(b)
if missing:
    sys.exit(f"Missing required keys in {path}: {sorted(missing)}")
fp = b["flavor_profile"]
expected_dims = {
    "sweet", "bitter", "sour", "citrusy", "fruity", "herbal", "floral",
    "spicy", "smoky", "vanilla", "woody", "minty", "earthy", "umami",
    "body", "intensity",
}
fp_missing = expected_dims - set(fp)
if fp_missing:
    sys.exit(f"flavor_profile missing dims: {sorted(fp_missing)}")
print(f"OK: {b['brand']} {b.get('label') or ''} [{b['class_name']}]")
PY

# 2. append to bottles_seed.json (idempotent: skip if same brand+label exists)
python3 - "$INPUT" "$SEED_JSON" <<'PY'
import json, sys
new_path, seed_path = sys.argv[1], sys.argv[2]
new = json.loads(open(new_path).read())
seed = json.loads(open(seed_path).read())
key = (new["brand"], new.get("label"))
for i, b in enumerate(seed):
    if (b["brand"], b.get("label")) == key:
        seed[i] = new
        print(f"Updated existing entry at index {i}")
        break
else:
    seed.append(new)
    print(f"Appended (total bottles: {len(seed)})")
open(seed_path, "w").write(json.dumps(seed, indent=2, ensure_ascii=False) + "\n")
PY

# 3. _bulk upsert
echo "→ POST $BACKEND_HOST/api/bottles/_bulk"
RESPONSE_FILE=$(mktemp)
trap 'rm -f "$RESPONSE_FILE"' EXIT
curl -fsS -X POST "$BACKEND_HOST/api/bottles/_bulk" \
    -H 'Content-Type: application/json' \
    --data-binary "@$SEED_JSON" -o "$RESPONSE_FILE"
python3 - "$RESPONSE_FILE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(f"  inserted={d.get('inserted')} errors={len(d.get('errors', []))}")
if d.get("errors"):
    print("  WARNING: _bulk reported errors:")
    print(json.dumps(d["errors"], indent=2))
    sys.exit(1)
PY

# 4. regenerate flavor map on the frontend
FRONTEND_HOST="${FRONTEND_HOST:-http://127.0.0.1:3000}"
echo "→ GET $FRONTEND_HOST/inventory/flavor-map/regenerate"
curl -fsS -o /dev/null "$FRONTEND_HOST/inventory/flavor-map/regenerate" || \
    echo "  WARNING: frontend regenerate returned non-200 (continuing — calibrate still runs)" >&2

# 5. calibrate inside the frontend container
echo "→ docker exec $FRONTEND_CONTAINER python -m app._tools.calibrate --write"
docker exec --user 0 "$FRONTEND_CONTAINER" \
    python -m app._tools.calibrate \
        --backend-url http://backend:8080 \
        --write \
        --output /opt/app-root/src/app/data/cluster_impressions.json

# 6. surface TODOs
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

# 7. optional seed regen
if [[ "$REGEN_SEED" -eq 1 ]]; then
    echo "→ Regenerating seed.sql"
    cd "$REPO_ROOT/scripts"
    python3 generate_seed_sql.py data/iba_cocktails_normalized.json >/dev/null
    cp seed.sql "$REPO_ROOT/db/seed.sql"
    cd - >/dev/null
fi

# 8. print suggested commit
echo
echo "Done. Suggested commit:"
ADDED_FILES=("scripts/data/bottles_seed.json" "frontend/app/data/cluster_impressions.json")
if [[ "$REGEN_SEED" -eq 1 ]]; then
    ADDED_FILES+=("scripts/seed.sql" "db/seed.sql")
fi
NEW_BOTTLE_DESC=$(python3 -c "import json; b=json.load(open('$INPUT')); print(f\"{b['brand']} {b.get('label') or ''}\".strip())")
echo "  git add ${ADDED_FILES[*]}"
echo "  git commit -m 'feat(bottles): add $NEW_BOTTLE_DESC'"
