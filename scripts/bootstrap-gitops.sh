#!/bin/bash
# Bootstrap GitOps infrastructure on OpenShift Local (CRC).
# Installs Red Hat OpenShift GitOps + Pipelines operators,
# waits for ArgoCD, grants permissions, and creates the Application CR.
#
# Prerequisites: oc CLI logged in as cluster-admin (kubeadmin on CRC).
# Idempotent — safe to re-run.
set -euo pipefail

echo "=== Mix-ML GitOps Bootstrap ==="
echo ""

# 1. Verify cluster-admin login
echo "Checking oc login..."
oc whoami || { echo "ERROR: Not logged in. Run: oc login -u kubeadmin" ; exit 1; }
echo ""

# 2. Install operators (idempotent — Subscription CR is declarative)
echo "Installing OpenShift GitOps and Pipelines operators..."
oc apply -k manifests/operators/
echo ""

# 3. Wait for GitOps operator CSV to succeed
echo "Waiting for GitOps operator to install (up to 5 min)..."
for i in $(seq 1 60); do
  CSV=$(oc get csv -n openshift-operators -o name 2>/dev/null \
    | grep openshift-gitops || true)
  if [[ -n "$CSV" ]]; then
    PHASE=$(oc get "$CSV" -n openshift-operators \
      -o jsonpath='{.status.phase}' 2>/dev/null || true)
    if [[ "$PHASE" == "Succeeded" ]]; then
      echo "GitOps operator installed: $CSV"
      break
    fi
  fi
  sleep 5
done
echo ""

# 4. Wait for ArgoCD server deployment
echo "Waiting for ArgoCD server to be ready (up to 5 min)..."
oc wait --for=condition=Available --timeout=300s \
  deployment/openshift-gitops-server -n openshift-gitops
echo ""

# 5. Grant ArgoCD permission to manage resources in mix-ml namespace
echo "Granting ArgoCD cluster-admin access..."
oc adm policy add-cluster-role-to-user cluster-admin \
  system:serviceaccount:openshift-gitops:openshift-gitops-argocd-application-controller \
  2>/dev/null || true
echo ""

# 6. Create the ArgoCD Application CR
echo "Creating mix-ml ArgoCD Application..."
oc apply -k manifests/argocd/
echo ""

# 7. Print ArgoCD UI access info
ARGOCD_URL=$(oc get route openshift-gitops-server -n openshift-gitops \
  -o jsonpath='{.spec.host}' 2>/dev/null || echo "UNKNOWN")
ARGOCD_PASSWORD=$(oc get secret openshift-gitops-cluster -n openshift-gitops \
  -o jsonpath='{.data.admin\.password}' 2>/dev/null | base64 -d || echo "UNKNOWN")

echo "==========================================="
echo "  ArgoCD Bootstrap Complete"
echo "==========================================="
echo ""
echo "  URL:      https://${ARGOCD_URL}"
echo "  Username: admin"
echo "  Password: ${ARGOCD_PASSWORD}"
echo ""
echo "  Next steps:"
echo "    1. Run scripts/setup-secrets.sh (if not done already)"
echo "    2. Open ArgoCD UI"
echo "    3. Find the 'mix-ml' application"
echo "    4. Click 'Sync' to deploy"
echo "    5. After pods are healthy, seed the database:"
echo "       oc delete job postgres-seed -n mix-ml --ignore-not-found"
echo "       oc apply -f manifests/base/seed-job.yaml -n mix-ml"
echo ""
