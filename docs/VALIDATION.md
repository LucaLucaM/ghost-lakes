# Ghost Lakes — validare (notițe pentru write-up)

## 1. Model: generalizare între regiuni (leave-one-region-out)

Antrenat pe 6 regiuni, testat pe a 7-a, pentru fiecare regiune pe rând. Etichete: JRC Global Surface Water 1984–2021, doar pe teren neconstruit. Seturile de test sunt echilibrate 50/50 apă/uscat, așa că cifrele sunt mai optimiste decât ar fi la prevalența reală.

| Regiune testată | AUC | F1 |
|---|---|---|
| București | 0.974 | 0.919 |
| Timișoara | 0.982 | 0.933 |
| Iași | 0.986 | 0.929 |
| Cluj | 0.987 | 0.834 |
| Galați | 0.975 | 0.909 |
| Craiova | 0.986 | 0.936 |
| Oradea | 0.948 | 0.884 |
| **Media** | **0.977** | **0.906** |

## 2. Test pe lacuri secate documentate (București)

**Versiune corectată (15 nov), fără leakage.** Prima versiune antrena modelul și pe regiunea București, iar acolo intrau și lacurile actuale din Cișmigiu și Tineretului, așa că rezultatul ieșea umflat (AUC 0,73). Acum modelul e antrenat **doar pe celelalte 6 regiuni** și n-a văzut niciun pixel din București. Comparăm cu 1500 de pixeli de **uscat** aleși la întâmplare din oraș, adică tot ce nu e apă azi (mediana p = 0,11).

| Loc documentat | Grup | p(apă) | Poziție în oraș |
|---|---|---|---|
| Balta Cocioc (Tineretului) | lac existent azi | 0,50 | top 4% |
| Balta lui Dura (Cișmigiu) | lac existent azi | 0,40 | top 8% |
| Pârâul Bucureștioara (Colțea → Unirii) | dispărut complet | 0,25 | top 20% |
| Pârâul Dâmbovicioara (Calea Rahovei) | dispărut complet | 0,18 | top 30% |
| Balta Icoanei (secată 1873) | dispărut complet | 0,13 | top 44% |
| Balta de la Carvasara | dispărut complet | 0,05 | top 78% |

**AUC pe cele 4 locuri dispărute complet: 0,57**, aproape de întâmplare. Pe toate 6 e 0,69, iar pe cele 2 unde mai există un lac e 0,94.

Interpretare cinstită:
- Pentru apele dispărute complet, un model bazat **doar pe forma terenului** e slab. Cel mult prinde ceva din lunca Dâmboviței (Bucureștioara, Dâmbovicioara).
- **Ratează bălțile de pe platou**, cum e Balta Icoanei, care era alimentată de izvor.
- Scorurile bune de la Cișmigiu și Tineretului vin în mare parte din lacurile de azi.
- De aceea constatările principale vin din **arhiva din satelit** (JRC, Dynamic World, radar), nu din modelul de teren.
- Coordonatele sunt aproximative și avem doar 6 locuri, deci e un indiciu, nu o dovadă.

Surse:
- https://www.bucharest.ro/articles/the-bucurestioara-stream-where-does-the-vanished-tributary-of-the-dambovita-flow-today-1498
- https://skia.one.ro/en/blog/the-waters-that-shape-bucharest/
- https://en.wikipedia.org/wiki/Lake_Ci%C8%99migiu

## 3. Hărți istorice
Am încercat Arcanum (ridicările militare austriece). Fără abonament, imaginea e prea neclară pentru verificarea la nivel de stradă. Alternative gratuite de încercat: Planurile directoare de tragere (proiectul eHarta de pe geo-spatial.org) și planurile vechi ale Bucureștiului, Borroczyn 1852 și Pappasoglu 1871, de pe Wikimedia Commons.
