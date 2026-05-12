#!/bin/bash
# Create Kubernetes secrets for mix-ml. Run BEFORE first ArgoCD sync,
# otherwise Postgres will crash-loop on missing credentials.
#
# Required env vars:
#   POSTGRES_PASSWORD          — Postgres user password
#   POSTGRES_ADMIN_PASSWORD    — Postgres admin password
#
# Optional env vars:
#   NAMESPACE                  — target namespace (default: mix-ml)
#   GITHUB_USERNAME            — for private ghcr.io image pull
#   GITHUB_TOKEN               — GitHub PAT with packages:read scope
#
# Idempotent — safe to re-run (rotates values in place).
set -euo pipefail

NAMESPACE="${NAMESPACE:-mix-ml}"

# Validate required vars
: "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD before running this script}"
: "${POSTGRES_ADMIN_PASSWORD:?Set POSTGRES_ADMIN_PASSWORD before running this script}"

GITHUB_USERNAME="${GITHUB_USERNAME:-}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

echo "=== Mix-ML Secret Setup (namespace: ${NAMESPACE}) ==="
echo ""

# Create namespace if it doesn't exist
oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

# Postgres credentials
echo "Creating postgres-credentials secret..."
oc create secret generic postgres-credentials \
  --namespace="$NAMESPACE" \
  --from-literal=POSTGRESQL_USER=cocktailuser \
  --from-literal=POSTGRESQL_PASSWORD="$POSTGRES_PASSWORD" \
  --from-literal=POSTGRESQL_ADMIN_PASSWORD="$POSTGRES_ADMIN_PASSWORD" \
  --dry-run=client -o yaml | oc apply -f -

# Optional: ghcr.io image pull secret
if [[ -n "$GITHUB_USERNAME" && -n "$GITHUB_TOKEN" ]]; then
  echo "Creating ghcr-pull-secret..."
  oc create secret docker-registry ghcr-pull-secret \
    --namespace="$NAMESPACE" \
    --docker-server=ghcr.io \
    --docker-username="$GITHUB_USERNAME" \
    --docker-password="$GITHUB_TOKEN" \
    --dry-run=client -o yaml | oc apply -f -

  # Link to default SA so deployments can pull
  oc secrets link default ghcr-pull-secret --for=pull -n "$NAMESPACE"
  echo "Pull secret linked to default service account."
fi

echo ""
echo "Secrets configured in namespace ${NAMESPACE}."
echo "You can now run ArgoCD sync."
