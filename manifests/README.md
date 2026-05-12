# Cocktail DB — Deploy on OpenShift Local (CRC)

PostgreSQL 16 deployment with automatic seeding of 102 IBA recipes on a single-node OpenShift Local cluster.

## Prerequisites

- OpenShift (e.g. OpenShift Local / CRC) running with valid login (`oc whoami` must work)
- `oc` CLI ≥ 4.14
- `kustomize` (built into `oc` via `oc apply -k`)

## Structure

```
manifests/
├── base/
│   ├── kustomization.yaml            # configMapGenerator for seed.sql
│   ├── namespace.yaml
│   ├── postgres-secret.yaml          # ⚠ placeholder credentials
│   ├── postgres-pvc.yaml             # 2Gi RWO
│   ├── postgres-deployment.yaml      # SCL postgresql-16-c9s
│   ├── postgres-service.yaml         # ClusterIP :5432
│   ├── seed-job.yaml                 # Idempotent seed job
│   ├── frontend-deployment.yaml      # Frontend app (2 replicas)
│   ├── frontend-service.yaml         # ClusterIP :8080
│   └── frontend-route.yaml           # OpenShift Route with TLS edge
└── overlays/
    └── crc/
        ├── kustomization.yaml
        └── patches/
            ├── resources.yaml        # 100m-500m CPU, 256Mi-512Mi RAM (postgres)
            └── frontend-resources.yaml # Reduced resources for frontend
```

## Deploy

### 1. Generate real credentials

Edit `manifests/base/postgres-secret.yaml` and replace the placeholders:

```bash
# Generate secure passwords
openssl rand -base64 24   # → POSTGRESQL_PASSWORD
openssl rand -base64 24   # → POSTGRESQL_ADMIN_PASSWORD
```

**Do not commit real credentials to the repo.** For non-demo environments use SealedSecrets or ExternalSecrets.

### 2. Apply manifests

```bash
oc apply -k manifests/overlays/crc/
```

This creates:
- Namespace `cocktail-db`
- Secret with Postgres credentials
- 2Gi PVC
- Postgres Deployment (1 replica, Recreate strategy)
- ClusterIP Service on port 5432
- ConfigMap `postgres-seed` generated from `db/seed.sql`
- Job `postgres-seed` that applies the schema + data
- Frontend Deployment, Service, and Route

### 3. Wait for seed

```bash
oc wait --for=condition=complete job/postgres-seed -n cocktail-db --timeout=180s
```

### 4. Verify

```bash
# Check tables
oc exec deploy/postgres -n cocktail-db -- \
  psql -U cocktailuser -d cocktails -c "\dt"

# Count records
oc exec deploy/postgres -n cocktail-db -- \
  psql -U cocktailuser -d cocktails -c "SELECT 'classes', COUNT(*) FROM ingredient_class UNION ALL SELECT 'recipes', COUNT(*) FROM recipe UNION ALL SELECT 'ingredients', COUNT(*) FROM recipe_ingredient;"
```

## Troubleshooting

### Connect via port-forward

```bash
oc port-forward svc/postgres 5432:5432 -n cocktail-db
# In another terminal:
psql -h localhost -U cocktailuser -d cocktails
```

### Seed Job logs

```bash
# Init container (wait-for-postgres)
oc logs job/postgres-seed -n cocktail-db -c wait-for-postgres

# Main container (seed)
oc logs job/postgres-seed -n cocktail-db -c seed
```

### Postgres logs

```bash
oc logs deploy/postgres -n cocktail-db
```

### Full reset

To redo everything from scratch (schema + data):

```bash
oc delete job postgres-seed -n cocktail-db --ignore-not-found
oc delete pvc postgres-data -n cocktail-db
oc apply -k manifests/overlays/crc/
oc wait --for=condition=complete job/postgres-seed -n cocktail-db --timeout=180s
```

### Job fails with "already seeded"

Expected behavior: the Job checks if `ingredient_class` has rows. If yes, it exits successfully without re-running the seed. To force a re-seed, delete the PVC (see full reset above).

### Job fails with SQL error

```bash
oc logs job/postgres-seed -n cocktail-db -c seed
```

The seed uses `ON_ERROR_STOP=1`: the first SQL error stops execution. Check `db/seed.sql` for syntax errors, then do a full reset.
