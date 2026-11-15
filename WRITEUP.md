# Ghost Lakes: A ban on paper, sand in the water
*AI and 40 years of free satellite data to find water that cities bury, and a protected lagoon that kept shrinking.* · Track: Climate · Team of 2 high-school students

> In 2023 Côte d'Ivoire suspended the filling-in of Abidjan's Ébrié lagoon. From space, we watched **33 ha of it (≈46 football pitches) turn into land at 11 sites**, 32 ha of it from 2024 on. Every site was confirmed by two independent satellites.

**Problem.** Buried water does not disappear: it floods the new neighbourhood in heavy rain and stops recharging groundwater. These losses are rarely mapped. *Can AI and free satellite archives find buried water and say when it vanished?*

**Approach** (Google Earth Engine, free data only).

1. **Terrain AI: where water *should* be.** A Random Forest trained on 23,000 points from 7 Romanian regions, with 10 terrain features and JRC water labels.
2. **Archive detector: where water *was*.** Water seen by Landsat before 2010, dry since 2015, built-up today. We ran it on 84 cities.
3. **Infill monitor: where water is disappearing *now*.** Dynamic World 2023 vs 2026, every hit confirmed by Sentinel-1 radar (which sees through clouds) and dated. One command runs it on any place.
4. **Human review of every hit:** old vs new imagery, OpenStreetMap, news and papers.

**Results.**

- **The terrain AI generalises across regions:** AUC 0.977 when trained on 6 regions and tested on the 7th. Alone, it cannot find water bodies that vanished completely (AUC 0.57 on 4 documented ones in Bucharest), which is why we built steps 2–3.
- **The archive detector rediscovers known lost lakes on its own:**
    - Kalikiliki Dam, Lusaka (water until 2005, dry from 2007; a 2007 study says it was "allowed to dry up" in late 2006), Parangipalya Lake under Bengaluru's HSR Layout, and the filled lakes of Phnom Penh.
- **Abidjan, Ébrié lagoon.** Officials gave only totals: 453 ha filled overall, "dozens of hectares" despite the suspension, and infill that "continues in several sectors". **No site locations, maps or dates were published.**
    - We mapped **11 sites, 33.0 ha**, each lagoon water for decades, optically water in 2023 and sand in 2026, and 4–7 dB brighter on radar.
    - **How sure are we?** Inside our polygons, 98% of the area is confirmed by a raw-reflectance rule and 91% by radar. Both independent methods also find changes just outside our edges, so 33 ha is a conservative estimate.
    - **Two sites (~2 ha) were filled in March–April 2026**, after the minister's 11 February warning. Radar still saw open water there on 14 March and 7 April, and land from mid-April; the optical data agree.
    - **About 75,000 people live within 500 m of these sites** (GHSL 2025), mostly in flood-prone Koumassi.
- **Global screen of ~120 cities, every hit checked by eye:** 23 of 29 radar-confirmed patches (79%; 95% by area) are real infill. Outside Abidjan they are mostly known port and coastal projects (Manila Bay, Colombo, Dakar). The other 6 are moving rivers or beaches, plus Herăstrău (Bucharest), drained for works.
- **Blind world scan (no cherry-picking):** only 503 of 26,336 urban ~11 km cells on Earth lost long-standing water in 2023–26, and most of the largest are official ports. **Abidjan surfaced without being named**, one of only two cities (with Lagos) filling lagoon water inside neighbourhoods.

![Ébrié lagoon, Abidjan, 2023 vs 2026](outputs/abidjan/before_after_compact.png)
*Vridi / Grands Moulins, Sentinel-2, 2023 vs 2026: inside each red outline, lagoon water became sand (26 of the 33 ha). All sites, timelapse and map: see the repository.*

**Limitations.**

- We cannot tell which fills were authorised; Vridi port works may be legal.
- Dates: optical and radar agree within 3 months for 7 sites but differ by 6–20 months for 4. Fills under 0.5 ha are not counted.
- Officials already know infill happens. Our contribution is public, independent, site-level evidence and dates, not to our knowledge published before.
- In Romania we found no new lost lakes (top candidates were artefacts, e.g. a sunken stadium pitch).

**Next.** Share the site list (and the French brief) with local journalists and lagoon authorities for ground checks, and run the monitor monthly. Code, tests and every number: see the repository's `RESULTS.ipynb`. *Data:* JRC GSW, Dynamic World, Sentinel-1/2, Landsat 5, FABDEM, MERIT Hydro, GHSL, OpenStreetMap.
