# Mix-ML Backend API

Read-only REST API per il database cocktail IBA, basata su FastAPI + SQLAlchemy + psycopg 3.

## Avvio locale

```bash
cd backend
uv venv && uv pip install -e ".[dev]"

# Port-forward verso il DB su CRC
oc port-forward svc/postgres 5432:5432 -n cocktail-db &

export DATABASE_URL="postgresql+psycopg://cocktailuser:<password>@localhost:5432/cocktails"
uvicorn app.main:app --reload
```

L'API è disponibile su `http://localhost:8000`. Docs interattivi: `http://localhost:8000/docs`.

## Endpoint

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/healthz` | Liveness probe |
| GET | `/readyz` | Readiness probe (verifica DB) |
| GET | `/api/classes` | Tassonomia ingredienti (albero o `?flat=true`) |
| GET | `/api/recipes` | Lista ricette con filtri `?category=`, `?search=`, `?limit=`, `?offset=` |
| GET | `/api/recipes/{id}` | Dettaglio ricetta con ingredienti |
| GET | `/api/recipes/by-name?name=` | Dettaglio ricetta per nome (case-insensitive) |

## Test

```bash
# Richiede un DB Postgres raggiungibile (port-forward o locale)
export DATABASE_URL="postgresql+psycopg://cocktailuser:<password>@localhost:5432/cocktails"
pytest tests/ -v
```

I test creano uno schema temporaneo `test_cocktail`, inseriscono dati minimi e lo droppano a fine sessione.

## Assumed-Available Ingredients

The `is_commodity` flag on `ingredient_class` marks ingredients that
the system assumes are always available without requiring them to be
tracked as `bottle` entries. This includes two semantic categories
sharing the same flag for implementation simplicity:

1. **True commodities**: low-cost consumables typically present in
   any kitchen (fresh citrus juices, soda water, sugar, eggs, cream,
   syrups preparable in 2 minutes).
2. **Assumed-available alcoholics**: items the home bar owner
   considers always at hand for hosting purposes, even though they
   are bottled spirits/wines with non-trivial cost (Champagne,
   Prosecco, Red Wine, Dry White Wine).

To track Champagne or Prosecco as actual inventoried bottles (e.g.
distinguishing brut vs demi-sec), the user would need to either:
(a) re-flag the class as non-commodity via SQL, or
(b) introduce a more granular class (e.g. "Brut Champagne",
"Demi-Sec Champagne") with the parent class remaining commodity for
backward compatibility.

## Build immagine OCI

```bash
podman build -t mix-ml-backend:latest backend/
```

## Variabili d'ambiente

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://cocktailuser:changeme@localhost:5432/cocktails` | Connection string SQLAlchemy |
| `LOG_LEVEL` | `INFO` | Livello di log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
