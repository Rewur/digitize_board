"""
================================================================================
digitize_board.py
--------------------------------------------------------------------------------
Beschreibung : Automatische Digitalisierung von Metaplan- und Workshop-Board-
               Fotos via OpenRouter API. Generiert strukturierte Markdown-Dateien
               (Rohdaten + Executive Summary) aus Board-Fotografien.
Autor        : [Autor-Platzhalter]
Version      : 1.0.0
Datum        : 2026-02-26
================================================================================
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
import os

# ---------------------------------------------------------------------------
# Logging-Konfiguration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("digitize_board.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Board-Kontext-Templates
# ---------------------------------------------------------------------------
BOARD_TEMPLATES: dict[str, str] = {
    "retrospektive": (
        "Dies ist ein Retrospektiven-Board. Typische Kategorien: "
        "'Was lief gut', 'Was lief schlecht', 'Maßnahmen/Action Items'. "
        "Achte auf Voting-Punkte zur Priorisierung von Maßnahmen."
    ),
    "ideensammlung": (
        "Dies ist ein Ideensammlungs-Board (Brainstorming). "
        "Zettel sind in thematische Cluster gruppiert. "
        "Klebepunkte/Votes zeigen Priorisierung der Ideen."
    ),
    "metaplan": (
        "Dies ist ein Metaplan-Board. Fragen stehen oben, "
        "Antworten als Karten darunter. Spalten strukturieren die Themen."
    ),
    "5s_audit": (
        "Dies ist ein 5S-Audit-Board. Die 5 Kategorien: "
        "Sortieren / Setzen / Säubern / Standardisieren / Selbstdisziplin. "
        "Bewertungen oder Maßnahmen sind den Kategorien zugeordnet."
    ),
    "custom": "",  # Wird per --context befüllt
}

# ---------------------------------------------------------------------------
# System-Prompt-Template
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_TEMPLATE = """Du bist ein Experte für die Digitalisierung von Workshop-Boards und Metaplan-Wänden.

{context_section}

Analysiere das Bild nach folgendem strikten Ablauf:

### SCHRITT 1 – STRUKTURANALYSE
1. Beschreibe zuerst die Struktur: Spalten, Cluster, Matrix, Freiform oder Mindmap?
2. Haben die Farben der Zettel eine erkennbare Bedeutung? (z.B. Gelb=Fakten, Grün=Ideen, Rot=Kritik)
   Falls unklar: schreibe "generisch".
3. Gibt es Voting-Punkte/Klebepunkte? Wenn ja, zähle sie exakt nach Farbe und Position.
4. Dokumentiere Verbindungen: Pfeile oder Linien zwischen Zetteln.

### SCHRITT 2 – TRANSKRIPTION
Erstelle ein Markdown das die erkannte Struktur abbildet:
- Spalten → ## Überschriften
- Cluster → ## Cluster-Titel + verschachtelte Listen
- Zettel → * Listenpunkte (Text 1:1, inkl. Abkürzungen & Tippfehler)
- Unleserliches → [unleserlich] oder [?]
- Votes/Punkte → in Klammern: (3 rote Punkte, 1 grüner Punkt)
- Farben wenn relevant → (Farbe: Rot) als Annotation{confidence_section}

### SCHRITT 5 – QUALITÄTSEINSCHÄTZUNG
Gib am Ende eine Gesamteinschätzung deiner Erkennungsqualität ab (0-100%) und begründe sie kurz."""

CONFIDENCE_SECTION = """
- Unsichere Erkennungen → mit [?] markieren und Konfidenz in Prozent angeben: [?] (Konfidenz: 65%)"""

# ---------------------------------------------------------------------------
# Hauptklasse
# ---------------------------------------------------------------------------

class BoardDigitizer:
    """
    Digitalisiert Workshop-Board-Fotos via OpenRouter Vision API.

    Verarbeitet Bilder in vier Schritten:
    1. Strukturanalyse
    2. Rohdaten-Transkription (_Raw.md)
    3. Bereinigung & Anreicherung
    4. Synthese / Executive Summary (_Summary.md)
    """

    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp"}
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 2  # Sekunden (exponential backoff)

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_model: str,
        output_dir: Path,
        max_tokens: int = 4000,
        template: str = "custom",
        context: str = "",
        confidence: bool = False,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.output_dir = output_dir
        self.max_tokens = max_tokens
        self.template = template
        self.context = context
        self.confidence = confidence

        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    def _encode_image(self, image_path: Path) -> tuple[str, str]:
        """
        Kodiert ein Bild als Base64-String.

        Returns:
            Tuple (base64_string, mime_type)
        """
        suffix = image_path.suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(suffix, "image/jpeg")

        with open(image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        logger.debug(f"Bild kodiert: {image_path.name} ({mime_type})")
        return encoded, mime_type

    def _build_context_section(self) -> str:
        """Erstellt den Kontext-Abschnitt für den System-Prompt."""
        template_text = BOARD_TEMPLATES.get(self.template, "")

        if self.template == "custom" and self.context:
            template_text = f"Board-Kontext: {self.context}"
        elif self.context:
            template_text = f"{template_text}\n\nZusätzlicher Kontext: {self.context}"

        if template_text:
            return f"Board-Kontext:\n{template_text}\n"
        return ""

    def _call_api(
        self,
        messages: list[dict],
        model: Optional[str] = None,
    ) -> str:
        """
        Führt einen API-Call durch mit Retry-Logik und Fallback.

        Args:
            messages: Liste der Chat-Nachrichten
            model: Modell-ID (überschreibt self.model)

        Returns:
            Antwort-Text des Modells

        Raises:
            RuntimeError: Wenn alle Versuche fehlschlagen
        """
        used_model = model or self.model
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info(f"API-Call (Versuch {attempt}/{self.MAX_RETRIES}) mit Modell: {used_model}")

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/local/board-digitizer",
                    "X-Title": "Board Digitizer",
                }

                payload = {
                    "model": used_model,
                    "messages": messages,
                    "max_tokens": self.max_tokens,
                }

                response = requests.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                response.raise_for_status()

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info(f"API-Call erfolgreich. Tokens verwendet: {data.get('usage', {})}")
                return content

            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(f"Timeout bei Versuch {attempt}. Warte {self.RETRY_BASE_DELAY ** attempt}s...")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_BASE_DELAY ** attempt)

            except requests.exceptions.HTTPError as e:
                last_exception = e
                status_code = e.response.status_code if e.response else "?"
                error_body = e.response.text if e.response else ""

                if status_code == 401:
                    raise RuntimeError(
                        "API-Key ungültig oder nicht gesetzt. "
                        "Prüfe OPENROUTER_API_KEY in der .env Datei."
                    ) from e
                elif status_code == 402:
                    raise RuntimeError(
                        "Unzureichendes Guthaben im OpenRouter-Account. "
                        "Bitte Konto aufladen unter https://openrouter.ai/credits"
                    ) from e
                elif status_code == 400 and "vision" in error_body.lower():
                    raise RuntimeError(
                        f"Modell '{used_model}' unterstützt kein Vision/Bild-Input. "
                        "Wechsle zu google/gemini-2.0-flash oder anthropic/claude-sonnet-4-5"
                    ) from e
                elif status_code in (429, 503):
                    logger.warning(f"Rate-Limit/Service unavailable (HTTP {status_code}). Warte...")
                    if attempt < self.MAX_RETRIES:
                        time.sleep(self.RETRY_BASE_DELAY ** attempt)
                else:
                    logger.error(f"HTTP-Fehler {status_code}: {error_body[:500]}")
                    if attempt < self.MAX_RETRIES:
                        time.sleep(self.RETRY_BASE_DELAY)

            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(f"Verbindungsfehler bei Versuch {attempt}: {e}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_BASE_DELAY ** attempt)

        # Fallback auf alternatives Modell
        if used_model != self.fallback_model:
            logger.warning(
                f"Alle {self.MAX_RETRIES} Versuche mit '{used_model}' fehlgeschlagen. "
                f"Wechsle zu Fallback-Modell: {self.fallback_model}"
            )
            return self._call_api(messages, model=self.fallback_model)

        raise RuntimeError(
            f"Alle {self.MAX_RETRIES} API-Versuche fehlgeschlagen. "
            f"Letzter Fehler: {last_exception}"
        )

    def _build_vision_message(self, image_b64: str, mime_type: str, prompt: str) -> list[dict]:
        """Erstellt eine Vision-API-Nachricht mit Bild und Text."""
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_b64}"
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ]

    # ------------------------------------------------------------------
    # Öffentliche Verarbeitungs-Methoden
    # ------------------------------------------------------------------

    def analyze_structure(self, image_b64: str, mime_type: str) -> str:
        """
        Schritt 1: Analysiert die Struktur des Boards (Layout, Farben, Votes).

        Args:
            image_b64: Base64-kodiertes Bild
            mime_type: MIME-Typ des Bildes

        Returns:
            Struktur-Analyse als Text
        """
        logger.info("Starte Strukturanalyse...")

        context_section = self._build_context_section()
        confidence_section = CONFIDENCE_SECTION if self.confidence else ""

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            context_section=context_section,
            confidence_section=confidence_section,
        )

        prompt = (
            "Führe NUR Schritt 1 (STRUKTURANALYSE) durch. "
            "Beschreibe Layout-Typ, Farb-Semantik, Voting-Punkte und Verbindungen. "
            "Sei präzise und strukturiert."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            *self._build_vision_message(image_b64, mime_type, prompt),
        ]

        result = self._call_api(messages)
        logger.info("Strukturanalyse abgeschlossen.")
        return result

    def transcribe_raw(self, image_b64: str, mime_type: str, structure_analysis: str) -> str:
        """
        Schritt 2: Erstellt die Rohdaten-Transkription (_Raw.md).

        Args:
            image_b64: Base64-kodiertes Bild
            mime_type: MIME-Typ des Bildes
            structure_analysis: Ergebnis aus analyze_structure()

        Returns:
            Rohdaten-Markdown als Text
        """
        logger.info("Starte Rohdaten-Transkription...")

        context_section = self._build_context_section()
        confidence_section = CONFIDENCE_SECTION if self.confidence else ""

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            context_section=context_section,
            confidence_section=confidence_section,
        )

        prompt = (
            f"Die Strukturanalyse hat folgendes ergeben:\n\n{structure_analysis}\n\n"
            "Führe nun Schritt 2 (TRANSKRIPTION) durch. "
            "Transkribiere ALLE Zettel/Karten 1:1, inklusive Tippfehler und Abkürzungen. "
            "Nutze die erkannte Struktur als Gliederung (## für Spalten/Cluster, * für Zettel). "
            "Annotiere Voting-Punkte und relevante Farben."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            *self._build_vision_message(image_b64, mime_type, prompt),
        ]

        result = self._call_api(messages)
        logger.info("Rohdaten-Transkription abgeschlossen.")
        return result

    def clean_and_enrich(self, raw_content: str, structure_analysis: str) -> str:
        """
        Schritt 3: Bereinigt und reichert die Rohdaten an.

        Args:
            raw_content: Inhalt der _Raw.md
            structure_analysis: Strukturanalyse für Kontext

        Returns:
            Bereinigter und angereicherter Markdown-Text
        """
        logger.info("Starte Bereinigung & Anreicherung...")

        context_section = self._build_context_section()

        prompt = (
            f"{context_section}\n"
            "Du erhältst eine Rohdaten-Transkription eines Workshop-Boards. "
            "Führe folgende Bereinigungen durch:\n\n"
            "1. Löse Abkürzungen auf (NUR wenn Kontext eindeutig, sonst belassen)\n"
            "2. Sortiere Einträge absteigend nach Votes/Stimmen (falls vorhanden)\n"
            "3. Entferne Farb-Annotationen wenn inhaltlich irrelevant (Noise Reduction)\n"
            "4. Reduziere Klebepunkte auf Zahlenwerte: '(3 rote Punkte, 1 grün)' → '(4 Stimmen)'\n"
            "5. Behalte die Markdown-Struktur (##, *) bei\n\n"
            f"Strukturkontext:\n{structure_analysis}\n\n"
            f"Rohdaten:\n\n{raw_content}"
        )

        messages = [{"role": "user", "content": prompt}]
        result = self._call_api(messages)
        logger.info("Bereinigung & Anreicherung abgeschlossen.")
        return result

    def synthesize_summary(self, cleaned_content: str, structure_analysis: str) -> str:
        """
        Schritt 4: Erstellt die Executive Summary (_Summary.md).

        Args:
            cleaned_content: Bereinigter Inhalt aus clean_and_enrich()
            structure_analysis: Strukturanalyse für Kontext

        Returns:
            Summary-Markdown als Text
        """
        logger.info("Starte Synthese / Executive Summary...")

        context_section = self._build_context_section()
        template_hint = BOARD_TEMPLATES.get(self.template, "")

        prompt = (
            f"{context_section}\n"
            f"Board-Template: {self.template}\n"
            f"{f'Template-Kontext: {template_hint}' if template_hint else ''}\n\n"
            "Erstelle eine strukturierte _Summary.md aus den bereinigten Board-Daten.\n\n"
            "## Pflicht-Struktur der Summary:\n\n"
            "### Executive Summary (max. 10 Zeilen)\n"
            "- Kernaussage 'in a nutshell'\n"
            "- Top 1-2 Themen oder Beschlüsse\n"
            "- Größte Hürde oder Kontroverse (falls erkennbar)\n\n"
            "### Detaillierter Bericht\n"
            "- Stichpunkte → ausformulierte, vollständige Sätze\n"
            "- Strukturiert nach Themenbereichen aus der Analyse\n"
            "- Pfeile/Verbindungen verbalisieren: 'Thema A führt zu Thema B'\n"
            "- Absteigende Sortierung nach Relevanz/Votes\n\n"
            f"Strukturanalyse:\n{structure_analysis}\n\n"
            f"Bereinigte Daten:\n\n{cleaned_content}"
        )

        messages = [{"role": "user", "content": prompt}]
        result = self._call_api(messages)
        logger.info("Synthese abgeschlossen.")
        return result

    def process_board(self, image_path: Path) -> tuple[Path, Path]:
        """
        Orchestriert alle 4 Verarbeitungsschritte für ein Board-Foto.

        Args:
            image_path: Pfad zum Bild-File

        Returns:
            Tuple (raw_md_path, summary_md_path)

        Raises:
            ValueError: Bei nicht unterstütztem Dateiformat
            FileNotFoundError: Wenn Bild nicht existiert
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Bild nicht gefunden: {image_path}")

        if image_path.suffix.lower() not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Format nicht unterstützt: {image_path.suffix}. "
                f"Erlaubt: {', '.join(self.SUPPORTED_FORMATS)}"
            )

        board_name = image_path.stem
        raw_path = self.output_dir / f"{board_name}_Raw.md"
        summary_path = self.output_dir / f"{board_name}_Summary.md"

        logger.info(f"{'='*60}")
        logger.info(f"Verarbeite Board: {image_path.name}")
        logger.info(f"Template: {self.template} | Modell: {self.model}")
        logger.info(f"{'='*60}")

        # Bild kodieren
        image_b64, mime_type = self._encode_image(image_path)

        # Schritt 1: Strukturanalyse
        structure_analysis = self.analyze_structure(image_b64, mime_type)

        # Schritt 2: Rohdaten-Transkription
        raw_content = self.transcribe_raw(image_b64, mime_type, structure_analysis)

        # Raw.md speichern
        raw_header = (
            f"# Rohdaten-Transkription: {board_name}\n\n"
            f"**Erstellt:** {time.strftime('%Y-%m-%d %H:%M')}\n"
            f"**Modell:** {self.model}\n"
            f"**Template:** {self.template}\n\n"
            f"---\n\n"
            f"## Strukturanalyse\n\n{structure_analysis}\n\n"
            f"---\n\n"
            f"## Transkription\n\n"
        )
        raw_path.write_text(raw_header + raw_content, encoding="utf-8")
        logger.info(f"Raw.md gespeichert: {raw_path}")

        # Schritt 3: Bereinigung & Anreicherung
        cleaned_content = self.clean_and_enrich(raw_content, structure_analysis)

        # Schritt 4: Synthese
        summary_content = self.synthesize_summary(cleaned_content, structure_analysis)

        # Summary.md speichern
        summary_header = (
            f"# Executive Summary: {board_name}\n\n"
            f"**Erstellt:** {time.strftime('%Y-%m-%d %H:%M')}\n"
            f"**Modell:** {self.model}\n"
            f"**Template:** {self.template}\n\n"
            f"---\n\n"
        )
        summary_path.write_text(summary_header + summary_content, encoding="utf-8")
        logger.info(f"Summary.md gespeichert: {summary_path}")

        logger.info(f"Board erfolgreich verarbeitet: {board_name}")
        return raw_path, summary_path


# ---------------------------------------------------------------------------
# CLI-Interface
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parst die Kommandozeilen-Argumente."""
    parser = argparse.ArgumentParser(
        prog="digitize_board.py",
        description="Digitalisiert Metaplan- und Workshop-Board-Fotos via OpenRouter Vision API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python digitize_board.py --image board.jpg
  python digitize_board.py --image board.jpg --template retrospektive
  python digitize_board.py --image board.jpg --context "Lager-Team, rote Punkte = Votes"
  python digitize_board.py --batch ./fotos/ --template ideensammlung
  python digitize_board.py --test
        """,
    )

    # Eingabe
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--image", "-i",
        type=Path,
        help="Pfad zum Board-Foto (JPG, PNG, WEBP)",
    )
    input_group.add_argument(
        "--batch", "-b",
        type=Path,
        help="Ordner mit mehreren Board-Fotos (alle werden verarbeitet)",
    )
    input_group.add_argument(
        "--test",
        action="store_true",
        help="Testet die API-Verbindung ohne Bild-Verarbeitung",
    )

    # Verarbeitungs-Optionen
    parser.add_argument(
        "--template", "-t",
        choices=list(BOARD_TEMPLATES.keys()),
        default="custom",
        help=f"Board-Template (Standard: custom). Optionen: {', '.join(BOARD_TEMPLATES.keys())}",
    )
    parser.add_argument(
        "--context", "-c",
        type=str,
        default="",
        help='Zusätzlicher Board-Kontext, z.B. "Lager-Team, rote Punkte = Votes"',
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default="",
        help="OpenRouter Modell-ID (überschreibt DEFAULT_MODEL aus .env)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Ausgabe-Ordner (überschreibt OUTPUT_DIR aus .env)",
    )
    parser.add_argument(
        "--confidence",
        action="store_true",
        help="Markiert unsichere Erkennungen mit Konfidenz-Scores",
    )

    return parser.parse_args()


def run_connection_test(api_key: str, model: str) -> None:
    """Testet die API-Verbindung mit einer einfachen Text-Anfrage."""
    logger.info(f"Teste API-Verbindung mit Modell: {model}")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Antworte mit: OK"}],
        "max_tokens": 10,
    }
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"]
        print(f"\n✅ API-Verbindung erfolgreich! Antwort: {answer}")
        print(f"   Modell: {model}")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        print(f"\n❌ API-Fehler (HTTP {status}): {e.response.text if e.response else e}")
    except Exception as e:
        print(f"\n❌ Verbindungsfehler: {e}")


def main() -> None:
    """Hauptfunktion: Parst Argumente, initialisiert BoardDigitizer und startet Verarbeitung."""
    load_dotenv()

    args = parse_args()

    # Konfiguration aus Umgebung / .env
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.error(
            "OPENROUTER_API_KEY nicht gesetzt! "
            "Bitte .env Datei erstellen (siehe .env.example)."
        )
        sys.exit(1)

    model = args.model or os.getenv("DEFAULT_MODEL", "google/gemini-2.0-flash")
    fallback_model = os.getenv("FALLBACK_MODEL", "anthropic/claude-sonnet-4-5")
    output_dir = args.output or Path(os.getenv("OUTPUT_DIR", "./output"))
    max_tokens = int(os.getenv("MAX_TOKENS", "4000"))

    # Test-Modus
    if args.test:
        run_connection_test(api_key, model)
        return

    if not args.image and not args.batch:
        logger.error("Bitte --image BILD.jpg oder --batch ORDNER/ angeben.")
        sys.exit(1)

    # BoardDigitizer initialisieren
    digitizer = BoardDigitizer(
        api_key=api_key,
        model=model,
        fallback_model=fallback_model,
        output_dir=output_dir,
        max_tokens=max_tokens,
        template=args.template,
        context=args.context,
        confidence=args.confidence,
    )

    # Bild-Liste bestimmen
    images: list[Path] = []

    if args.image:
        images = [args.image]
    elif args.batch:
        batch_dir = args.batch
        if not batch_dir.is_dir():
            logger.error(f"Ordner nicht gefunden: {batch_dir}")
            sys.exit(1)
        for fmt in BoardDigitizer.SUPPORTED_FORMATS:
            images.extend(batch_dir.glob(f"*{fmt}"))
            images.extend(batch_dir.glob(f"*{fmt.upper()}"))
        images = sorted(set(images))
        if not images:
            logger.error(f"Keine unterstützten Bilder in: {batch_dir}")
            sys.exit(1)
        logger.info(f"Batch-Modus: {len(images)} Bilder gefunden.")

    # Verarbeitung
    success_count = 0
    error_count = 0

    for image_path in images:
        try:
            raw_path, summary_path = digitizer.process_board(image_path)
            print(f"\n✅ {image_path.name}")
            print(f"   Raw:     {raw_path}")
            print(f"   Summary: {summary_path}")
            success_count += 1
        except Exception as e:
            logger.error(f"Fehler bei {image_path.name}: {e}")
            print(f"\n❌ {image_path.name}: {e}")
            error_count += 1

    # Abschlussbericht
    if len(images) > 1:
        print(f"\n{'='*50}")
        print(f"Verarbeitung abgeschlossen: {success_count} ✅  {error_count} ❌")
        print(f"Ausgabe-Ordner: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
