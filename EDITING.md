# TC Kooike website — Inhoud bewerken

Handleiding voor bestuursleden en vrijwilligers die de website bijhouden.
Je hebt **geen Python of technische kennis** nodig. Bewerk gewoon een bestand, sla op, push — en de site herbouwt zichzelf automatisch binnen ~2 minuten.

---

## Hoe werkt het? (30 seconden)

1. Alle tekst en data staan in de map `input/` als eenvoudige tekstbestanden (`.md`).
2. Zodra je een bestand aanpast en pusht naar GitHub, start er automatisch een CI-taak.
3. Die taak bouwt `docs/index.html` opnieuw en pusht het resultaat.
4. GitHub Pages serveert dat bestand live op **tckooike.com** — geen extra stappen nodig.

---

## Welke bestanden bewerk je?

| Bestand | Wat het bevat |
|---|---|
| `input/welkom.md` | Welkomsttekst op de homepage + knoppen |
| `input/kalender.md` | Agenda met clubactiviteiten en tornooien |
| `input/interclub.md` | Interclub wedstrijden (datum, ploeg, kapitein) |
| `input/school.md` | Tennisschool — lessen, prijzen, info |
| `input/ladder.md` | Laddercompetitie — FAQ en uitleg |
| `input/bestuur.md` | Bestuurslid namen, rollen en foto's |
| `input/sponsors.md` | Sponsorlogo's met optionele links |
| `input/contact.md` | Adres, e-mail, telefoon, handige links |
| `input/reglement.md` | Clubreglement |
| `input/sfeer.md` | Lijst van sfeerbeelden voor de galerij |

---

## Tekst opmaken

In de `.md`-bestanden gebruik je een eenvoudige opmaaktaal. Hieronder alle mogelijkheden:

| Wat je typt | Resultaat |
|---|---|
| `**woord**` | **vetgedrukt** |
| `[label](https://url)` | klikbare link die opent in nieuw tabblad |
| `[e-mail](mailto:info@voorbeeld.be)` | klikbare e-maillink |
| `[telefoon](tel:+32412345678)` | klikbare telefoonlink |
| `## Hoofding` | gekleurde sectietitel |
| `### Subtitel` | kleinere sectietitel |
| `- item` | punt in een lijst |
| `> tekst` | grijze hulptekst |
| `? Vraag` gevolgd door antwoord | FAQ-blok (vraag + antwoord) |
| `[cta: Knoptekst](https://url)` | grote knop |
| `// dit is een opmerking` | regel wordt **niet** getoond op de site |

> Gebruik **geen HTML-tags** (zoals `<b>` of `<br>`). Die worden niet verwerkt.

---

## Per bestand

### Welkomstpagina (`input/welkom.md`)

De eerste alinea's vormen de welkomsttekst. Na `## Hoe reserveren?` (of een andere `##`-kop) volgen de reservatieknoppen.

```
… een club **voor iedereen**. Beschrijving van de club.

## Hoe reserveren?

[cta: 🎾 Reserveer een terrein](https://www.tennisenpadelvlaanderen.be/...)
[cta: ✅ Word lid](https://www.tennisenpadelvlaanderen.be/...)
```

---

### Kalender (`input/kalender.md`)

Elk evenement begint met `## datum | omschrijving`. Optioneel voeg je een notitieregel toe, en/of een `hide-after:`-datum om de notitie automatisch te verbergen.

```
## 6 april 2026 | Start seizoen 🎉
Terreinreservaties via Tennis & Padel Vlaanderen

## 12 – 21 juni 2026 | Bring a Smile – Tornooi
[Schrijf je hier in!](https://link-naar-inschrijving)
hide-after: 2026-06-12
```

- **datum**: vrije tekst vóór de `|` (bv. `1 mei 2026`, `Maart 2026`, `12 – 21 juni 2026`)
- **omschrijving**: tekst na de `|`
- **notitieregel**: verschijnt als kleine tekst onder het evenement
- **hide-after**: na die datum verdwijnt de notitieregel automatisch (het evenement zelf blijft zichtbaar)

---

### Interclub (`input/interclub.md`)

Elke ploeg begint met `## TYPE | Kapitein | Reeks`. Daarna volgen de wedstrijden als `-`-regels.

```
## TV | Jan Janssens | Heren 4B

- 15/03/2026 14:00 | TC Kooike | TC Riviera
- 22/03/2026 10:00 | TC Westside | TC Kooike
```

- **TYPE**: bv. `TV`, `ART`, `NK`, `BC`
- **Kapitein**: naam van de ploegkapitein
- **Reeks**: bv. `Heren 4B` (optioneel)
- **Wedstrijdregel**: `DD/MM/YYYY UU:MM | thuisclub | bezoekende club`

---

### Tennisschool (`input/school.md`)

Gebruik `## Sectietitel` om secties te scheiden. Daarbinnen gewone tekst, lijsten of tabellen.

```
## Groepslessen kids (6–12 jaar)

| Formule | Prijs |
|---|---|
| 1× per week | € 280/jaar |
| 2× per week | € 480/jaar |

> Lessen worden gegeven door WhackIt.
```

---

### Ladder (`input/ladder.md`)

De ladder-pagina bestaat volledig uit FAQ-blokken. Elk blok: `? Vraag` op één regel, antwoord op de volgende regel(s).

```
? Hoe schrijf ik me in?
Stuur een berichtje naar tckooike@gmail.com.

? Hoe worden punten berekend?
Je krijgt punten op basis van het klassementsverschil met je tegenstander.
```

---

### Bestuur (`input/bestuur.md`)

Eén lid per regel, formaat: `- Naam | Rol | pad/naar/foto.jpg` (foto is optioneel).

```
- Steven De Cuyper | Sponsoring & events | images/bestuur/steven.jpg
- Nieuw Lid       | Secretaris
```

Foto's worden opgeslagen in `docs/images/bestuur/`. Naam het bestand hetzelfde als de voornaam (kleine letters).

---

### Sponsors (`input/sponsors.md`)

Eén sponsor per regel: `- Naam | pad/naar/logo.png | https://website` (website is optioneel).

```
- Mijn Bedrijf | images/sponsors/mijnbedrijf.png | https://mijnbedrijf.be
- Lokale Bakker | images/sponsors/bakker.png
```

Logo's worden opgeslagen in `docs/images/sponsors/`. PNG-formaat, bij voorkeur op transparante achtergrond.

---

### Contact (`input/contact.md`)

Sectie per `## Koptekst`. Regels worden naast elkaar getoond (met regelbreuk). Gebruik e-mail- en telefoonlinks zodat ze klikbaar zijn op mobiel.

```
## 📧 E-mail & Telefoon
[tckooike@gmail.com](mailto:tckooike@gmail.com)
[+32 497 89 14 54 (Steven)](tel:+32497891454)
```

---

### Clubreglement (`input/reglement.md`)

Gewone Markdown-tekst met koppen, lijsten en alinea's. De eerste alinea verschijnt automatisch in een kleinere grijze stijl (inleiding).

---

### Sfeerbeelden (`input/sfeer.md`)

Gebruik `## Sectietitel` om een nieuwe groep foto's te beginnen. Elke foto staat op een `-`-regel met de bestandsnaam (zonder `.jpg`). Optioneel voeg je een CSS `object-position`-waarde toe om het uitsnijpunt in te stellen.

```
## DG-dag 2026
- DG_dag_2026_1 | center 65%
- DG_dag_2026_2
- DG_dag_2026_3 | top
```

De sectietitel verschijnt als label boven de eerste foto van die groep.

---

## Sfeerbeelden toevoegen

1. Bewaar de foto als `.jpg` en geef hem een duidelijke naam (bv. `zomertornooi_2026.jpg`).
2. Sleep het bestand naar `docs/images/sfeer/` via de GitHub-webinterface (of via je git-client).
3. Open `input/sfeer.md` en voeg een regel toe in de juiste sectie:
   ```
   - zomertornooi_2026
   ```
4. Commit en push. De thumbnail wordt automatisch aangemaakt door de CI.

> De bestandsnaam in `sfeer.md` is **zonder extensie** (dus `zomertornooi_2026`, niet `zomertornooi_2026.jpg`).

---

## Commentaarregels

Elke regel die begint met `//` wordt genegeerd en verschijnt niet op de site. Handig om iets tijdelijk uit te zetten zonder het te verwijderen:

```
// ## 1 april 2026 | Grap-evenement (verborgen)
## 1 mei 2026 | Dubbel gemengd dag 👫
```

---

## Na het pushen

Zodra je wijzigingen pusht naar GitHub:

1. GitHub Actions start automatisch (te volgen via het tabblad **Actions** in de repository).
2. De CI draait de tests, bouwt `docs/index.html` opnieuw en pusht het resultaat.
3. Binnen **~2 minuten** is de wijziging live op [tckooike.com](https://tckooike.com).

Als de CI-taak mislukt (rood kruis bij Actions), stuur dan een berichtje naar de technische beheerder — de site blijft dan op de vorige versie staan.
