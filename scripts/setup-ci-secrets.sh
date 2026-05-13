#!/bin/bash
# Create Kubernetes secrets for the CI pipeline.
# Run ONCE (or to rotate credentials) BEFORE triggering pipelines.
#
# Required env vars:
#   GITHUB_USERNAME   — GitHub username
#   GITHUB_TOKEN      — GitHub PAT with repo + write:packages scope
#
# Idempotent — safe to re-run (overwrites existing secrets).
set -euo pipefail

NAMESPACE="${NAMESPACE:-mix-ml-ci}"

: "${GITHUB_USERNAME:?Set GITHUB_USERNAME before running this script}"
: "${GITHUB_TOKEN:?Set GITHUB_TOKEN (PAT with repo + write:packages scope)}"

echo "=== Mix-ML CI Secret Setup (namespace: ${NAMESPACE}) ==="
echo ""

# Ensure namespace exists
oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

# GitHub credentials for git clone + push
echo "Creating github-credentials secret..."
oc create secret generic github-credentials \
  --namespace="$NAMESPACE" \
  --type=kubernetes.io/basic-auth \
  --from-literal=username="$GITHUB_USERNAME" \
  --from-literal=password="$GITHUB_TOKEN" \
  --dry-run=client -o yaml | \
  oc annotate --local -f - tekton.dev/git-0=https://github.com -o yaml | \
  oc apply -f -

# ghcr.io registry credentials
echo "Creating ghcr-credentials secret..."
oc create secret docker-registry ghcr-credentials \
  --namespace="$NAMESPACE" \
  --docker-server=ghcr.io \
  --docker-username="$GITHUB_USERNAME" \
  --docker-password="$GITHUB_TOKEN" \
  --dry-run=client -o yaml | oc apply -f -

# Link secrets to the pipeline service account
echo "Linking secrets to pipeline-bot SA..."
oc secrets link pipeline-bot github-credentials -n "$NAMESPACE" 2>/dev/null || \
  echo "  (SA pipeline-bot not yet created — run bootstrap-ci.sh first, then re-run this script)"
oc secrets link pipeline-bot ghcr-credentials -n "$NAMESPACE" 2>/dev/null || true

echo ""
echo "CI secrets configured in ${NAMESPACE}."
echo "Next: bash scripts/bootstrap-ci.sh"
