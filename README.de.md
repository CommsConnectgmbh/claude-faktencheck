[English](README.md)

# claude-faktencheck

**Weniger Halluzinationen in Claude Code. Belege verlangen, Paketnamen prüfen, Erfolgsmeldungen hinterfragen.**

claude-faktencheck ergänzt Claude Code um einen Belegpflicht-Modus, einen unabhängigen Prüf-Agenten und Hooks für Paketinstallationen und Schlussantworten. Kostenlos, unter MIT-Lizenz und ohne zusätzliche Python-Abhängigkeiten.

Skill, Agent und Hook-Meldungen sind auf Englisch. Deutsche Fassungen von Skill, Agent und CLAUDE.md-Regeln liegen in [templates/de](templates/de); wer sie nutzen will, kopiert sie nach der Installation über die englischen Dateien in `~/.claude`.

## Installation

Voraussetzung: Claude Code und `python3`.

```bash
git clone https://github.com/CommsConnectgmbh/claude-faktencheck
cd claude-faktencheck
./install.sh
```

Der Installer kopiert Skill, Agent und auf Wunsch die Hooks nach `~/.claude`. Vor Änderungen an einer vorhandenen `settings.json` legt er `settings.json.bak-faktencheck` an. Hook-Einträge werden bei erneuter Installation nicht doppelt angelegt.

Starte anschließend eine neue Claude-Code-Sitzung.

## So nutzt du es

Aktiviere die Belegpflicht in Claude Code:

```text
/faktencheck
```

Claude soll Tatsachenbehauptungen mit Dateien, URLs oder Befehlsausgaben belegen, bei Dokumenten erst zitieren und dann auswerten und Zahlen per Skript berechnen. Fehlende Belege sollen als offen markiert werden. „Weiß ich nicht“ ist ausdrücklich erlaubt.

Für eine unabhängige Prüfung:

```text
Lass den faktenpruefer über die Antwort laufen.
```

Der Agent prüft mit frischem Kontext und liefert pro Behauptung **confirmed** (bestätigt), **false** (falsch) oder **unsupported** (nicht belegt), jeweils mit Beleg. Er ändert nichts.

Mit `Faktencheck aus` oder `fact check off` beendest du den Belegpflicht-Modus. Die Hooks bleiben davon unabhängig aktiv.

Optional: Übernimm die sechs Regeln aus [CLAUDE.faktencheck.md](templates/de/CLAUDE.faktencheck.de.md) in deine eigene `CLAUDE.md`.

## Was die Hooks prüfen

### Paketnamen vor der Installation

Der Bash-Hook [paket-check.py](hooks/paket-check.py) fragt die npm-Registry, PyPI oder crates.io ab, bevor erkannte Paketinstallationen ausgeführt werden.

- **Paket existiert nicht:** Der Befehl wird blockiert.
- **Paket ist jünger als 30 Tage:** Der Befehl wird blockiert. Die Schwelle ist über `FAKTENCHECK_MIN_TAGE` einstellbar.

Erkannt werden Befehle mit npm, pnpm, yarn, bun, npx, bunx, pnpx, pip, pip3, `python -m pip`, uv, poetry, pipx, uvx und cargo, einschließlich `pip -r requirements.txt`.

Befehle mit eigener Registry oder eigenem Paketindex (`--registry`, `--index-url`, Scope in `.npmrc`, `pip.conf`, uv- oder poetry-Quellen) prüft der Hook nicht. So gehen private Paketnamen nicht an öffentliche Registries.

Ein bewusst geprüftes Paket kannst du für einen einzelnen Befehl freigeben:

```bash
FAKTENCHECK_OK=1 npm install paketname
```

Die Altersprüfung ist eine Bremsschwelle. Sie sagt nicht, ob ein Paket sicher ist.

### Prüfschritte vor der Schlussantwort

Der Stop-Hook [beleg-stopp.py](hooks/beleg-stopp.py) hält das Ende einer Antwort einmal an, wenn:

- Code geändert wurde und danach kein erkannter Prüfschritt lief, etwa Test, Build, Lint, Skript, curl oder Browser.
- Die Schlussantwort Erfolg behauptet, etwa „Tests grün“, „verifiziert“ oder „ist live“, obwohl im gesamten Turn kein Prüfschritt lief.

Claude erhält den Hinweis, zu prüfen oder die Aussage zurückzunehmen. Höchstens ein Anstoß pro Turn verhindert eine Schleife. Der Hook erkennt Prüfschritte; er bewertet nicht, ob deren Ergebnis die Behauptung tatsächlich belegt.

## Warum Regeln und Hooks zusammengehören

Eine Regel in der `CLAUDE.md` kann im langen Kontext übersehen werden. Hooks werden an den vorgesehenen Stellen ausgeführt und prüfen konkrete Bedingungen. Deshalb kombiniert dieses Repo Belegpflicht mit Prüfungen während des Agenten-Laufs.

Erfundene Paketnamen sind ein dokumentiertes Problem: Eine [Studie zu Paket-Halluzinationen](https://arxiv.org/abs/2406.10279), veröffentlicht beim USENIX Security Symposium 2025, fand in 576.000 Code-Beispielen von 16 LLMs durchschnittlich mindestens 5,2 % halluzinierte Pakete bei kommerziellen Modellen. Das ist keine spezifische Messung für Claude Code. Registrieren Angreifer solche erfundenen Namen, spricht man von **Slopsquatting**.

Die Belegpflicht greift Empfehlungen aus Anthropics [Reduce hallucinations](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations) auf: Unwissen zulassen, zuerst zitieren und unbelegte Behauptungen zurückziehen.

[Hintergrund und Vergleich mit anderen Projekten](docs/was-wirklich-hilft.md)

## Grenzen

**Keine Garantie gegen Halluzinationen und keine Sicherheitsgrenze.** Beide Hooks lassen bei Fehlern durch; bei Netzfehlern blockiert der Paket-Check nicht. Die Hooks ersetzen keine inhaltliche Prüfung.

`FAKTENCHECK_AUS=1` deaktiviert beide Hooks als Umgebungsvariable. `Faktencheck aus` beendet dagegen nur den Skill-Modus.

## Installation anpassen oder entfernen

```bash
./install.sh --yes        # Ohne Rückfragen, einschließlich Hooks
./install.sh --no-hooks   # Nur Skill und Agent
./install.sh --uninstall  # Eigene Hooks, Skill und Agent entfernen
```

Beim Uninstall entfernt der Installer nur seine eigenen Hook-Einträge aus der `settings.json`.

## Tests

[36 Tests](tests/test_hooks.py) prüfen die Hooks ohne Netzwerkzugriff mit gemockten Registries. Sie benötigen nur die Python-Standardbibliothek. Die [GitHub-Actions-Konfiguration](.github/workflows/ci.yml) führt sie mit Python 3.9 und 3.12 aus.

```bash
python3 -m unittest discover -s tests -v
```

## Mehr für dein Claude-Code-Setup

Das kostenlose Schwester-Repo [claude-starter-kit](https://github.com/CommsConnectgmbh/claude-starter-kit) liefert Skills, Agents und Vorlagen für dein Setup. claude-faktencheck ergänzt es um Belegpflicht und Prüf-Hooks.

Wenn dir das Projekt hilft, gib ihm einen ⭐ auf [GitHub](https://github.com/CommsConnectgmbh/claude-faktencheck).

Von [Rainer Roloff](https://rainerroloff.de). [MIT-Lizenz](LICENSE), Copyright 2026 Rainer Roloff.