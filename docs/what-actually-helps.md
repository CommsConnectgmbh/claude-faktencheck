[Deutsch](was-wirklich-hilft.md)

# What actually helps with coding agent hallucinations

Coding agents can invent plausible package names or claim a change has been verified when no checks have run. [claude-faktencheck](https://github.com/CommsConnectgmbh/claude-faktencheck) addresses this at several points: by requiring evidence, checking packages before installation, and prompting verification before a task ends.

This free repository is available under the [MIT License](../LICENSE). It is the sister project of [claude-starter-kit](https://github.com/CommsConnectgmbh/claude-starter-kit) for Claude Code users in German-speaking countries. The author is [Rainer Roloff](https://rainerroloff.de).

## What the sources actually support

### Anthropic recommends evidence and allows uncertainty

Anthropic's documentation recommends explicitly allowing Claude to say "I don't know". For long documents with [more than 20,000 tokens](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations), it recommends extracting relevant quotes before analyzing the content. Claims should be supported by quotes, and statements without suitable evidence should be retracted.

Anthropic also lists verification, comparing multiple responses, iterative revision, and restricting answers to supplied external sources. The documentation explicitly says these techniques can significantly reduce hallucinations but cannot eliminate them. [Source: Anthropic, "Reduce hallucinations"](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations)

This supports the approach used in this repository. It does not establish how effective this particular implementation is.

### Invented packages are a documented problem

The study *We Have a Package for You! A Comprehensive Analysis of Package Hallucinations by Code Generating LLMs* examined [16 language models using 576,000 code samples](https://arxiv.org/abs/2406.10279). It reports average hallucinated-package rates of at least [5.2% for commercial models and 21.7% for open-source models](https://arxiv.org/abs/2406.10279), as well as [205,474 unique invented package names](https://arxiv.org/abs/2406.10279).

These findings apply to the models and tasks studied. They are neither a measured hallucination rate for a current Claude Code session nor a measurement of claude-faktencheck's effectiveness.

In slopsquatting, attackers register package names invented by AI. Checking whether a package exists is therefore not enough as a protective measure: an invented name may have been registered by the time it is checked. The [study](https://arxiv.org/abs/2406.10279) demonstrates the underlying condition: there are many invented names.

## What this repository implements

| Component | Implementation | Limitation |
|---|---|---|
| [`faktencheck` skill](../skills/faktencheck/SKILL.md) | `/faktencheck` enables evidence requirements. It allows uncertainty, requires quotes before analysis, and removes or flags unsupported claims. Numbers should be calculated with scripts. | Instructions guide the model but do not enforce a correct answer. Turn off with "Faktencheck aus" or "fact check off". |
| [`faktenpruefer` agent](../agents/faktenpruefer.md) | Checks a finished response with fresh context. Opens sources itself and labels each claim "confirmed", "false", or "unsupported". Must not make changes. | The reviewer is also a language model. Fresh context does not replace reliable sources. |
| [Package hook](../hooks/paket-check.py) | Queries the official npm, PyPI, and crates.io registries before recognized installations through Bash. Blocks nonexistent packages and packages below the age threshold. | Checks existence and age, not package contents, API behavior, or whether a requested version is correct. |
| [Stop hook](../hooks/beleg-stopp.py) | Pauses the end of a turn if a recognized code change was not followed by a verification step, or if a recognized success claim was made without a verification step. | Recognizes tool calls and command patterns. Does not assess their results or whether they support the specific claim. |
| [CLAUDE.md template](../templates/CLAUDE.faktencheck.md) | Adds evidence requirements, source checking, scripted calculations, and independent review to the project context. | Remains an instruction that can be overlooked in a long context. |

These components combine source checking with checks outside free-form text generation. The reason for using hooks is practical: rules can be overlooked in a long context, while installed and active hooks run at their configured events. This does not establish a measured advantage over other projects.

### Checking packages before installation

The package hook recognizes installation and execution commands for tools including npm, pnpm, yarn, bun, npx, pip, uv, poetry, pipx, and cargo. It also reads package names from `pip -r requirements.txt`, including nested `-r` references. It skips commands using custom registries or package indexes (`--registry`, `--index-url`, scope entries in `.npmrc`, `pip.conf`, uv and poetry sources), so private package names are not sent to public registries. [Source: package hook](../hooks/paket-check.py)

The default minimum age is [30 days](../hooks/paket-check.py), adjustable through `FAKTENCHECK_MIN_TAGE`. `FAKTENCHECK_OK=1` allows a deliberate exception for a single command. `FAKTENCHECK_AUS=1` disables the hooks.

The age threshold creates a pause for review. It can also stop legitimate new packages. An older package does not receive a safety verdict merely because it passes this check.

### A prompt to reconsider unsupported success claims

The Stop hook asks Claude to verify a claim or retract it. `stop_hook_active` prevents repeated pauses in the same turn. [Source: Stop hook](../hooks/beleg-stopp.py)

Detection is deliberately limited: a command recognized as a verification step is enough, even if it fails or does not support the claim. Changes made through Bash are not recognized as calls to an editing tool. The hook therefore does not confirm that "tests pass" or a change "is live".

## Comparing other projects fairly

| Project | Focus described in the source material | Difference from claude-faktencheck |
|---|---|---|
| [assafkip/research-mode](https://github.com/assafkip/research-mode) | A plugin that toggles citation requirements, uncertainty, and quoting before analysis; uses prompts without hooks. | Similar source checking. claude-faktencheck adds registry checks and a Stop hook. |
| [Pinperepette/grounded](https://github.com/Pinperepette/grounded) | A Node.js package with hooks for reading before editing, checking identifier existence, and detecting loops. | Different checks. Claude Code already refuses edits to unread files; the other checks go further. |
| [instantX-research/anthropic-anti-hallucinate-skills](https://github.com/instantX-research/anthropic-anti-hallucinate-skills) | Instructions for CLAUDE.md. | claude-faktencheck adds executable hooks and a separate review agent. |
| [mattschaller/slopcheck](https://github.com/mattschaller/slopcheck) | Checks npm names in Markdown and configuration files before a commit. | claude-faktencheck checks recognized commands during the agent's run before installation, and also covers PyPI, crates.io, and package age. |

There is no overall winner implied here. Checks before a commit and checks before installation operate at different points. Identifier checks and loop detection address tasks that this repository's hooks do not cover.

## Limitations and available evidence

**There is no empirical evidence that this repository reduces the hallucination rate.** Its [36 tests](../tests/test_hooks.py) check hook behavior using mocked registry responses without network access. They do not establish the general reliability of a coding agent.

Further limitations follow directly from the code:

- **Fail-open:** Network failures and unexpected errors let commands or responses proceed. The package hook also lets commands proceed when age data is missing or registry responses are too large. [Package hook](../hooks/paket-check.py), [Stop hook](../hooks/beleg-stopp.py)
- **Limited detection:** The package hook checks recognized package names in supported command forms. It does not fully inspect project manifests, transitive dependencies, or arbitrary shell constructs. [Package hook](../hooks/paket-check.py)
- **Existence does not establish quality:** An existing package above the age threshold can still be the wrong package for the task. [Package hook](../hooks/paket-check.py)
- **Running a check does not prove success:** Whether the output supports the claim still needs to be assessed. [Stop hook](../hooks/beleg-stopp.py), [review agent](../agents/faktenpruefer.md)

claude-faktencheck combines evidence requirements with technical checks that pause the workflow. It makes certain errors open to verification and can stop recognized problematic installations. It guarantees neither hallucination-free responses nor safe packages.
