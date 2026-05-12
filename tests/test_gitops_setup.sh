#!/bin/bash
# Smoke test for GitOps Slice 1 setup.
# Validates that operators, ArgoCD, and the mix-ml Application are running.
#
# Prerequisites: oc CLI logged in, bootstrap-gitops.sh already executed.
set -euo pipefail

NAMESPACE="${NAMESPACE:-mix-ml}"
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

echo "=== GitOps Slice 1 — Smoke Test ==="
echo ""

# 1. Operators installed
echo "Operators:"
check "GitOps operator CSV exists" \
  bash -c "oc get csv -n openshift-operators -o name 2>/dev/null | grep -q openshift-gitops"
check "Pipelines operator CSV exists" \
  bash -c "oc get csv -n openshift-operators -o name 2>/dev/null | grep -q openshift-pipelines"
echo ""

# 2. ArgoCD instance healthy
echo "ArgoCD:"
check "ArgoCD server pod running" \
  bash -c "oc get pods -n openshift-gitops -l app.kubernetes.io/name=openshift-gitops-server --no-headers 2>/dev/null | grep -q Running"
check "ArgoCD route exists" \
  oc get route openshift-gitops-server -n openshift-gitops
echo ""

# 3. Application CR
echo "Application:"
check "mix-ml Application exists" \
  oc get application mix-ml -n openshift-gitops

SYNC_STATUS=$(oc get application mix-ml -n openshift-gitops \
  -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "Unknown")
HEALTH_STATUS=$(oc get application mix-ml -n openshift-gitops \
  -o jsonpath='{.status.health.status}' 2>/dev/null || echo "Unknown")
echo "  Sync status:   $SYNC_STATUS"
echo "  Health status:  $HEALTH_STATUS"

if [[ "$HEALTH_STATUS" == "Healthy" ]]; then
  PASS=$((PASS + 1))
  echo "  PASS: Application healthy"
else
  FAIL=$((FAIL + 1))
  echo "  WARN: Application not Healthy (may need initial sync)"
fi
echo ""

# 4. Target namespace resources (only if synced)
if [[ "$SYNC_STATUS" == "Synced" ]]; then
  echo "Resources in ${NAMESPACE}:"
  check "Postgres deployment exists" \
    oc get deployment postgres -n "$NAMESPACE"
  check "Backend deployment exists" \
    oc get deployment backend -n "$NAMESPACE"
  check "Frontend deployment exists" \
    oc get deployment frontend -n "$NAMESPACE"
  check "Postgres service exists" \
    oc get service postgres -n "$NAMESPACE"
  check "Backend service exists" \
    oc get service backend -n "$NAMESPACE"
  check "Frontend service exists" \
    oc get service frontend -n "$NAMESPACE"
  check "Frontend route exists" \
    oc get route frontend -n "$NAMESPACE"
  echo ""
fi

# Summary
echo "==========================================="
echo "  Results: ${PASS} passed, ${FAIL} failed"
echo "==========================================="

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
