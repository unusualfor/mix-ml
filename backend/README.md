# Mix-ML Backend API

Read-only REST API per il database cocktail IBA, basata su FastAPI + SQLAlchemy + psycopg 3.

## Avvio locale

```bash
cd backend
uv venv && uv pip install -e ".[dev]"

# Port-forward verso il DB su CRC (bind 0.0.0.0 per WSL2)
oc port-forward svc/postgres 5432:5432 -n cocktail-db --address 0.0.0.0 &

# Usa l'IP del Windows host da WSL2
export DATABASE_URL="postgresql+psycopg://cocktailuser:<password>@$(grep nameserver /etc/resolv.conf | awk '{print $2}'):5432/cocktails"
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
| GET | `/api/recipes/{id}/substitutions` | Sostituti per ingredienti mancanti |
| GET | `/api/bottles` | Lista bottiglie personali |
| GET | `/api/bottles/{id}` | Dettaglio bottiglia |
| POST | `/api/bottles` | Crea bottiglia |
| POST | `/api/bottles/bulk` | Bulk upsert bottiglie |
| PUT | `/api/bottles/{id}` | Aggiorna bottiglia |
| DELETE | `/api/bottles/{id}` | Elimina bottiglia |
| GET | `/api/cocktails/can-make-now` | Lista ricette fattibili con inventory corrente |
| GET | `/api/cocktails/{id}/feasibility` | Dettaglio fattibilità per ricetta |
| GET | `/api/cocktails/optimize-next` | Prossima bottiglia che sblocca più ricette |
| GET | `/api/bottles/optimize-shopping` | Piano acquisti ILP multi-step |
| GET | `/api/bottles/optimize-shopping/verify` | Sanity check ILP vs greedy |
| GET | `/api/flavor/distance` | Distanza gustativa tra due bottiglie |
| GET | `/api/flavor/similar-bottles` | Ranking bottiglie simili a un pivot |
| GET | `/api/flavor/substitution-trace` | Debug dettagliato logica sostituzione |

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

## Flavor Distance

La metrica `flavor_distance` calcola una distanza euclidea pesata tra
due `flavor_profile` a 16 dimensioni (valori 0-5). Lo spazio è
suddiviso in:

- **Gustativo** (14 dim): sweet, bitter, sour, citrusy, fruity,
  herbal, floral, spicy, smoky, vanilla, woody, minty, earthy, umami
- **Strutturale** (2 dim): body, intensity

Ogni sotto-distanza è normalizzata in [0, 1], poi combinata:

$$d = w_g \cdot d_{\text{gustativo}} + w_s \cdot d_{\text{strutturale}}$$

Pesi default: $w_g = 0.7$, $w_s = 0.3$ ($w_g + w_s = 1$).

### Endpoint diagnostico

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/api/flavor/distance?bottle_a=<id>&bottle_b=<id>` | Breakdown distanza tra due bottle |

Parametri opzionali: `gustative_weight`, `structural_weight`.
Errori: 404 se una bottle non esiste, 422 se i pesi non sommano a 1.

## Similarity & Substitution

Due endpoint complementari basati su `flavor_distance`:

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/api/flavor/similar-bottles?bottle_id=<id>` | Ranking bottle per distanza da un pivot |
| GET | `/api/recipes/{id}/substitutions` | Sostituti per ingredienti mancanti |
| GET | `/api/flavor/substitution-trace?recipe_id=<id>&recipe_ingredient_id=<id>` | Debug completo logica sostituzione |

### Similar Bottles

Parametri: `top` (default 10), `max_distance`, `same_family_only`.
Ritorna le bottle più vicine al pivot con `top_shared_dimensions` e
`top_differing_dimensions` per spiegare la similarità.

### Substitutions

Per ogni `recipe_ingredient` non soddisfatto:
1. Calcola un **pivot profile** dalla classe richiesta (o dai sibling)
2. Esclude bottle **anti-doppione** (classi già usate nella ricetta)
3. Classifica per **tier**: `strict` (stessa famiglia, ≤ 0.25) o
   `loose` (cross-family, ≤ 0.20)

Parametri: `tier=strict|loose|both`, `strict_threshold`, `loose_threshold`,
`include_satisfied`.

## Multi-step Shopping Optimization

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/api/bottles/optimize-shopping?budget=K` | Piano acquisti ILP a K bottiglie |
| GET | `/api/bottles/optimize-shopping/verify` | Sanity check: ILP(K=1) vs greedy |

Evoluzione dell'endpoint `optimize-next` (greedy K=1): dato un budget di K
bottiglie (max 15), un solver CP-SAT (Google OR-Tools) trova il set di acquisti
che massimizza il numero pesato di ricette IBA fattibili.

**Modello ILP**: variabili booleane `x_c` (compro classe c?), `y_r` (ricetta r
diventa fattibile?). Vincoli: `sum(x) ≤ budget`, per ogni requirement non
soddisfatto di r: `y_r ≤ sum(x_c)` dove c può soddisfarlo (match strict +
wildcard generic). Obiettivo: `max sum(weight[cat] × y_r)`.

**Parametri**: `budget` (1–15), `weight_unforgettable/contemporary/new_era`
(default 1.0), `explain` (false), `solver_timeout_seconds` (30).

**`?explain=true`**: aggiunge `newly_feasible_recipes` (con `covered_by_purchases`)
e `purchases_marginal_value` (decomposizione greedy a posteriori sul piano ottimo).

**`/verify`**: confronta ILP(K=1) con greedy. Se `match: false`, la modellazione
ILP diverge dalla logica di feasibility — indica un bug.

**Timeout**: se il solver non converge, ritorna best-incumbent con
`is_optimal: false`, `solver_status: "FEASIBLE"`.

## Build immagine OCI

```bash
podman build -t mix-ml-backend:latest backend/
```

## Variabili d'ambiente

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://cocktailuser:changeme@localhost:5432/cocktails` | Connection string SQLAlchemy |
| `LOG_LEVEL` | `INFO` | Livello di log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
