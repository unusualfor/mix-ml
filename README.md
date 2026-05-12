# IBA Cocktails — Scraper & Analisi

Scarica le ricette ufficiali IBA (International Bartenders Association) dal sito [iba-world.com](https://iba-world.com) e le salva in un file JSON strutturato, poi analizzale.

## Requisiti

- Python 3.11+
- `requests`
- `beautifulsoup4`

## Installazione

```bash
pip install requests beautifulsoup4
```

## Utilizzo

```bash
python scrape_iba.py
```

Lo script:

1. Scarica la pagina indice con tutte le ricette IBA
2. Visita ogni pagina ricetta (con 2s di pausa tra le richieste)
3. Estrae nome, categoria, ingredienti, metodo e guarnizione
4. Salva tutto in `iba_cocktails.json` (ordinato alfabeticamente)

### Idempotenza

Se `iba_cocktails.json` esiste già, lo script salta le ricette già presenti. Utile per riprendere uno scraping interrotto.

## Output

File `iba_cocktails.json` — array di oggetti con struttura:

```json
{
  "name": "Negroni",
  "iba_category": "unforgettable",
  "ingredients": [
    {"amount": 30, "unit": "ml", "name": "Gin"},
    {"amount": 30, "unit": "ml", "name": "Bitter Campari"},
    {"amount": 30, "unit": "ml", "name": "Sweet Red Vermouth"}
  ],
  "method": "Pour all ingredients directly into chilled old fashioned glass filled with ice. Stir gently.",
  "garnish": "Garnish with half orange slice.",
  "source_url": "https://iba-world.com/iba-cocktail/negroni/"
}
```

### Categorie IBA

| Chiave JSON      | Nome sul sito            |
|------------------|--------------------------|
| `unforgettable`  | The Unforgettables       |
| `contemporary`   | Contemporary Classics    |
| `new_era`        | New Era                  |

### Parsing ingredienti

| Pattern nel testo           | `amount` | `unit`  | `name`                |
|-----------------------------|----------|---------|-----------------------|
| `30 ml Gin`                 | `30`     | `"ml"`  | `"Gin"`               |
| `2 dashes Angostura`        | `2`      | `"dash"`| `"Angostura"`         |
| `Few Dashes Bitters`        | `null`   | `"dash"`| `"Bitters"`           |
| `1 bar spoon Sugar`         | `1`      | `"bsp"` | `"Sugar"`             |
| `2 tsp Sugar syrup`         | `2`      | `"tsp"` | `"Sugar syrup"`       |
| `2 Maraschino cherries`     | `2`      | `"whole"`| `"Maraschino cherries"`|
| `Champagne to top`          | `null`   | `"top"` | `"Champagne"`         |
| `Soda Water` (bare name)    | `null`   | `null`  | `"Soda Water"`        |

---

## Analisi descrittiva

### Utilizzo

```bash
python analyze_iba.py iba_cocktails.json
```

Nessuna dipendenza oltre la standard library (Python 3.11+).

### Output

Lo script produce 5 report:

| File | Contenuto |
|------|-----------|
| `report_ingredient_frequency.csv` | Frequenza di ogni ingrediente unico, con lista ricette |
| `report_unit_inventory.csv` | Unità di misura presenti, frequenza, esempio |
| `report_amount_anomalies.txt` | Casi con amount null/zero/non numerico |
| `report_ingredient_clusters.txt` | Cluster di nomi simili (candidati a merge) |
| `report_summary.md` | Overview: categorie, top-20 ingredienti, glassware, tecniche |

Tutti i report sono anche stampati su stdout durante l'esecuzione.
