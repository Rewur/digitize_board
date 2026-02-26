# Board Digitizer – Benutzeranleitung

Automatische Digitalisierung von Metaplan- und Workshop-Board-Fotos via OpenRouter Vision API.

---

## 1. Voraussetzungen

### Python-Version
- Python **3.10 oder höher** erforderlich
- Prüfen: `python --version`

### Benötigte Pakete installieren
```bash
pip install -r requirements.txt
```

### OpenRouter-Account & API-Key
1. Account erstellen unter [openrouter.ai](https://openrouter.ai)
2. API-Key generieren unter [openrouter.ai/keys](https://openrouter.ai/keys)
3. Key beginnt mit `sk-or-v1-...`

### Vision-fähige Modelle prüfen
Nicht alle Modelle auf OpenRouter unterstützen Bild-Input.
Alle Vision-Modelle findest du unter: [openrouter.ai/models?modalities=image](https://openrouter.ai/models?modalities=image)

Empfohlene Modelle:
| Modell | Stärke | Geschwindigkeit |
|--------|--------|-----------------|
| `google/gemini-2.0-flash` | Gut für Drucktext, schnell | ⚡ Schnell |
| `anthropic/claude-sonnet-4-5` | Besser bei Handschriften | 🐢 Langsamer |
| `openai/gpt-4o` | Sehr gute Allround-Erkennung | ⚡ Mittel |

---

## 2. Einrichtung (Schritt-für-Schritt)

### Schritt 1: .env Datei erstellen
```bash
cp .env.example .env
```

### Schritt 2: .env befüllen

Öffne `.env` in einem Texteditor:

```ini
# ZWINGEND – ohne diesen Key startet das Skript nicht:
OPENROUTER_API_KEY=sk-or-v1-dein-echter-key-hier

# OPTIONAL – Standardwerte funktionieren out-of-the-box:
DEFAULT_MODEL=google/gemini-2.0-flash
FALLBACK_MODEL=anthropic/claude-sonnet-4-5
OUTPUT_DIR=./output
MAX_TOKENS=4000
```

| Feld | Pflicht? | Standardwert | Beschreibung |
|------|----------|--------------|--------------|
| `OPENROUTER_API_KEY` | **Ja** | – | Dein OpenRouter API-Key |
| `DEFAULT_MODEL` | Nein | `google/gemini-2.0-flash` | Primäres Vision-Modell |
| `FALLBACK_MODEL` | Nein | `anthropic/claude-sonnet-4-5` | Fallback bei Fehler |
| `OUTPUT_DIR` | Nein | `./output` | Ausgabe-Ordner |
| `MAX_TOKENS` | Nein | `4000` | Max. Tokens pro API-Antwort |

### Schritt 3: Verbindung testen
```bash
python digitize_board.py --test
```
Erwartete Ausgabe: `✅ API-Verbindung erfolgreich!`

---

## 3. Grundlegende Nutzung

### Einfachstes Beispiel (ein Bild, keine Optionen)
```bash
python digitize_board.py --image board.jpg
```

### Mit Template-Auswahl
```bash
python digitize_board.py --image retro.jpg --template retrospektive
```

### Mit eigenem Kontext (`--context`)
```bash
python digitize_board.py --image lager_board.jpg \
  --context "Lager-Team Zentrallager, rote Punkte = Priorität, grüne = Zustimmung"
```

### Batch-Verarbeitung eines ganzen Ordners
```bash
python digitize_board.py --batch ./workshop_fotos/ --template ideensammlung
```

### Alle CLI-Parameter im Überblick

| Parameter | Kurzform | Pflicht | Standardwert | Beschreibung |
|-----------|----------|---------|--------------|--------------|
| `--image` | `-i` | Nein* | – | Pfad zu einem Board-Foto |
| `--batch` | `-b` | Nein* | – | Ordner mit mehreren Fotos |
| `--test` | – | Nein | – | API-Verbindungstest |
| `--template` | `-t` | Nein | `custom` | Board-Template wählen |
| `--context` | `-c` | Nein | `""` | Zusätzlicher Kontext-Text |
| `--model` | `-m` | Nein | Aus `.env` | Modell überschreiben |
| `--output` | `-o` | Nein | Aus `.env` | Ausgabe-Ordner überschreiben |
| `--confidence` | – | Nein | `False` | Konfidenz-Scores anzeigen |

*`--image` oder `--batch` oder `--test` wird benötigt.

### Verfügbare Templates

| Template | Verwendung |
|----------|------------|
| `retrospektive` | Was lief gut / schlecht / Maßnahmen |
| `ideensammlung` | Brainstorming, Cluster, Votes |
| `metaplan` | Fragen oben, Antworten als Karten |
| `5s_audit` | Sortieren / Setzen / Säubern / Standardisieren / Selbstdisziplin |
| `custom` | Freier Kontext via `--context "..."` |

---

## 4. Ausgabe-Dateien verstehen

Das Skript erstellt pro Board-Foto **zwei Markdown-Dateien** im Ausgabe-Ordner:

### `{boardname}_Raw.md` – Rohdaten-Transkription
- Enthält die **1:1-Transkription** aller sichtbaren Zettel/Karten
- Tippfehler und Abkürzungen werden **absichtlich beibehalten**
- Dient als unverändertes Primär-Dokument / Protokoll
- Enthält auch die Strukturanalyse (Layout, Farb-Semantik, Votes)

### `{boardname}_Summary.md` – Executive Summary
- Enthält eine **ausformulierte Zusammenfassung** des Board-Inhalts
- Beginnt mit einem Executive Summary (max. 10 Zeilen)
- Darauf folgt ein detaillierter Bericht mit Fließtext
- Abkürzungen sind aufgelöst, Einträge nach Relevanz sortiert

### Ausgabe-Ordner
Standard: `./output/` (konfigurierbar via `OUTPUT_DIR` in `.env` oder `--output`)

### Annotationen im Raw.md

| Annotation | Bedeutung |
|------------|-----------|
| `[unleserlich]` | Text nicht erkennbar |
| `[?]` | Unsichere Erkennung |
| `[?] (Konfidenz: 65%)` | Unsicher + Konfidenz-Score (nur mit `--confidence`) |
| `(3 rote Punkte, 1 grün)` | Voting-/Klebepunkte mit Farbe |
| `(5 Stimmen)` | Votes nach Bereinigung (in Summary) |
| `(Farbe: Rot)` | Farb-Annotation wenn inhaltlich relevant |

---

## 5. Anpassungen & Konfiguration

### a) Modell wechseln (Zeile ~95 in digitize_board.py)

**Wann welches Modell?**
- **Gemini 2.0 Flash**: Standard für gedruckten Text, schnell und günstig
- **Claude Sonnet**: Besser bei schwieriger Handschrift oder gemischten Sprachen
- **GPT-4o**: Sehr gute Allround-Erkennung, höhere Kosten

In `.env` ändern:
```ini
DEFAULT_MODEL=openai/gpt-4o
```

Oder per CLI für einen einzelnen Run:
```bash
python digitize_board.py --image board.jpg --model openai/gpt-4o
```

### b) Eigene Board-Templates hinzufügen (Zeile ~42)

Im Skript das `BOARD_TEMPLATES`-Dictionary erweitern:
```python
BOARD_TEMPLATES: dict[str, str] = {
    # ... bestehende Templates ...
    "kanban": (
        "Dies ist ein Kanban-Board. Spalten: 'To Do', 'In Progress', 'Done'. "
        "Karten repräsentieren Aufgaben/Tickets."
    ),
}
```
Danach auch im `argparse choices`-Parameter ergänzen (Zeile ~230).

### c) System-Prompt erweitern für interne Abkürzungen (Zeile ~57)

Im `SYSTEM_PROMPT_TEMPLATE` oder via `--context`:
```bash
python digitize_board.py --image board.jpg \
  --context "Abkürzungen: ZL=Zentrallager, FS=Frühschicht, SS=Spätschicht,
             MHD=Mindesthaltbarkeitsdatum, WA=Warenausgang, WE=Wareneingang"
```

### d) max_tokens erhöhen bei großen Boards (Zeile ~100)

In `.env`:
```ini
MAX_TOKENS=8000
```
Oder direkt im Skript bei `BoardDigitizer.__init__()` den Standardwert ändern.

### e) Retry-Verhalten anpassen (Zeile ~85)

In der `BoardDigitizer`-Klasse:
```python
MAX_RETRIES = 5          # Mehr Versuche (Standard: 3)
RETRY_BASE_DELAY = 3     # Längere Wartezeit in Sekunden (Standard: 2)
```

### f) Output-Format ändern (nur Raw, nur Summary)

Im `process_board()`-Methode (Zeile ~185): Die jeweiligen `write_text()`-Aufrufe auskommentieren oder bedingt schalten. Beispiel nur Summary:
```python
# raw_path.write_text(...)  # Diese Zeile auskommentieren
```

### g) Sprache des Outputs konfigurieren

Im `SYSTEM_PROMPT_TEMPLATE` (Zeile ~57) hinzufügen:
```python
"Antworte ausschließlich auf Englisch.\n\n"
```
Oder via `--context`:
```bash
python digitize_board.py --image board.jpg --context "Please respond in English only."
```

---

## 6. Fehlerbehebung (Troubleshooting)

| Fehlermeldung / Symptom | Ursache | Lösung |
|-------------------------|---------|--------|
| `OPENROUTER_API_KEY nicht gesetzt` | `.env` fehlt oder Key leer | `.env.example` kopieren, Key eintragen |
| `HTTP 401 Unauthorized` | API-Key ungültig oder abgelaufen | Neuen Key unter [openrouter.ai/keys](https://openrouter.ai/keys) generieren |
| `HTTP 402 Payment Required` | Kein Guthaben im Account | Unter [openrouter.ai/credits](https://openrouter.ai/credits) aufladen |
| `Modell unterstützt kein Vision` | Gewähltes Modell hat kein Bild-Input | Wechseln zu `google/gemini-2.0-flash` oder `anthropic/claude-sonnet-4-5` |
| `Timeout` / sehr langsam | Bild zu groß oder Netzwerk-Problem | Bild komprimieren (max. 5 MB empfohlen), stabiles Netz prüfen |
| Output leer oder `{}` | API-Antwort unvollständig | `MAX_TOKENS` erhöhen, Board in Teile aufteilen |
| `Format nicht unterstützt` | Dateiformat nicht JPG/PNG/WEBP | Bild konvertieren, z.B. `magick input.bmp output.jpg` |
| Viele `[unleserlich]` | Schlechte Fotoqualität | Tipps unter Abschnitt 7 beachten |
| Batch-Modus findet keine Bilder | Groß-/Kleinschreibung der Endung | Dateinamen prüfen (`.JPG` und `.jpg` werden beide erkannt) |

---

## 7. Tipps für beste Ergebnisse

### Optimale Foto-Bedingungen
- **Licht**: Gleichmäßige, blendfreie Ausleuchtung (kein Gegenlicht)
- **Winkel**: Möglichst frontal (< 15° Neigung)
- **Auflösung**: Mindestens 1920×1080px; 12 MP oder mehr empfohlen
- **Abstand**: Gesamtes Board soll vollständig im Bild sein
- **Schärfe**: Zoom nutzen statt Ausschneiden – Schärfe bleibt erhalten

### Wann welches Modell wählen?
| Situation | Empfehlung |
|-----------|------------|
| Klarer Druck, viele Farben, schnell | `google/gemini-2.0-flash` |
| Schwierige Handschrift | `anthropic/claude-sonnet-4-5` |
| Gemischte Sprachen (DE/EN) | `anthropic/claude-sonnet-4-5` |
| Höchste Präzision, Budget egal | `openai/gpt-4o` |

### `--context` effektiv nutzen
Je mehr Kontext, desto besser die Erkennung von Abkürzungen und Farbcodierungen:
```bash
python digitize_board.py --image board.jpg \
  --context "Retro-Meeting Lager-Team KW12.
             Rote Punkte = Priorität (1 Punkt = 1 Stimme).
             Abkürzungen: ZL=Zentrallager, FS=Frühschicht,
             SS=Spätschicht, MHD=Mindesthaltbarkeitsdatum."
```

### Mehrteilige Boards (mehrere Fotos)
Bei sehr großen Boards mehrere Fotos machen und im Batch verarbeiten:
```bash
python digitize_board.py --batch ./retro_board/
```
Anschließend die einzelnen `_Summary.md`-Dateien manuell zusammenführen.

---

## 8. Beispiel-Workflow (End-to-End)

### Szenario: "Retro Lager-Team KW12"

**CLI-Befehl:**
```bash
python digitize_board.py \
  --image retro_lager_kw12.jpg \
  --template retrospektive \
  --context "Lager-Team Zentrallager Berlin, KW12. Rote Punkte = Votes (1=1 Stimme). ZL=Zentrallager, FS=Frühschicht, SS=Spätschicht" \
  --output ./output/kw12/ \
  --confidence
```

**Erwartete `retro_lager_kw12_Raw.md`:**
```markdown
# Rohdaten-Transkription: retro_lager_kw12

**Erstellt:** 2026-02-26 14:30
**Modell:** google/gemini-2.0-flash
**Template:** retrospektive

---

## Strukturanalyse

**Layout-Typ:** 3 Spalten (Spalten-Layout)
**Farb-Semantik:** Gelbe Zettel = neutral/allgemein; keine weiteren Farbkodierungen erkennbar
**Voting-Punkte:** 12 rote Klebepunkte insgesamt
**Verbindungen:** Pfeil von "Kommunikation verbessern" → "Tägliches Standup einführen"

---

## Transkription

## Was lief gut? ✅

* Neue Scannergeräte funktionierten problemlos
* FS und SS haben sich gut abgesprochen (2 rote Punkte)
* MHD-Kontrolle jetzt digitalisiert (4 rote Punkte)
* Teamstimmung positiv

## Was lief schlecht? ❌

* Kommunikation zw. FS und SS mangelhaft (5 rote Punkte)
* [unleserlich] Palettenplätze oft falsch belegt
* Überstunden in KW11 unnötig hoch [?] (Konfidenz: 70%)

## Maßnahmen 🎯

* Tägliches Standup einführen (3 rote Punkte) → (Farbe: Rot)
* Palettenplan aktualisieren – verantwortlich: Holger
* FS-SS Übergabeprotokoll erstellen
```

**Erwartete `retro_lager_kw12_Summary.md`:**
```markdown
# Executive Summary: retro_lager_kw12

**Erstellt:** 2026-02-26 14:32
**Modell:** google/gemini-2.0-flash
**Template:** retrospektive

---

### Executive Summary

Das Lager-Team des Zentrallagers identifizierte in der Retrospektive für KW12
die **mangelnde Kommunikation zwischen Früh- und Spätschicht** als dringlichstes
Problem (5 Stimmen). Positiv hervorzuheben ist die erfolgreiche Digitalisierung
der MHD-Kontrolle (4 Stimmen). Als zentrale Gegenmaßnahme wurde die Einführung
eines täglichen Standups priorisiert (3 Stimmen).

### Detaillierter Bericht

#### Was lief gut

Die Einführung neuer Scannergeräte verlief reibungslos und wurde vom Team positiv
aufgenommen. Die digitalisierte MHD-Kontrolle war der meistgelobte Fortschritt
der Woche (4 Stimmen). Die Abstimmung zwischen Früh- und Spätschicht funktionierte
in dieser Woche vergleichsweise gut.

#### Verbesserungsbedarf

Die Kommunikation zwischen Früh- und Spätschicht wurde als größtes Problem
benannt und erhielt mit 5 Stimmen die höchste Priorität. Fehler bei der
Palettenbelegung führten zu zusätzlichem Aufwand.

#### Maßnahmen (nach Priorität)

1. **Tägliches Standup einführen** (3 Stimmen) – Die Kommunikationsprobleme
   zwischen den Schichten führten direkt zur Priorisierung dieser Maßnahme.
2. **Übergabeprotokoll FS↔SS erstellen** – Strukturierte Übergabe soll
   Informationsverluste vermeiden.
3. **Palettenplan aktualisieren** – Verantwortlich: Holger.
```

---

*Generiert mit [Board Digitizer v1.0.0](https://github.com/local/board-digitizer)*
