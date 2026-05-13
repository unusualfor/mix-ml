#!/bin/bash
# Full GitOps smoke test — validates the entire stack:
# operators, ArgoCD, Tekton CI (both pipelines), and workloads.
set -euo pipefail

APP_NS="${APP_NS:-mix-ml}"
CI_NS="${CI_NS:-mix-ml-ci}"
GITOPS_NS="${GITOPS_NS:-openshift-gitops}"
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

echo "=== Full GitOps Stack — Smoke Test ==="
echo ""

# 1. Operators
echo "Operators:"
check "GitOps operator CSV" \
  bash -c "oc get csv -n openshift-operators -o name 2>/dev/null | grep -q openshift-gitops"
check "Pipelines operator CSV" \
  bash -c "oc get csv -n openshift-operators -o name 2>/dev/null | grep -q openshift-pipelines"
echo ""

# 2. ArgoCD
echo "ArgoCD (${GITOPS_NS}):"
check "ArgoCD server pod running" \
  bash -c "oc get pods -n ${GITOPS_NS} -l app.kubernetes.io/name=openshift-gitops-server --no-headers 2>/dev/null | grep -q Running"
check "ArgoCD route exists" \
  oc get route openshift-gitops-server -n "$GITOPS_NS"
echo ""

# 3. Application
echo "Application:"
check "mix-ml Application exists" \
  oc get application mix-ml -n "$GITOPS_NS"

SYNC=$(oc get application mix-ml -n "$GITOPS_NS" -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "Unknown")
HEALTH=$(oc get application mix-ml -n "$GITOPS_NS" -o jsonpath='{.status.health.status}' 2>/dev/null || echo "Unknown")
echo "  Sync: $SYNC | Health: $HEALTH"
if [[ "$HEALTH" == "Healthy" ]]; then
  PASS=$((PASS + 1)); echo "  PASS: Application healthy"
else
  FAIL=$((FAIL + 1)); echo "  WARN: Application not Healthy"
fi
echo ""

# 4. Workloads
echo "Workloads (${APP_NS}):"
for dep in postgres backend frontend; do
  check "Deployment ${dep} exists" oc get deployment "$dep" -n "$APP_NS"
done
for svc in postgres backend frontend; do
  check "Service ${svc} exists" oc get service "$svc" -n "$APP_NS"
done
check "Frontend route exists" oc get route frontend -n "$APP_NS"
echo ""

# 5. Tekton CI
echo "Tekton CI (${CI_NS}):"
check "Namespace ${CI_NS} exists" oc get namespace "$CI_NS"
check "ServiceAccount pipeline-bot" oc get serviceaccount pipeline-bot -n "$CI_NS"
check "Secret github-credentials" oc get secret github-credentials -n "$CI_NS"
check "Secret ghcr-credentials" oc get secret ghcr-credentials -n "$CI_NS"

for task in git-clone compute-image-tag python-lint-test buildah-build-push update-manifest; do
  check "Task ${task}" oc get task "$task" -n "$CI_NS"
done

check "Pipeline backend-ci" oc get pipeline backend-ci -n "$CI_NS"
check "Pipeline frontend-ci" oc get pipeline frontend-ci -n "$CI_NS"
echo ""

# Summary
echo "==========================================="
echo "  Results: ${PASS} passed, ${FAIL} failed"
echo "==========================================="

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
