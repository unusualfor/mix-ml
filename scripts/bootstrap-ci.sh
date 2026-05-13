#!/bin/bash
# Bootstrap the Tekton CI pipeline resources on the cluster.
# Creates namespace, service account, RBAC, tasks, and pipeline.
#
# Prerequisites:
#   - oc CLI logged in as cluster-admin
#   - OpenShift Pipelines operator installed (Slice 1)
set -euo pipefail

echo "=== Bootstrapping CI pipeline resources ==="
echo ""

# Apply all CI manifests via kustomize
echo "Applying manifests/ci/..."
oc apply -k manifests/ci/

# Wait for service account to be ready
echo "Waiting for pipeline-bot SA..."
oc wait --for=jsonpath='{.metadata.name}'=pipeline-bot \
  serviceaccount/pipeline-bot -n mix-ml-ci --timeout=30s

echo ""
echo "Tekton CI ready."
echo ""
echo "Next steps:"
echo "  1. Configure CI secrets: bash scripts/setup-ci-secrets.sh"
echo "  2. Trigger a build:      bash scripts/build-backend.sh"
echo "  3. Watch in OpenShift console > Pipelines > mix-ml-ci"
