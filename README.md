# Wortissimo

Zwei-Spieler-Wortspiel für iPhone und iPad. In jeder Runde erscheint ein
langes deutsches Wort; beide Spieler suchen 180 Sekunden lang deutsche
Wörter, die als **zusammenhängende Zeichenfolge** darin stecken.

Gültige Wörter geben 1 Punkt, Wörter die nur einer gefunden hat 2 Punkte.

## Betrieb auf dem Homelab

```bash
docker compose up -d --build
sudo tailscale serve --bg --https=443 http://127.0.0.1:8000
tailscale serve status
```

Die ausgegebene `*.ts.net`-Adresse auf dem iPhone in Safari öffnen und über
**Teilen → Zum Home-Bildschirm** installieren.

Das TLS-Zertifikat von Tailscale ist keine Bequemlichkeit, sondern
Voraussetzung: iOS erlaubt Service Worker und die Installation als App nur
in einem sicheren Kontext. Über `http://192.168.x.x` funktioniert beides
nicht.

Der Container lauscht bewusst nur auf `127.0.0.1` — der einzige Weg hinein
führt über Tailscale.

## Entwicklung

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m pip install fastapi "uvicorn[standard]" pytest-asyncio httpx

# Server
WORTISSIMO_STATIC=web/dist .venv/Scripts/python.exe -m uvicorn wortissimo.server.app:app --reload

# Frontend
cd web && npm install && npm run dev
```

## Tests

```bash
.venv/Scripts/python.exe -m pytest
cd web && npx vitest run --environment jsdom
cd web && npx playwright test        # benötigt einmalig: npx playwright install
```

## Korpus neu bauen

Nur nötig, wenn sich die Blockliste oder die Schwierigkeitstabelle ändert.
Braucht rund 500 MB RAM (CharSplits ngram-Modell) und etwa vier Minuten.

```bash
.venv/Scripts/python.exe scripts/fetch_dictionary.py   # einmalig
.venv/Scripts/python.exe scripts/fetch_hunspell.py     # einmalig
.venv/Scripts/python.exe scripts/build_puzzles.py --per-difficulty 500
```

Runden, die im Spiel über **Schlechte Runde** gemeldet wurden, landen in
`data/flagged.txt`. Fragwürdige Wörter nach Prüfung in
`data/blocklist.txt` eintragen und neu bauen.

Werkzeuge zur Kontrolle:

```bash
.venv/Scripts/python.exe scripts/inspect_puzzle.py --difficulty schwer -n 3
.venv/Scripts/python.exe scripts/play.py --difficulty mittel
```

## Aufbau

```
wortissimo/rules/       rein: Normalisierung, Prüfung, Punkte.
                        Von Generator UND Server benutzt — dadurch können
                        die beiden sich nie uneinig sein.
wortissimo/lexicon/     nur Buildzeit: Wortlisten, Hunspell-Autorität
wortissimo/generator/   Teilwortsuche, Kompositumzerlegung, Schwierigkeit
wortissimo/server/      FastAPI, WebSocket, Spielzustand
web/                    React + Vite PWA
```

Der Server hält **kein** Wörterbuch. Pro Runde kennt er genau zwei Mengen:
die anzuzeigenden Lösungen und die akzeptierten Wörter.

### Zwei Wortlisten, nicht eine

Sie haben entgegengesetzte Anforderungen:

- **akzeptiert** entscheidet, ob ein eingetipptes Wort zählt. Großzügig —
  ein echtes deutsches Wort fälschlich abzulehnen ist der ärgerlichste
  Fehler, den dieses Spiel machen kann.
- **angezeigt** ist die Liste der verpassten Wörter. Sauber — würde das
  Spiel `alk` als verpasstes Wort anzeigen, wäre das Vertrauen sofort weg.

Über die Zugehörigkeit zur zweiten Liste entscheidet Hunspell de_DE, nicht
die Korpushäufigkeit: Häufigkeit misst, wie oft eine Zeichenfolge vorkommt,
nicht ob sie ein Wort ist.

## Daten

- Wortliste: [Free German Dictionary](https://sourceforge.net/projects/germandict/),
  gemeinfrei, ~2,15 Mio. Formen.
- Rechtschreibung: Hunspell de_DE (igerman98), GPL v2/v3. Wird beim Bauen
  heruntergeladen, nicht mitgeliefert.
- Häufigkeiten: `wordfreq` — nur für die Schwierigkeitseinstufung.
