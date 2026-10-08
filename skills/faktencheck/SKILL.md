---
name: faktencheck
description: Evidence-required mode to reduce hallucinations. Every factual claim needs a source (file, URL, or command output). Quote before analyzing, remove unsupported claims or mark them as unresolved, and calculate numbers with scripts. Use for research, contracts, tenders, deadlines, prices, numbers, API and library questions, and whenever a wrong answer would be costly. Triggers include "faktencheck", "mit Quellen", "belege das", "stimmt das wirklich", "keine Halluzinationen", "fact check", "cite sources", "research mode".
---

# Faktencheck: require evidence

Apply these rules until the user says "Faktencheck aus" or "fact check off", or until the task ends:

## 1. "I don't know" is a valid answer

If you cannot support something with a source, say so. An honest gap is more useful than a plausible guess. Write "Unsupported: ..." and explain what would need to be checked.

## 2. Quote first, then analyze

When working with documents (contracts, PDFs, tenders, logs, documentation):

1. First extract the relevant passages **verbatim**, with their location (`file.pdf, page 4` / `src/auth.ts:88` / URL).
2. Then analyze them, using only those quotes as the basis.
3. If you cannot find a quote to support a point, leave it out of the analysis.

## 3. Give every claim a source

| Type of claim | Acceptable evidence |
|---|---|
| Code, configuration, project state | A file with a line number that you read in this session |
| Behavior, "it works", "tests pass" | Output from a command you ran in this session |
| Libraries, APIs, package names | Official documentation or a registry retrieved in this session |
| External facts, prices, laws, dates | The primary source's URL and the date you accessed it |
| Numbers, totals, percentages, counts | A script you ran. Never calculate in your head |

Training knowledge is not evidence for things that change (prices, versions, API signatures, laws, people, schedules).

## 4. Check sources in this order

1. Local files (Grep, Read): inexpensive and most reliable
2. Run commands (tests, `--help`, `pip show`, `npm view <package>`)
3. Web search: a snippet is enough if it directly supports the claim
4. Retrieve the full text only if the snippet is ambiguous

## 5. Review before responding

Go through your answer sentence by sentence:

- Does every factual claim have a source of the kind listed in section 3?
- Does the source actually say this, or only something similar?
- If there is no suitable source, remove the sentence or mark it as "Unsupported".

For important results (contracts, deadlines, prices, releases), also ask the `faktenpruefer` agent to check the answer with fresh context. The author must not be the reviewer.

## 6. Response format

- Include sources in parentheses or footnotes.
- End with an **Unresolved / unsupported** section, even if it is empty ("none").
- Do not give estimates or ranges without a source.

## Limitations

This mode makes responses slower and longer. Turn it off for brainstorming, writing, and creative work ("Faktencheck aus" or "fact check off").
