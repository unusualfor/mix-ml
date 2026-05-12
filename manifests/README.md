# Cocktail DB — Deploy su OpenShift Local (CRC)

Deploy di PostgreSQL 16 con seed automatico delle 102 ricette IBA su un cluster OpenShift Local single-node.

## Prerequisiti

- CRC running e login valido (`oc whoami` deve funzionare)
- `oc` CLI ≥ 4.14
- `kustomize` (integrato in `oc` via `oc apply -k`)

## Struttura

```
manifests/
├── base/
│   ├── kustomization.yaml            # configMapGenerator per seed.sql
│   ├── namespace.yaml
│   ├── postgres-secret.yaml          # ⚠ credenziali placeholder
│   ├── postgres-pvc.yaml             # 2Gi RWO
│   ├── postgres-deployment.yaml      # SCL postgresql-16-c9s
│   ├── postgres-service.yaml         # ClusterIP :5432
│   └── seed-job.yaml                 # Job idempotente
└── overlays/
    └── crc/
        ├── kustomization.yaml
        └── patches/
            └── resources.yaml        # 100m-500m CPU, 256Mi-512Mi RAM
```

## Deploy

### 1. Generare credenziali reali

Editare `manifests/base/postgres-secret.yaml` e sostituire i placeholder:

```bash
# Genera password sicure
openssl rand -base64 24   # → POSTGRESQL_PASSWORD
openssl rand -base64 24   # → POSTGRESQL_ADMIN_PASSWORD
```

**Non committare credenziali reali nel repo.** Per ambienti non-demo usare SealedSecrets o ExternalSecrets.

### 2. Applicare i manifest

```bash
oc apply -k manifests/overlays/crc/
```

Questo crea:
- Namespace `cocktail-db`
- Secret con credenziali Postgres
- PVC da 2Gi
- Deployment Postgres (1 replica, strategy Recreate)
- Service ClusterIP sulla porta 5432
- ConfigMap `postgres-seed` generata da `db/seed.sql`
- Job `postgres-seed` che applica lo schema + dati

### 3. Attendere il seed

```bash
oc wait --for=condition=complete job/postgres-seed -n cocktail-db --timeout=180s
```

### 4. Verificare

```bash
# Controllare le tabelle
oc exec deploy/postgres -n cocktail-db -- \
  psql -U cocktailuser -d cocktails -c "\dt"

# Output atteso:
#               List of relations
#  Schema |        Name         | Type  |    Owner
# --------+---------------------+-------+--------------
#  public | bottle              | table | cocktailuser
#  public | ingredient_class    | table | cocktailuser
#  public | recipe              | table | cocktailuser
#  public | recipe_ingredient   | table | cocktailuser

# Contare i record
oc exec deploy/postgres -n cocktail-db -- \
  psql -U cocktailuser -d cocktails -c "SELECT 'classes', COUNT(*) FROM ingredient_class UNION ALL SELECT 'recipes', COUNT(*) FROM recipe UNION ALL SELECT 'ingredients', COUNT(*) FROM recipe_ingredient;"
```

## Troubleshooting

### Connettersi via port-forward

```bash
oc port-forward svc/postgres 5432:5432 -n cocktail-db
# In un altro terminale:
psql -h localhost -U cocktailuser -d cocktails
```

### Logs del Job di seed

```bash
# Init container (wait-for-postgres)
oc logs job/postgres-seed -n cocktail-db -c wait-for-postgres

# Container principale (seed)
oc logs job/postgres-seed -n cocktail-db -c seed
```

### Logs di Postgres

```bash
oc logs deploy/postgres -n cocktail-db
```

### Reset completo

Per rifare tutto da zero (schema + dati):

```bash
# Eliminare Job, PVC e riapplicare
oc delete job postgres-seed -n cocktail-db --ignore-not-found
oc delete pvc postgres-data -n cocktail-db
oc apply -k manifests/overlays/crc/
oc wait --for=condition=complete job/postgres-seed -n cocktail-db --timeout=180s
```

### Il Job fallisce con "already seeded"

Comportamento atteso: il Job controlla se `ingredient_class` ha righe. Se sì, esce con successo senza rieseguire il seed. Per forzare il re-seed, eliminare il PVC (vedi reset completo sopra).

### Il Job fallisce con errore SQL

```bash
oc logs job/postgres-seed -n cocktail-db -c seed
```

Il seed usa `ON_ERROR_STOP=1`: il primo errore SQL interrompe l'esecuzione. Controllare `db/seed.sql` per errori di sintassi, poi fare reset completo.
