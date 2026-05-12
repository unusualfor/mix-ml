# Mix-ML — Kubernetes Manifests

Kustomize manifests for deploying mix-ml on OpenShift Local (CRC), managed by ArgoCD.

## Structure

```
manifests/
├── operators/
│   ├── kustomization.yaml
│   ├── openshift-gitops-subscription.yaml    # Red Hat OpenShift GitOps
│   └── openshift-pipelines-subscription.yaml # Red Hat OpenShift Pipelines
├── argocd/
│   ├── kustomization.yaml
│   └── mix-ml-app.yaml                      # ArgoCD Application CR
├── base/
│   ├── kustomization.yaml
│   ├── namespace.yaml                        # mix-ml namespace
│   ├── postgres-secret.yaml                  # ⚠ placeholder (real values via setup-secrets.sh)
│   ├── postgres-pvc.yaml                     # 2Gi RWO
│   ├── postgres-deployment.yaml              # SCL postgresql-16-c9s
│   ├── postgres-service.yaml                 # ClusterIP :5432
│   ├── backend-deployment.yaml               # FastAPI backend (ghcr.io)
│   ├── backend-service.yaml                  # ClusterIP :8080
│   ├── frontend-deployment.yaml              # HTMX frontend (ghcr.io)
│   ├── frontend-service.yaml                 # ClusterIP :8080
│   ├── frontend-route.yaml                   # OpenShift Route with TLS edge
│   ├── seed-job.yaml                         # Manual seed job (not in kustomization)
│   └── seed.sql                              # Database seed data
└── overlays/
    └── crc/
        ├── kustomization.yaml
        └── patches/
            ├── resources.yaml                # Postgres resource limits for CRC
            ├── backend-resources.yaml        # Backend resource limits for CRC
            └── frontend-resources.yaml       # Frontend resource limits for CRC
```

## GitOps Flow

ArgoCD watches `manifests/overlays/crc/` on the `main` branch.

1. Edit manifests → commit → push to `main`
2. ArgoCD detects changes (click "Refresh")
3. Click "Sync" to apply to cluster
4. ArgoCD reconciles desired state with live state

**Seed job** is intentionally excluded from Kustomize resources.
It is applied manually when needed: `oc apply -f manifests/base/seed-job.yaml -n mix-ml`.

**Secrets** are placeholders in Git. Real values injected by `scripts/setup-secrets.sh`.
ArgoCD `ignoreDifferences` prevents overwriting live secrets with placeholders.

## Bootstrap

See root README "Deployment & GitOps" section, or run:

```bash
bash scripts/setup-secrets.sh     # secrets first
bash scripts/bootstrap-gitops.sh  # operators + ArgoCD app
```

## Troubleshooting

### Connect via port-forward

```bash
oc port-forward svc/postgres 5432:5432 -n mix-ml
psql -h localhost -U cocktailuser -d cocktails
```

### Logs

```bash
oc logs deploy/postgres -n mix-ml
oc logs deploy/backend -n mix-ml
oc logs deploy/frontend -n mix-ml
oc logs job/postgres-seed -n mix-ml -c seed
```

### Full reset

```bash
oc delete job postgres-seed -n mix-ml --ignore-not-found
oc delete pvc postgres-data -n mix-ml
# Then sync via ArgoCD to recreate PVC + deployment
# Re-apply seed job manually
oc apply -f manifests/base/seed-job.yaml -n mix-ml
```
