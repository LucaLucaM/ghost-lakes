# Ghost Lakes — ce am găsit (14–15 nov 2026)

> **Notă:** jurnalul folosește numele vechi ale scripturilor (`lagoon_infill.py`, `abidjan_accuracy.py` etc.). Din 15 nov. tot codul e în pachetul `ghostlakes/` și rulează cu `python run.py ...` (vezi README).


> **Cât de bune sunt estimările (15 nov, `abidjan_accuracy.py`):**
> - **Suprafața, verificată independent în interiorul celor 11 poligoane:**
>   - 98% (32,5 ha) e confirmat de o regulă simplă de reflectanță Sentinel-2: apă = NIR < 0,10; uscat = NIR și SWIR > 0,15.
>   - 91% (30,1 ha) e confirmat de radar; ambele metode împreună confirmă 29,8 ha.
>   - Cu o margine de 20 m, metodele independente găsesc ~44–46 ha, deci 33 ha e o estimare prudentă.
>   - MNDWI a fost încercat întâi și respins: în laguna tulbure și în compozitele cu ceață, apa deschisă are MNDWI ≈ −0,1…−0,2, ca uscatul.
> - **Sensibilitatea la praguri:** 20–47 ha pentru pragurile 0,6–0,7. Cu pragul 0,8 iese 0, pentru că Dynamic World rar dă probabilitate de apă ≥ 0,8 în această lagună.
> - **Datele (optic vs radar):**
>   - Concordă în cel mult 3 luni la 7 locuri: #2, #3, #5, #6, #8, #9, #10.
>   - Diferă cu 6–20 de luni la 4 locuri: #1, #4, #7, #11. Pentru ele dăm intervale, nu o lună precisă.
>   - #8 și #10 sunt sigure: radarul vede apă pe 7 aprilie și 14 martie 2026 și uscat de la jumătatea lui aprilie, deci umplere în martie–aprilie 2026, după avertismentul din 11 februarie.
> - **Oameni:** ~75.000 la cel mult 500 m de locuri și ~314.000 la cel mult 1 km (GHSL 2025), mai ales în Koumassi.
> - **Ce au publicat oficialii** (interviul DGAMP pe NCI 360, 1 martie 2026): 453 ha umplute în total (110 regulate, 343 neregulate), 46 de locuri vechi de dinainte de 2017, 32 după 2019, iar BRISRA a oprit 36 de locuri. Au numit Koumassi, Cocody, Marcory și golful Biétry. **Nicio hartă, nicio listă de locuri, nicio dată.**
>
> **Actualizare după code review (15 nov):**
> - **Pipeline-ul Abidjan e reproductibil.** `lagoon_infill.py` aplică singur confirmarea radar, cu aceeași regulă ca `radar_check.py` (11/11), și dă 11 locuri / 33,0 ha.
> - **Calendarul ignoră acum pixelii cu nori.** Înainte erau numărați ca −1. S-a schimbat doar #4: uscat din 2025-09, nu din 2025-01.
> - **32 ha s-au umplut din 2024 încoace.** ~1 ha (Koumassi, 2023-10) e posibil de dinainte de suspendare.
> - **Validarea din București e refăcută fără leakage.** Pe apele dispărute complet, AUC e 0,57, aproape de întâmplare. Detalii în `VALIDATION.md`.
>
> **Actualizare 15 nov:**
> - **Abidjan, confirmat cu radar Sentinel-1:** 11 din 12 locuri, **33,0 ha**. #12 era alarmă falsă: radarul îl vede tot apă, așa că l-am scos. Tabelul de mai jos e versiunea veche, cu 12 locuri. Lista curentă e `outputs/abidjan_infill.geojson`, iar cea veche e salvată în `*_optical_all.*`.
> - **Scanarea umplerilor 2023→2026 pe ~120 de orașe (`recent_infill.py`):** tot ce a găsit în afara Abidjanului e cunoscut sau natural:
>   - proiecte mari de umplere din mare: Manila, Colombo Port City, portul Dakar;
>   - râuri și plaje care se mută: Padma la Rajshahi, Krishna la Vijayawada, Lima;
>   - Herăstrău, golit în iunie 2026 pentru lucrări (documentat);
>   - un iaz de ~1,3 ha umplut în ansamblul privat Star City din Yangon, probabil pentru casele „Estella” (nedocumentat, dar puțin interesant).
> - **După ordinul Prim-ministrului din iunie 2026 (`abidjan_radar_recent.py`):** radarul a dat 20 de zone, dar verificarea optică arată că majoritatea sunt bărci, vegetație sau apă tulbure. Doar ~1,7 ha sunt plauzibile (#7, #13 și #18: Vridi/Zone 3 și Koumassi, august–septembrie 2026). Dovada e slabă.

## TL;DR
- **România:** nimic nou. Cei 16 candidați ai modelului de teren sunt artefacte (de ex. terenul coborât de la Stadionul Dinamo, excavația de lângă Casa Poporului, o carieră, terasamente) sau lunci deja cunoscute. Niciunul nu apare ca apă în arhiva din satelit 1984–2021.
- **Detectorul global de ape dispărute** (`vanished.py`, 84 de orașe) **regăsește corect lacuri documentate.** Asta e validarea metodei:
  - **Lacul Parangipalya** (Bengaluru), documentat ca fiind sub HSR Layout.
  - **Barajul Kalikiliki** (Lusaka). Nchito (2007) scrie că în noiembrie 2006 barajul „fusese lăsat să sece”. Arhiva JRC arată, independent, apă permanentă până în 2005, apă sezonieră în 2006 și uscat din 2007. Azi locul e acoperit de case.
  - **Lacurile umplute din Phnom Penh** (Boeung Kak și altele), bine cunoscute.
- **Constatare nouă, după căutările noastre:** harta și calendarul umplerii lagunei Ébrié din Abidjan **după suspendarea oficială din 2023**. Vezi mai jos.

## Constatarea principală: lagună umplută în Abidjan după suspendarea din 2023

**Ce e deja public:**
- Februarie 2026: ministrul Transporturilor spune că umplerile sunt suspendate din 2023, dar că „zeci de hectare” au fost totuși umplute. Anunță sancțiuni și sesizarea procurorului.
- 11 iunie 2026: Prim-ministrul ordonă oprirea imediată a umplerilor neautorizate.
- 10 septembrie 2026: presa scrie că umplerea ilegală „continuă în mai multe sectoare”.

**Ce nu am găsit online:** nicio sursă nu dă **locațiile, suprafețele sau datele** umplerilor de după 2023.

**Ce am măsurat** (`lagoon_infill.py`, Dynamic World, ianuarie–iunie 2023 vs. aprilie–noiembrie 2026, doar pe lagună permanentă cu JRC occurrence ≥ 50%):
- **34,4 ha de lagună transformată în uscat (nisip sau construcții), în 12 locuri ≥ 0,5 ha.**
- Fiecare loc e verificat de ochi pe Sentinel-2: apă întunecată în 2023, platformă de nisip în 2026. Imaginile sunt în `research/abidjan_infill_sheet.png`.
- Luna umplerii vine din seria lunară Dynamic World (`outputs/abidjan_infill_timing.json`).

| # | Zonă | ha | Ultima lună cu apă | Prima lună uscat |
|---|---|---|---|---|
| 1 | Vridi | 7,79 | 2024-03 | 2024-08 |
| 2 | Les Grands Moulins | 7,55 | 2025-09 | 2025-11 |
| 3 | Zone 3 | 5,12 | 2024-11 | 2026-02 |
| 4 | Les Grands Moulins | 3,17 | 2024-11 | 2025-01 |
| 5 | Koumassi | 2,55 | 2023-05 | 2024-04 |
| 6 | Vridi | 1,82 | 2024-05 | 2024-09 |
| 7 | M'pouto (după Nominatim) | 1,36 | 2024-03 | 2025-12 |
| 8 | Koumassi | 1,23 | **2026-03** | **2026-07** |
| 9 | Koumassi | 1,03 | 2023-05 | 2023-10 |
| 10 | Petit Bassam | 0,77 | **2026-02** | **2026-07** |
| 11 | Vridi | 0,65 | 2024-01 | 2024-04 |
| 12 | Port-Bouët | 0,54 | **2026-03** | **2026-09** |

**De reținut:** locurile #8, #10 și #12 (~2,5 ha) au devenit uscat **după** avertismentul ministrului din februarie 2026. Două dintre ele (#8 și #10) aveau încă apă la începutul lui 2026 și erau uscat în iulie 2026, adică în jurul ordinului Prim-ministrului din 11 iunie.

**Limite (cinstit):**
- Nu putem ști care umpleri sunt **autorizate**. Vridi, Grands Moulins și Zone 3 sunt zone portuare și industriale. Acolo pot fi lucrări legale ale portului, iar presa menționează 110 ha de amenajări regulate, mai ales în perimetrul Portului Autonom. Koumassi, Petit Bassam, Port-Bouët și M'pouto sunt mai probabil private.
- Datele lunare au goluri din cauza norilor (Abidjan e foarte înnorat), deci luna e aproximativă, ±1–2 luni.
- Pragul de 0,5 ha și filtrul strict ratează umplerile mici. 34 ha e o **limită inferioară**.
- „Nedocumentat online” înseamnă că nu am găsit nimic în căutările noastre, în franceză și engleză. Nu e o garanție.

## Piste rămase
- **Nellore (India):** cartierul Revenue Colony / Chandrababu Nagar pare construit pe albia unui lac sezonier, iar malul de sud al lacului mare din Nellore pare ocupat. APSAC are rapoarte oficiale „Mapping of Urban Tanks”, dar site-ul nu se deschide din rețeaua noastră. **De verificat de voi** dacă se deschide: https://apsac.ap.gov.in/wp-content/uploads/2025/01/Nellore/SPS%20Nellore.pdf
- **Bujumbura:** malul lacului Tanganyika (apă până în ~2003, construit azi). Pare variația nivelului lacului plus construcții pe mal.
- **Scanarea celor 60 de orașe** s-a oprit la 35 de orașe. Restul se reia cu `python -c "import vanished as v; v.main(list(v.CENTRES))"`.

## Surse
- Nchito, W. S. (2007), *Flood risk in unplanned settlements in Lusaka*, Environment & Urbanization 19(2): https://journals.sagepub.com/doi/10.1177/0956247807082835
- Lusaka Times (2023), *Lusaka Floods, Our Leaders to Blame*: https://www.lusakatimes.com/2023/02/12/lusaka-floods-our-leaders-to-blame/
- Bengaluru lost lakes: https://30stades.com/environment/bengaluru-43-lost-lakes-and-what-stands-on-them-today-water-crisis-4435946
- Fratmat / AllAfrica (feb 2026), ministrul Koné despre suspendarea din 2023: https://fr.allafrica.com/stories/202602130183.html
- Ivoireactu (10 sep 2026), umplerea ilegală continuă: https://www.ivoireactu.net/abidjan-malgre-les-mises-en-garde-de-letat-le-dragage-illegal-de-la-lagune-ebrie-continue/
- Afriqueinfos (mar 2026): https://afriqueinfos.net/2026/03/04/cote-divoire-lagune-ebrie-letat-serre-la-vis-contre-le-remblayage-illegal/
- Rural21, Soweto Remblais / Adjahui: https://www.rural21.com/english/a-closer-look-at/detail/article/land-reclamation-for-housing-the-example-of-cote-divoire.html
