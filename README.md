# Traukalender-Monitor (Düsseldorf) — gratis via GitHub Actions + ntfy

Prüft stündlich die freien **Fr/Sa-Termine im Zeitraum 15.–30.04.2027** in den
Trauorten **Standesamt**, **Standesamt 2** und **Schloss Eller** und schickt das
Ergebnis als **Push aufs Handy** (ntfy.sh). Neu freigewordene Zeitslots werden mit
`(NEU)` markiert. Läuft komplett kostenlos in der GitHub-Cloud — kein eigener
Rechner, kein LLM, kein Token-Verbrauch.

## Dateien
- `monitor.py` — der eigentliche Checker (Python, nur Standardbibliothek + `curl`)
- `.github/workflows/traukalender.yml` — der stündliche GitHub-Actions-Job
- `state.json` — merkt sich den letzten Stand (wird automatisch fortgeschrieben)

## Einrichtung (einmalig, ~5 Minuten)

### 1. ntfy einrichten (Push-Kanal)
1. App **ntfy** installieren (iOS/Android) — oder https://ntfy.sh im Browser.
2. Ein **geheimes Topic** ausdenken, schwer zu erraten, z. B.
   `traukalender-sx7k2p9q3m`. (Jeder, der das Topic kennt, kann mitlesen —
   also lang & zufällig wählen und nicht öffentlich posten.)
3. In der App dieses Topic **abonnieren** (Subscribe → Topic-Name eingeben).

### 2. GitHub-Repo anlegen
1. Auf github.com ein **neues, privates Repo** erstellen (z. B. `traukalender-monitor`).
2. Die drei Dateien hochladen (Struktur beibehalten — die Workflow-Datei muss
   unter `.github/workflows/` liegen). Entweder per „Add file → Upload files"
   oder per `git push`.

### 3. Secret hinterlegen
Repo → **Settings → Secrets and variables → Actions → New repository secret**
- **Name:** `NTFY_TOPIC`
- **Secret:** dein Topic-Name von oben (nur der Name, ohne `https://ntfy.sh/`)

### 4. Läuft
- Der Job startet automatisch stündlich (zur Minute :01, UTC-basiert).
- Sofort testen: Repo → **Actions → Traukalender-Monitor → Run workflow**.
- Beim allerersten Lauf wird nur der Ausgangsstand erfasst (kein `(NEU)`),
  ab dann werden neue Slots markiert.

## Push-Verhalten
- **Neue Slots** → Push mit hoher Priorität, Titel „NEUE Termine!".
- Standardlauf ohne Änderung → leiser Push (Priorität „low").
- Möchtest du **nur bei Änderungen** benachrichtigt werden: in der Workflow-Datei
  die Zeile `# ONLY_ON_CHANGE: "1"` einkommentieren (Raute entfernen).

## Anpassen
Oben in `monitor.py`:
- `TRAUORTE` — Orte/IDs ergänzen oder entfernen.
- `WIN_START` / `WIN_END` — Zeitraum ändern.
- `WEEKDAYS` — Wochentage (Mo=0 … So=6; aktuell Fr=4, Sa=5).
- In der Workflow-Datei `cron:` — Takt ändern (GitHub-Minimum ist 5 Minuten).

## Hinweise
- GitHub kann geplante Läufe unter Last um einige Minuten verschieben — für
  diesen Zweck unkritisch.
- Geplante Workflows werden nach 60 Tagen **ohne Repo-Aktivität** deaktiviert.
  Da der Job nach jedem Lauf `state.json` zurückcommittet, bleibt das Repo aktiv
  und der Job läuft weiter.
- Es werden ausschließlich **lesende** Abrufe gemacht — nichts wird reserviert
  oder gebucht.
