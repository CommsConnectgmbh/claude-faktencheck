[Deutsch](README.md)

# claude-faktencheck

**Fewer hallucinations in Claude Code. Require evidence, check package names, question success claims.**

claude-faktencheck adds an evidence-required mode, an independent fact-checking agent, and hooks for package installations and final responses to Claude Code. Free, MIT-licensed, and with no additional Python dependencies.

The names are German: *Faktencheck* means “fact check,” and *Faktenprüfer* means “fact checker.” Commands, agent names, and `FAKTENCHECK_*` environment variables keep their German names. The skill text and hook messages are in German.

## Installation

Requirements: Claude Code and `python3`.

```bash
git clone https://github.com/CommsConnectgmbh/claude-faktencheck
cd claude-faktencheck
./install.sh
```

The installer copies the skill, agent, and optionally the hooks into `~/.claude`. Before changing an existing `settings.json`, it creates a backup named `settings.json.bak-faktencheck`. Reinstalling does not create duplicate hook entries.

Then start a new Claude Code session.

## Usage

Enable evidence-required mode in Claude Code:

```text
/faktencheck
```

Claude is instructed to support factual claims with files, URLs, or command output, quote documents before analyzing them, and calculate numbers using scripts. Missing evidence should be marked as unresolved. “I don't know” is explicitly allowed.

For an independent check:

```text
Ask faktenpruefer to check the response.
```

The agent checks with fresh context and returns a verdict for each claim: **bestätigt** (confirmed), **falsch** (false), or **nicht belegt** (unsupported), with supporting evidence. It makes no changes.

Use `Faktencheck aus` (“fact check off”) to end evidence-required mode. The hooks remain active independently.

Optional: Add the six rules from [CLAUDE.faktencheck.md](templates/CLAUDE.faktencheck.md) to your own `CLAUDE.md`.

## What the hooks check

### Package names before installation

The Bash hook [paket-check.py](hooks/paket-check.py) queries the npm registry, PyPI, or crates.io before recognized package installation commands run.

- **Package does not exist:** The command is blocked.
- **Package is less than 30 days old:** The command is blocked. Adjust this threshold with `FAKTENCHECK_MIN_TAGE`.

It recognizes commands using npm, pnpm, yarn, bun, npx, bunx, pnpx, pip, pip3, `python -m pip`, uv, poetry, pipx, uvx, and cargo, including `pip -r requirements.txt`.

Commands that use their own registry or package index (`--registry`, `--index-url`, a scope in `.npmrc`, `pip.conf`, uv or poetry sources) are not checked, so private package names are never sent to public registries.

After deliberately checking a package, you can allow it for a single command:

```bash
FAKTENCHECK_OK=1 npm install package-name
```

The age threshold introduces a pause for review. It does not tell you whether a package is safe.

### Verification before the final response

The Stop hook [beleg-stopp.py](hooks/beleg-stopp.py) pauses the end of a response once when:

- Code was changed without a subsequent recognized verification step, such as a test, build, lint run, script, curl request, or browser check.
- The final response claims success, such as “all tests pass,” “verified,” or “is live,” even though no verification step ran during the entire turn.

Claude receives a reminder to verify the claim or retract it. At most one reminder per turn prevents a loop. The hook recognizes verification steps; it does not assess whether their results actually support the claim.

## Why combine rules and hooks?

A rule in `CLAUDE.md` can be overlooked in a long context. Hooks run at their configured points and check concrete conditions. This repository therefore combines evidence requirements with checks during the agent's run.

Invented package names are a documented problem: A [study of package hallucinations](https://arxiv.org/abs/2406.10279), published at the USENIX Security Symposium 2025, examined 576,000 code samples from 16 LLMs and found an average hallucinated-package rate of at least 5.2% for commercial models. This is not a measurement specific to Claude Code. When attackers register these invented names, the practice is called **slopsquatting**.

The evidence requirements draw on Anthropic's [Reduce hallucinations](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations) recommendations: allow uncertainty, quote first, and retract unsupported claims.

[Background and comparison with other projects (in German)](docs/was-wirklich-hilft.md)

## Limitations

**No guarantee against hallucinations and no security boundary.** Both hooks fail open on errors; network failures do not cause the package checker to block commands. The hooks do not replace substantive review.

Setting the environment variable `FAKTENCHECK_AUS=1` disables both hooks. By contrast, `Faktencheck aus` only ends the skill's evidence-required mode.

## Customize or remove the installation

```bash
./install.sh --yes        # No prompts, including hooks
./install.sh --no-hooks   # Skill and agent only
./install.sh --uninstall  # Remove this project's hooks, skill, and agent
```

During uninstall, the installer removes only its own hook entries from `settings.json`.

## Tests

[36 tests](tests/test_hooks.py) check the hooks without network access using mocked registries. They require only the Python standard library. The [GitHub Actions configuration](.github/workflows/ci.yml) runs them with Python 3.9 and 3.12.

```bash
python3 -m unittest discover -s tests -v
```

## More for your Claude Code setup

The free sister repository [claude-starter-kit](https://github.com/CommsConnectgmbh/claude-starter-kit) provides skills, agents, and templates for your setup. claude-faktencheck complements it with evidence requirements and verification hooks.

If this project helps you, give it a ⭐ on [GitHub](https://github.com/CommsConnectgmbh/claude-faktencheck).

By [Rainer Roloff](https://rainerroloff.de). [MIT License](LICENSE), Copyright 2026 Rainer Roloff.