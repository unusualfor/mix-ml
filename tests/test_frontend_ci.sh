#!/bin/bash
# Smoke test for frontend-ci pipeline setup.
# Validates that pipeline exists and Tasks are compatible.
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

echo "=== Frontend CI — Smoke Test ==="
echo ""

echo "Pipeline:"
check "Pipeline frontend-ci exists" \
  oc get pipeline frontend-ci -n "$NAMESPACE"
echo ""

echo "Shared Tasks (reused from backend-ci):"
for task in git-clone compute-image-tag python-lint-test buildah-build-push update-manifest; do
  check "Task ${task} exists" \
    oc get task "$task" -n "$NAMESPACE"
done
echo ""

echo "Secrets:"
check "ghcr-credentials exists" \
  oc get secret ghcr-credentials -n "$NAMESPACE"
check "github-credentials exists" \
  oc get secret github-credentials -n "$NAMESPACE"
echo ""

echo "==========================================="
echo "  Results: ${PASS} passed, ${FAIL} failed"
echo "==========================================="

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
