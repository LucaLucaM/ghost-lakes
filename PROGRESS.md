# Ghost Lakes — unde am rămas (salvat 14 nov 2026)

> **Actualizare:** rezultatele căutării globale și constatarea din Abidjan sunt în `FINDINGS.md`.
> Scripturi noi: `lagoon_infill.py` (umplerea lagunei Ébrié), `vanished.py` (84 de orașe).

## Ce merge
- `ghostlakes.py`: modelul de teren antrenat pe 7 orașe din România. AUC 0.977 în testul leave-one-region-out. Exclude apele vizibile din satelit și din OSM.
  - Rezultate: `outputs/candidates.csv`, `outputs/map.html`, `outputs/metrics.json`
- `validate.py`: test pe 6 bălți secate documentate din București (AUC 0.73). Detaliile sunt în `VALIDATION.md`.
- `inspect_sites.py` + `montage.py`: imagini Landsat vechi vs. Sentinel-2 noi plus istoricul JRC al apei pentru orice listă de puncte.
  - Planșele pentru România sunt în `research/ro_sheet1.png` și `research/ro_sheet2.png`.

## Concluzia verificării manuale a candidaților din România
Nimic nou. Cei mai mulți candidați sunt artefacte sau zone de luncă deja cunoscute:
- București #1 = terenul de fotbal coborât de la Stadionul Dinamo
- București #3 = excavația de lângă Casa Poporului
- Galați și Oradea = carieră sau terasament de cale ferată
- Cluj = zona industrială din lunca Someșului

Niciunul nu are apă în arhiva JRC 1984–2021.

## În lucru: căutarea globală a apelor dispărute (`vanished.py`)
- Caută pixeli văzuți ca apă în 1984–2000 (JRC YearlyHistory), fără apă în 2015–2021 și construiți azi (Dynamic World built ≥ 0.3).
- Are 24 de orașe: 2 de control (Bengaluru, Hyderabad), restul mai puțin studiate (India tier-2, Kano, Niamey, Ouagadougou, Lusaka, Antananarivo, N'Djamena, Erbil, Tashkent etc.).
- Rularea a fost întreruptă când s-a închis sesiunea. Repornește cu `.venv\Scripts\python vanished.py`. Orașele deja scanate sunt salvate în `outputs/vanished/<oraș>.geojson` și nu se recalculează.
- Testul de pe Bengaluru cu pragurile vechi (≥4 ani apă, built ≥ 0.5) a dat 0 zone. Arhiva din anii '80–'90 e rară peste India, iar multe lacuri pierdute au devenit teren gol, nu clădiri. De aceea pragurile sunt acum mai relaxate (≥2 ani, ≥2 ha).

## Pașii următori
1. Termină `vanished.py`. Ia top zonele din `outputs/vanished/all_patches.csv`.
2. Rulează `python osm_check.py <csv id,lat,lon> research/osm.json`. Verifică dacă zona e deja marcată ca apă sau lac în OSM și află numele cartierului.
3. Rulează `python inspect_sites.py <csv> research/<folder>` + `montage.py`. Confirmă de ochi că era apă în imaginile Landsat vechi.
4. Caută pe web cartier + „lake / tank / pond encroached”. Ce nu apare nicăieri e candidat „nedocumentat online”. Formulează cinstit: „nu am găsit nicio mențiune”, nu „descoperire sigură”.
