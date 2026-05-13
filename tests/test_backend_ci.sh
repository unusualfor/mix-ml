#!/bin/bash
# Smoke test for backend-ci pipeline setup.
# Validates that namespace, SA, secrets, tasks, and pipeline exist.
set -euo pipefail

NAMESPACE="${NAMESPACE:-mix-ml-ci}"
PASS=0
FAIL=0

check() {
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "  PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $desc"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Backend CI — Smoke Test ==="
echo ""

# Namespace
echo "Infrastructure:"
check "Namespace ${NAMESPACE} exists" \
  oc get namespace "$NAMESPACE"
check "ServiceAccount pipeline-bot exists" \
  oc get serviceaccount pipeline-bot -n "$NAMESPACE"
echo ""

# Secrets
echo "Secrets:"
check "github-credentials exists" \
  oc get secret github-credentials -n "$NAMESPACE"
check "ghcr-credentials exists" \
  oc get secret ghcr-credentials -n "$NAMESPACE"
echo ""

# Tasks
echo "Tasks:"
for task in git-clone compute-image-tag python-lint-test buildah-build-push update-manifest; do
  check "Task ${task} exists" \
    oc get task "$task" -n "$NAMESPACE"
done
echo ""

# Pipeline
echo "Pipeline:"
check "Pipeline backend-ci exists" \
  oc get pipeline backend-ci -n "$NAMESPACE"
echo ""

# Summary
echo "==========================================="
echo "  Results: ${PASS} passed, ${FAIL} failed"
echo "==========================================="

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
