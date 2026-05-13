#!/bin/bash
# Trigger both backend-ci and frontend-ci pipelines in parallel.
# Useful for coordinated releases where both images change.
#
# Prerequisites:
#   - bootstrap-ci.sh and setup-ci-secrets.sh already run
#   - tkn CLI installed
set -euo pipefail

GIT_URL="${GIT_URL:-https://github.com/unusualfor/mix-ml.git}"
GIT_BRANCH="${GIT_BRANCH:-$(git branch --show-current)}"
NAMESPACE="${NAMESPACE:-mix-ml-ci}"

echo "=== Triggering backend + frontend pipelines in parallel ==="
echo "  Repo:   $GIT_URL"
echo "  Branch: $GIT_BRANCH"
echo ""

# Start backend pipeline
echo "→ Starting backend-ci..."
tkn pipeline start backend-ci \
  --namespace "$NAMESPACE" \
  --serviceaccount pipeline-bot \
  --param git-url="$GIT_URL" \
  --param git-revision="$GIT_BRANCH" \
  --workspace name=shared,volumeClaimTemplateFile=manifests/ci/pvc-template.yaml \
  --workspace name=docker-credentials,secret=ghcr-credentials \
  --output name &
BACKEND_PID=$!

# Start frontend pipeline
echo "→ Starting frontend-ci..."
tkn pipeline start frontend-ci \
  --namespace "$NAMESPACE" \
  --serviceaccount pipeline-bot \
  --param git-url="$GIT_URL" \
  --param git-revision="$GIT_BRANCH" \
  --workspace name=shared,volumeClaimTemplateFile=manifests/ci/pvc-template.yaml \
  --workspace name=docker-credentials,secret=ghcr-credentials \
  --output name &
FRONTEND_PID=$!

# Wait for both triggers
wait $BACKEND_PID || echo "  Backend pipeline trigger failed"
wait $FRONTEND_PID || echo "  Frontend pipeline trigger failed"

echo ""
echo "Both pipelines triggered. Watch progress with:"
echo "  tkn pipelinerun list -n $NAMESPACE"
echo "  tkn pipelinerun logs <name> -f -n $NAMESPACE"
echo ""
echo "Or in OpenShift console: Pipelines → $NAMESPACE"
