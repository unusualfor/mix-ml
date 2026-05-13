#!/bin/bash
# Trigger the backend-ci Tekton pipeline manually.
# Builds, tests, pushes image, and updates manifests.
#
# Prerequisites:
#   - bootstrap-ci.sh and setup-ci-secrets.sh already run
#   - tkn CLI installed
set -euo pipefail

GIT_URL="${GIT_URL:-https://github.com/unusualfor/mix-ml.git}"
GIT_BRANCH="${GIT_BRANCH:-$(git branch --show-current)}"
NAMESPACE="${NAMESPACE:-mix-ml-ci}"

echo "=== Triggering backend-ci pipeline ==="
echo "  Repo:   $GIT_URL"
echo "  Branch: $GIT_BRANCH"
echo ""

tkn pipeline start backend-ci \
  --namespace "$NAMESPACE" \
  --serviceaccount pipeline-bot \
  --param git-url="$GIT_URL" \
  --param git-revision="$GIT_BRANCH" \
  --workspace name=shared,volumeClaimTemplateFile=manifests/ci/pvc-template.yaml \
  --workspace name=docker-credentials,secret=ghcr-credentials \
  --showlog
