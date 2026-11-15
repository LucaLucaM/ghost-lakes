# Lagune Ébrié : remblais observés par satellite, 2023–2026
*Fiche d'information indépendante, données satellitaires publiques · Projet « Ghost Lakes » (lycéens, hackathon Veritas AI 2026)*

> **En bref.** Entre début 2023 et novembre 2026, **33 ha de la lagune Ébrié** (environ 46 terrains de football) sont devenus de la terre ferme sur **11 sites** à Abidjan, dont **32 ha à partir de 2024**. Chaque site est confirmé par deux satellites indépendants (optique Sentinel-2 et radar Sentinel-1). **Deux sites (~2 ha) ont été remblayés en mars–avril 2026**, après la mise en garde du ministre du 11 février 2026. Environ **75 000 personnes** vivent à moins de 500 m de ces sites.

**Pourquoi cette fiche ?** Les chiffres publiés jusqu'ici sont des totaux : 453 ha remblayés, 46 sites anciens d'avant 2017, 32 sites depuis 2019 (DGAMP, NCI 360, 1er mars 2026). Ni carte, ni liste de sites, ni dates n'ont été publiées. Cette fiche donne la position, la surface et la période de chaque remblai récent que nous avons pu détecter.

| # | Quartier (OpenStreetMap) | Surface | Terre ferme depuis (optique / radar) | Habitants < 500 m |
|---|---|---|---|---|
| 1 | Vridi | 7,8 ha | 2024-08 / 2025-02 | ~6 400 |
| 2 | Les Grands Moulins | 7,6 ha | 2025-11 / 2025-10 | ~8 800 |
| 3 | Zone 3 | 5,1 ha | 2026-02 / 2025-11 | ~4 100 |
| 4 | Les Grands Moulins | 3,2 ha | 2025-09 / 2024-04 | ~9 000 |
| 5 | Koumassi | 2,6 ha | 2024-04 / 2024-03 | ~19 400 |
| 6 | Vridi | 1,8 ha | 2024-09 / 2024-09 | ~2 200 |
| 7 | M'pouto | 1,4 ha | 2025-12 / 2024-11 | ~1 600 |
| 8 | Koumassi | 1,2 ha | **2026-07 / 2026-04** | ~17 000 |
| 9 | Koumassi | 1,0 ha | 2023-10 / 2023-11 | ~17 700 |
| 10 | Petit Bassam | 0,8 ha | **2026-07 / 2026-04** | ~5 300 |
| 11 | Vridi | 0,6 ha | 2024-04 / 2025-12 | ~4 600 |

Les coordonnées exactes, les contours des sites et les liens vers la carte sont dans `outputs/abidjan/abidjan_sites.csv` et `abidjan_sites.geojson`. Une carte interactive est disponible dans `outputs/abidjan/abidjan_map.html`.

**Méthode.**

- Un site est retenu s'il était de l'eau de lagune depuis des décennies (JRC Global Surface Water ≥ 50 % des observations 1984–2021).
- Il devait encore être de l'eau au 1er semestre 2023 (Google Dynamic World) et être devenu sable ou bâti en 2026.
- Le radar Sentinel-1, qui voit à travers les nuages, devait aussi montrer de l'eau libre en 2023 (≤ −17 dB), puis un signal nettement plus fort (+3 dB ou plus).

**Fiabilité.**

- **Surface :** 98 % de la surface est confirmée par une règle de réflectance indépendante et 91 % par le radar. Le total de 33 ha est plutôt une **estimation basse**, car les remblais de moins de 0,5 ha ne sont pas comptés.
- **Dates :** l'optique et le radar concordent à 3 mois près pour 7 sites. Pour 4 sites (n° 1, 4, 7, 11), l'écart va de 6 à 20 mois : leurs dates sont incertaines.

**Limites importantes.**

- **Nous ne savons pas quels remblais sont autorisés.** Certains sites de Vridi, des Grands Moulins et de la Zone 3 sont en zone portuaire ou industrielle et peuvent être légaux.
- Cette fiche ne désigne aucun responsable. Elle indique seulement où et quand la lagune est devenue terre ferme, et doit être vérifiée sur le terrain.
- Le nombre d'habitants (GHSL 2025) mesure la population qui vit à proximité, pas un dommage.

*Données : Copernicus Sentinel-1 et Sentinel-2 (ESA), Google Dynamic World, JRC Global Surface Water, JRC GHSL, OpenStreetMap. Code ouvert et reproductible : dépôt Ghost Lakes.*
