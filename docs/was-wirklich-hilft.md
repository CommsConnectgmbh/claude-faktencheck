# Was gegen Halluzinationen von Coding-Agenten wirklich hilft

Coding-Agenten können plausible Paketnamen erfinden oder behaupten, eine Änderung sei geprüft, obwohl kein Prüflauf stattgefunden hat. [claude-faktencheck](https://github.com/CommsConnectgmbh/claude-faktencheck) setzt deshalb an verschiedenen Stellen an: bei der Belegpflicht, vor Paketinstallationen und vor dem Abschluss einer Aufgabe.

Das kostenlose Repo steht unter der [MIT-Lizenz](../LICENSE). Es ist das Schwesterprojekt zum [claude-starter-kit](https://github.com/CommsConnectgmbh/claude-starter-kit) für Menschen im DACH-Raum, die Claude Code nutzen. Autor ist [Rainer Roloff](https://rainerroloff.de).

## Was die Quellen tatsächlich belegen

### Anthropic empfiehlt Belege und erlaubt Nichtwissen

Anthropics Dokumentation empfiehlt, Claude ausdrücklich „weiß ich nicht“ zu erlauben. Bei langen Dokumenten mit [mehr als 20.000 Tokens](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations) sollen relevante Stellen zunächst wörtlich zitiert und erst danach ausgewertet werden. Behauptungen sollen durch Zitate gestützt werden; Aussagen ohne passende Belege sollen zurückgezogen werden.

Als weiterführende Verfahren nennt Anthropic Verifikation, den Vergleich mehrerer Antworten, iterative Überarbeitung und die Beschränkung auf vorgegebene externe Quellen. Die Dokumentation sagt ausdrücklich: Diese Techniken können Halluzinationen deutlich reduzieren, beseitigen sie aber nicht. [Quelle: Anthropic, „Reduce hallucinations“](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations)

Das stützt die Arbeitsweise dieses Repos. Es belegt keine bestimmte Wirksamkeit seiner konkreten Implementierung.

### Erfundene Pakete sind ein untersuchtes Problem

Die Studie *We Have a Package for You! A Comprehensive Analysis of Package Hallucinations by Code Generating LLMs* untersuchte [16 Sprachmodelle anhand von 576.000 Code-Beispielen](https://arxiv.org/abs/2406.10279). Sie berichtet durchschnittlich mindestens [5,2 % halluzinierte Pakete bei kommerziellen Modellen und 21,7 % bei Open-Source-Modellen](https://arxiv.org/abs/2406.10279) sowie [205.474 einzigartige erfundene Paketnamen](https://arxiv.org/abs/2406.10279).

Diese Ergebnisse beziehen sich auf die untersuchten Modelle und Aufgaben. Sie sind keine gemessene Halluzinationsrate für eine heutige Claude-Code-Sitzung und keine Wirkungsmessung von claude-faktencheck.

Beim sogenannten Slopsquatting registrieren Angreifer von KI erfundene Paketnamen. Eine Existenzprüfung allein reicht deshalb als Schutzgedanke nicht aus: Ein erfundener Name kann inzwischen tatsächlich registriert sein. Die [Studie](https://arxiv.org/abs/2406.10279) zeigt die Voraussetzung dafür: Erfundene Namen sind zahlreich.

## Was dieses Repo davon umsetzt

| Baustein | Umsetzung | Grenze |
|---|---|---|
| [Skill `faktencheck`](../skills/faktencheck/SKILL.md) | Aktiviert mit `/faktencheck` die Belegpflicht. Erlaubt Nichtwissen, verlangt Zitate vor der Auswertung und streicht oder kennzeichnet unbelegte Aussagen. Zahlen sollen per Skript berechnet werden. | Ein Regeltext steuert das Modell, erzwingt aber keine korrekte Antwort. Ausschalten mit „Faktencheck aus“. |
| [Agent `faktenpruefer`](../agents/faktenpruefer.md) | Prüft eine fertige Antwort mit frischem Kontext. Öffnet Quellen selbst und bewertet jede Behauptung als „bestätigt“, „falsch“ oder „nicht belegt“. Soll nichts ändern. | Auch der Prüfer ist ein Sprachmodell. Frischer Kontext ersetzt keine belastbaren Quellen. |
| [Paket-Hook](../hooks/paket-check.py) | Fragt vor erkannten Installationen über Bash die offiziellen Registries npm, PyPI und crates.io ab. Blockiert nicht vorhandene und zu junge Pakete. | Prüft Existenz und Alter, nicht Paketinhalt, API-Verhalten oder die Richtigkeit einer gewünschten Version. |
| [Stop-Hook](../hooks/beleg-stopp.py) | Hält das Turn-Ende an, wenn nach einer erkannten Codeänderung kein Prüfschritt lief oder eine erkannte Erfolgsmeldung ohne Prüfschritt behauptet wird. | Erkennt Werkzeugaufrufe und Befehlsmuster. Bewertet weder deren Ergebnis noch, ob sie die konkrete Aussage belegen. |
| [CLAUDE.md-Vorlage](../templates/CLAUDE.faktencheck.md) | Verankert Belegpflicht, Quellenarbeit, Rechnungen per Skript und unabhängige Prüfung im Projektkontext. | Bleibt eine Anweisung, die im langen Kontext übersehen werden kann. |

Die Bausteine verbinden damit Quellenarbeit mit Prüfungen außerhalb der freien Textgenerierung. Die Begründung für Hooks ist praktisch: Regeln können im langen Kontext übersehen werden; installierte und aktive Hooks werden an den konfigurierten Ereignissen aufgerufen. Das ist keine gemessene Überlegenheit dieses Repos.

### Paketprüfung vor der Installation

Der Paket-Hook erkennt Installations- und Ausführungsbefehle unter anderem für npm, pnpm, yarn, bun, npx, pip, uv, poetry, pipx und cargo. Auch Paketnamen aus `pip -r requirements.txt` werden berücksichtigt, einschließlich verschachtelter `-r`-Verweise. Befehle mit eigener Registry oder eigenem Paketindex (`--registry`, `--index-url`, Scope-Einträge in `.npmrc`, `pip.conf`, uv- und poetry-Quellen) prüft der Hook nicht, damit private Paketnamen nicht an öffentliche Registries gehen. [Quelle: Paket-Hook](../hooks/paket-check.py)

Die voreingestellte Altersgrenze beträgt [30 Tage](../hooks/paket-check.py) und lässt sich mit `FAKTENCHECK_MIN_TAGE` ändern. `FAKTENCHECK_OK=1` erlaubt eine bewusste Ausnahme für einen Befehl. `FAKTENCHECK_AUS=1` deaktiviert die Hooks.

Die Altersprüfung ist eine Bremsschwelle: Sie kann auch legitime neue Pakete anhalten. Ein älteres Paket erhält dadurch kein Sicherheitsurteil.

### Ein Anstoß gegen unbelegte Erfolgsmeldungen

Der Stop-Hook fordert zum Prüfen oder zum Zurücknehmen einer unbelegten Erfolgsmeldung auf. `stop_hook_active` verhindert wiederholtes Anhalten desselben Turns. [Quelle: Stop-Hook](../hooks/beleg-stopp.py)

Seine Erkennung ist bewusst begrenzt: Ein als Prüfschritt erkanntes Kommando genügt, auch wenn es fehlschlägt oder die Behauptung nicht trägt. Änderungen über Bash werden nicht als Edit-Werkzeugaufruf erkannt. Der Hook bestätigt deshalb weder „Tests grün“ noch „ist live“.

## Ehrlicher Vergleich mit anderen Projekten

| Projekt | Schwerpunkt laut Faktenstand | Unterschied zu claude-faktencheck |
|---|---|---|
| [assafkip/research-mode](https://github.com/assafkip/research-mode) | Umschalt-Plugin mit Zitierpflicht, Nichtwissen und „quote first“; promptbasiert, ohne Hooks. | Ähnliche Quellenarbeit. claude-faktencheck ergänzt Registry-Prüfung und Stop-Hook. |
| [Pinperepette/grounded](https://github.com/Pinperepette/grounded) | Node.js-Paket mit Hooks für Read-before-Edit, Bezeichner-Existenzprüfung und Loop-Erkennung. | Andere Prüfziele. Claude Code verweigert Edits auf ungelesene Dateien bereits selbst; die weiteren Prüfungen gehen darüber hinaus. |
| [instantX-research/anthropic-anti-hallucinate-skills](https://github.com/instantX-research/anthropic-anti-hallucinate-skills) | Regeltext für die CLAUDE.md. | claude-faktencheck ergänzt ausführbare Hooks und einen gesonderten Prüf-Agenten. |
| [mattschaller/slopcheck](https://github.com/mattschaller/slopcheck) | Prüft npm-Namen in Markdown- und Konfigurationsdateien vor dem Commit. | claude-faktencheck prüft erkannte Befehle im Agenten-Lauf vor der Installation und berücksichtigt zusätzlich PyPI und crates.io sowie das Paketalter. |

Daraus folgt kein allgemeiner Sieger. Eine Prüfung vor dem Commit und eine Prüfung vor einer Installation setzen an unterschiedlichen Stellen an. Bezeichnerprüfung und Loop-Erkennung adressieren Aufgaben, die die Hooks dieses Repos nicht übernehmen.

## Grenzen und Nachweisstand

**Für dieses Repo ist keine empirische Reduktion der Halluzinationsrate belegt.** Die [36 Tests](../tests/test_hooks.py) prüfen das Verhalten der Hooks mit gemockten Registry-Antworten und ohne Netz. Sie belegen keine allgemeine Zuverlässigkeit eines Coding-Agenten.

Weitere Grenzen ergeben sich direkt aus dem Code:

- **Fail-open:** Bei Netzwerkfehlern und unerwarteten Fehlern lassen die Hooks durch. Der Paket-Hook lässt auch bei fehlenden Altersdaten oder zu großen Registry-Antworten durch. [Paket-Hook](../hooks/paket-check.py), [Stop-Hook](../hooks/beleg-stopp.py)
- **Begrenzte Erkennung:** Der Paket-Hook prüft erkannte Paketnamen aus unterstützten Befehlsformen. Er führt keine vollständige Prüfung von Projektmanifesten, transitiven Abhängigkeiten oder beliebigen Shell-Konstruktionen durch. [Paket-Hook](../hooks/paket-check.py)
- **Existenz ist kein Qualitätsbeleg:** Ein vorhandenes, ausreichend altes Paket kann trotzdem das falsche Paket für die Aufgabe sein. [Paket-Hook](../hooks/paket-check.py)
- **Ein Prüflauf ist kein Erfolgsbeweis:** Ob Ausgabe und Behauptung zusammenpassen, muss weiterhin geprüft werden. [Stop-Hook](../hooks/beleg-stopp.py), [Prüf-Agent](../agents/faktenpruefer.md)

claude-faktencheck ist damit eine Kombination aus Belegpflicht und technischen Bremsschwellen. Es macht bestimmte Fehler überprüfbar und kann erkannte problematische Installationen anhalten. Es garantiert weder halluzinationsfreie Antworten noch sichere Pakete.