---
name: faktencheck
description: Belegpflicht-Modus gegen Halluzinationen. Jede Tatsachenbehauptung braucht eine Quelle (Datei, URL, Befehlsausgabe), Zitate kommen vor der Auswertung, Unbelegtes wird gestrichen oder als offen markiert, Zahlen werden per Skript gerechnet. Nutzen bei Recherche, Verträgen, Ausschreibungen, Fristen, Preisen, Zahlen, API- und Bibliotheksfragen und immer, wenn eine falsche Antwort teuer wäre. Trigger: "faktencheck", "mit Quellen", "belege das", "stimmt das wirklich", "keine Halluzinationen", "research mode", "cite sources", "fact check".
---

# Faktencheck: Belegpflicht-Modus

Ab jetzt gilt bis „Faktencheck aus“ oder bis zum Ende der Aufgabe:

## 1. „Weiß ich nicht“ ist eine gültige Antwort

Wenn du etwas nicht aus einer Quelle belegen kannst, sag das. Eine ehrliche Lücke ist hilfreicher als eine plausible Vermutung. Formulierung: „Nicht belegt: …“ plus was man prüfen müsste.

## 2. Erst zitieren, dann auswerten

Bei Dokumenten (Verträge, PDFs, Ausschreibungen, Logs, Doku):

1. Ziehe zuerst die relevanten Stellen **wörtlich** heraus, mit Fundort (`datei.pdf, Seite 4` / `src/auth.ts:88` / URL).
2. Erst danach: Auswertung, die sich nur auf diese Zitate stützt.
3. Findest du zu einem Punkt kein Zitat, gehört er nicht in die Auswertung.

## 3. Jede Behauptung bekommt eine Quelle

| Art der Aussage | Gilt als Beleg |
|---|---|
| Code, Konfiguration, Projektstand | Datei mit Zeilennummer, die du in dieser Sitzung gelesen hast |
| Verhalten, „funktioniert“, „Tests grün“ | Ausgabe eines Befehls, den du in dieser Sitzung ausgeführt hast |
| Bibliotheken, APIs, Paketnamen | Offizielle Doku oder Registry, in dieser Sitzung abgerufen |
| Externe Fakten, Preise, Gesetze, Daten | URL der Primärquelle plus Abrufdatum |
| Zahlen, Summen, Prozente, Zählungen | Skript, das du ausgeführt hast. Nie im Kopf rechnen |

Trainingswissen ist kein Beleg für Dinge, die sich ändern (Preise, Versionen, API-Signaturen, Gesetze, Personen, Termine).

## 4. Quellen in dieser Reihenfolge

1. Lokale Dateien (Grep, Read): billig und am verlässlichsten
2. Befehle ausführen (Tests, `--help`, `pip show`, `npm view <paket>`)
3. Websuche: Snippet reicht, wenn es die Aussage wörtlich trägt
4. Volltext abrufen nur, wenn das Snippet mehrdeutig ist

## 5. Vor dem Abschicken: Gegenlesen

Gehe deine Antwort Satz für Satz durch:

- Hat jede Tatsachenbehauptung eine Quelle aus Punkt 3?
- Sagt die Quelle wirklich das, oder nur etwas Ähnliches?
- Gibt es keine passende Quelle: Satz streichen oder als „Nicht belegt“ markieren.

Bei wichtigen Ergebnissen (Vertrag, Frist, Preis, Release) zusätzlich den Agenten `faktenpruefer` mit frischem Kontext auf die Antwort ansetzen. Wer die Antwort geschrieben hat, prüft sie nicht selbst.

## 6. Format der Antwort

- Aussagen mit Quelle in Klammern oder als Fußnote
- Am Ende ein Block **Offen / nicht belegt**, auch wenn er leer ist („keine“)
- Keine Schätzungen und keine Wertspannen ohne Quelle

## Grenzen

Der Modus macht Antworten langsamer und länger. Für Brainstorming, Texte und kreative Arbeit ausschalten („Faktencheck aus“).
