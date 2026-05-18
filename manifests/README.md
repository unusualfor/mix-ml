# Kubernetes Manifests

Kustomize manifests for deploying mix-ml on OpenShift Local (CRC) with ArgoCD.

**For overview and quick start, see the [root README](../README.md).**

For full GitOps workflow details, see [OpenShift GitOps Setup (Advanced)](../README.md#openshift-gitops-setup-advanced) in the root README.

## Structure

```
manifests/
├── operators/
│   ├── kustomization.yaml
│   ├── openshift-gitops-subscription.yaml    # Red Hat OpenShift GitOps
│   └── openshift-pipelines-subscription.yaml # Red Hat OpenShift Pipelines
├── argocd/
│   ├── kustomization.yaml
│   └── mix-ml-app.yaml                      # ArgoCD Application CR (watches overlays/crc/)
├── base/
│   ├── kustomization.yaml
│   ├── namespace.yaml                        # mix-ml namespace
│   ├── postgres-secret.yaml                  # WARNING: placeholder (filled by setup-secrets.sh)
│   ├── postgres-pvc.yaml                     # 2Gi RWO persistent volume
│   ├── postgres-deployment.yaml              # PostgreSQL 16
│   ├── postgres-service.yaml                 # ClusterIP port 5432
│   ├── backend-deployment.yaml               # FastAPI backend (ghcr.io images)
│   ├── backend-service.yaml                  # ClusterIP port 8080
│   ├── frontend-deployment.yaml              # HTMX frontend (ghcr.io images)
│   ├── frontend-service.yaml                 # ClusterIP port 8080
│   ├── frontend-route.yaml                   # OpenShift Route with TLS edge
│   ├── seed-job.yaml                         # Manual seed job (run on-demand)
│   └── seed.sql                              # Database seed (102 IBA recipes + bottles)
└── overlays/crc/
    ├── kustomization.yaml
    └── patches/
        ├── resources.yaml                # Postgres CPU/memory limits (CRC-friendly)
        ├── backend-resources.yaml        # Backend resource limits
        └── frontend-resources.yaml       # Frontend resource limits
```

## Key Files

| File | Purpose |
|------|---------|
| `base/kustomization.yaml` | Base resources + common settings |
| `overlays/crc/kustomization.yaml` | CRC-specific patches (1 replica, reduced resources) |
| `argocd/mix-ml-app.yaml` | ArgoCD Application CR (points to overlays/crc/) |
| `base/seed.sql` | Database initialization (idempotent) |

## Kustomize Paths

**Base:** `manifests/base/kustomization.yaml`  
**CRC Overlay:** `manifests/overlays/crc/kustomization.yaml`  
**ArgoCD watches:** `manifests/overlays/crc/` on `main` branch

## Secrets

The `postgres-secret.yaml` file contains placeholder values. Real secrets are injected during bootstrap:

```bash
bash scripts/setup-secrets.sh
```

This creates/updates:
- `postgres-credentials` (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_ADMIN_PASSWORD)
- `github-credentials` (for pushing manifest updates during CI/CD)
- `ghcr-credentials` (for pulling images from ghcr.io)

## Seeding

Database is seeded automatically by an ArgoCD PostSync hook that runs `seed.sql` on every sync. The SQL is idempotent.

To manually seed (one-time):
```bash
oc apply -f manifests/base/seed-job.yaml -n mix-ml
oc logs -f job/seed-job -n mix-ml
```

To update seed data:
1. Edit `scripts/data/bottles_seed.json`
2. Run `cd scripts && python generate_seed_sql.py ...`
3. Copy result to `manifests/base/seed.sql`
4. Commit and push
5. ArgoCD detects change and re-seeds automatically on sync

See [root README: Database Seeding](../README.md#database-seeding) for full workflow.

## GitOps Flow

1. **Developer** edits code/manifests → commit/push to `main`
2. **GitHub** receives push
3. **ArgoCD** polls every 3 minutes, detects change
4. **ArgoCD UI** shows "OutOfSync" (or auto-syncs if enabled)
5. **Human** reviews diff, clicks "Sync"
6. **Kustomize** renders final manifests (base + overlay patches)
7. **kubectl apply** brings cluster to desired state
8. **PostSync hook** runs seed job (idempotent re-seeding)

## Common Tasks

**Apply base manifests only (no GitOps):**
```bash
oc apply -k manifests/base/
```

**Apply CRC overlay (with resource limits):**
```bash
oc apply -k manifests/overlays/crc/
```

**Delete everything:**
```bash
oc delete -k manifests/overlays/crc/
```

**View current Applied Config (what ArgoCD syncs):**
```bash
oc get application mix-ml -n openshift-gitops -o yaml
```

**Watch sync status:**
```bash
oc get application mix-ml -n openshift-gitops --watch
```

---

See [root README: OpenShift GitOps Setup](../README.md#openshift-gitops-setup-advanced) for full initialization and daily workflows.
