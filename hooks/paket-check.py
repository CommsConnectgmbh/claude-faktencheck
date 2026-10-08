#!/usr/bin/env python3
"""PreToolUse-Hook: erfundene Pakete abfangen, bevor sie installiert werden.

Sprachmodelle erfinden Paketnamen, die plausibel klingen. Angreifer registrieren
genau diese Namen und legen Schadcode hinein ("Slopsquatting"). Der Hook liest
jeden Bash-Befehl, sucht darin Installationen (npm, pnpm, yarn, bun, npx, pip,
uv, poetry, pipx, cargo) und fragt die offizielle Registry:

  * Paket existiert nicht        -> blockiert
  * Paket juenger als 30 Tage    -> blockiert, bis es bewusst freigegeben wird

Freigabe fuer einen einzelnen Befehl: `FAKTENCHECK_OK=1` direkt vor die
Installation stellen (`FAKTENCHECK_OK=1 npm install x`).
Hook komplett aus: Umgebungsvariable `FAKTENCHECK_AUS=1`.

Befehle mit eigener Registry oder eigenem Paketindex (--registry, --index-url,
.npmrc-Scope, pip.conf, uv-/poetry-Quellen) prueft der Hook nicht: Die
oeffentliche Registry kennt solche Pakete nicht, und ihre Namen sollen sie auch
nicht erfahren.

Nur Standardbibliothek. Netzfehler, Zeitueberschreitungen und alles
Unerwartete lassen den Befehl durch (fail-open): Der Hook ist eine
Bremsschwelle gegen Halluzinationen, keine Sicherheitsgrenze.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

MIN_AGE_DAYS = int(os.environ.get("FAKTENCHECK_MIN_TAGE", "30"))
TIMEOUT = 4
MAX_PACKAGES = 8
# Grosse Dokumente gehoeren zu etablierten Paketen; nicht komplett laden.
MAX_BYTES = 3_000_000
USER_AGENT = "claude-faktencheck (+https://github.com/CommsConnectgmbh/claude-faktencheck)"

WRAPPERS = {"sudo", "env", "time", "nice", "nohup", "command", "exec", "doas"}
WRAPPER_VALUE_FLAGS = {
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-U", "-r", "-t", "-T", "--user", "--group", "--host",
             "--prompt", "--close-from", "--chdir", "--role", "--type", "--other-user", "--command-timeout"},
    "doas": {"-u", "-C"},
    "env": {"-u", "-C", "-S", "--unset", "--chdir", "--split-string"},
    "nice": {"-n", "--adjustment"},
}

NAME_RE = {
    "npm": re.compile(r"^(@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*$", re.I),
    "pypi": re.compile(r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$", re.I),
    "crates": re.compile(r"^[a-z0-9_-]+$", re.I),
}

NPM_VALUE_FLAGS = {"--prefix", "-C", "--dir", "--filter", "-F", "--tag", "-w", "--workspace", "--cwd",
                   "--userconfig", "--cache", "--loglevel", "--omit", "--include", "--save-prefix"}
PIP_VALUE_FLAGS = {"-c", "--constraint", "-e", "--editable", "-t", "--target", "-f", "--find-links",
                   "--only-binary", "--no-binary", "--platform", "--python-version", "--implementation",
                   "--abi", "--root", "--prefix", "--src", "--upgrade-strategy", "--progress-bar", "--log",
                   "--proxy", "--retries", "--timeout", "--cache-dir", "--trusted-host", "--report",
                   "--config-settings", "-C", "--global-option", "--exists-action", "--python",
                   "--group", "-G", "--optional", "--extra", "--with", "--only", "--without", "--lock",
                   "--source", "--index-strategy", "--keyring-provider", "--resolution", "--prerelease",
                   "--client-cert", "--cert", "--log-file", "--python-platform", "--require-hashes-file",
                   "--build-constraint", "--overrides", "--override", "--exclude-newer", "--link-mode",
                   "--compile-bytecode-timeout", "--config-file", "--directory", "--project", "--package"}
PIP_CUSTOM_INDEX = ("-i", "--index-url", "--extra-index-url", "--index", "--default-index", "--source")
CARGO_VALUE_FLAGS = {"--version", "--features", "-F", "--branch", "--tag", "--rev", "--package", "-p",
                     "--rename", "--target", "--root", "--manifest-path", "-j", "--jobs", "--profile"}
CARGO_CUSTOM = ("--git", "--path", "--registry", "--index")
PY_INDEX_ENV = ("PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "UV_INDEX_URL", "UV_INDEX", "UV_EXTRA_INDEX_URL",
                "UV_DEFAULT_INDEX")


class Word(str):
    """Ein Shell-Wort ohne Quotes. `dynamic`: enthaelt $-Expansion oder Backticks."""

    dynamic = False


def as_word(value):
    if isinstance(value, Word):
        return value
    w = Word(value)
    w.dynamic = "$" in value or "`" in value
    return w


class Command(list):
    """Ein einfacher Befehl. `scope`: Kette der offenen ( )-Subshells, in denen er steht."""

    scope = ()


def tokenize(command):
    """Zerlegt einen Bash-Befehl in einfache Befehle (Listen von Words).

    Beachtet Quotes, Backslashes, Kommentare, Zeilenumbrueche, Befehlstrenner
    (; & | && || ( )), Umleitungen (> 2>&1 &> < <<<), deren Ziel verworfen wird,
    und Here-Docs, deren Inhalt kein Befehl ist.
    """
    commands = []
    current = Command()
    buf, dynamic, in_word, skip_next = [], False, False, False
    scopes, counter, heredocs = [], 0, []
    i, n = 0, len(command)

    def end_word():
        nonlocal buf, dynamic, in_word, skip_next
        if in_word:
            text = "".join(buf)
            if skip_next == "heredoc":
                heredocs.append(text)
                skip_next = False
            elif skip_next:
                skip_next = False
            else:
                w = Word(text)
                w.dynamic = dynamic
                current.append(w)
        buf, dynamic, in_word = [], False, False

    def end_command():
        nonlocal current
        end_word()
        if current:
            commands.append(current)
        current = Command()
        current.scope = tuple(scopes)

    while i < n:
        c = command[i]
        if c == "\\" and i + 1 < n:
            if command[i + 1] != "\n":
                buf.append(command[i + 1])
                in_word = True
            i += 2
            continue
        if c == "'":
            j = command.find("'", i + 1)
            j = n if j < 0 else j
            buf.append(command[i + 1:j])
            in_word, i = True, j + 1
            continue
        if c == '"':
            j = i + 1
            while j < n and command[j] != '"':
                if command[j] == "\\" and j + 1 < n:
                    buf.append(command[j + 1])
                    j += 2
                    continue
                if command[j] in "$`":
                    dynamic = True
                buf.append(command[j])
                j += 1
            in_word, i = True, j + 1
            continue
        if c in "$`":
            dynamic = True
            buf.append(c)
            in_word = True
            i += 1
            continue
        if c == "#" and not in_word:
            while i < n and command[i] != "\n":
                i += 1
            continue
        if c in " \t\r":
            end_word()
            i += 1
            continue
        if c == "\n":
            end_command()
            i += 1
            # Here-Doc-Inhalte bis zur Endmarke ueberspringen.
            while heredocs:
                marker = heredocs.pop(0)
                while i < n:
                    j = command.find("\n", i)
                    j = n if j < 0 else j
                    line = command[i:j]
                    i = j + 1
                    if line.strip("\t") == marker:
                        break
            continue
        if c == "&" and i + 1 < n and command[i + 1] == ">":
            end_word()
            i += 2
            if i < n and command[i] == ">":
                i += 1
            skip_next = True
            continue
        if c in "<>":
            if in_word and "".join(buf).isdigit():
                buf, in_word = [], False  # Dateideskriptor wie 2>
            else:
                end_word()
            if command.startswith("<<<", i):
                i += 3
                skip_next = True
                continue
            if command.startswith("<<", i):
                i += 2
                if i < n and command[i] == "-":
                    i += 1
                skip_next = "heredoc"
                continue
            while i < n and command[i] in "<>&|":
                i += 1
            skip_next = True
            continue
        if c in ";|&":
            end_command()
            i += 1
            continue
        if c == "(":
            end_command()
            counter += 1
            scopes.append(counter)
            current.scope = tuple(scopes)
            i += 1
            continue
        if c == ")":
            end_command()
            if scopes:
                scopes.pop()
            current.scope = tuple(scopes)
            i += 1
            continue
        buf.append(c)
        in_word = True
        i += 1
    end_command()
    return commands


def strip_prefix(words):
    """Entfernt Zuweisungen und Wrapper (sudo, env ...). Liefert (rest, zuweisungen)."""
    assigns, i = {}, 0
    while i < len(words):
        w = words[i]
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", w)
        if m:
            assigns[m.group(1)] = m.group(2)
            i += 1
        elif os.path.basename(w) in WRAPPERS:
            value_flags = WRAPPER_VALUE_FLAGS.get(os.path.basename(w), set())
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] in value_flags else 1
        else:
            break
    return words[i:], assigns


def positional(args, value_flags):
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a in value_flags:
            skip = True
            continue
        if a.startswith("-"):
            continue
        out.append(a)
    return out


def has_flag(args, names):
    return any(a == f or a.startswith(f + "=") or (len(f) == 2 and a.startswith(f) and len(a) > 2)
               for a in args for f in names)


def flag_values(args, names):
    """Werte von Optionen in allen Schreibweisen: -p x, --package x, --package=x, -px."""
    vals = []
    for k, a in enumerate(args):
        for f in names:
            if a == f and k + 1 < len(args):
                vals.append(args[k + 1])
            elif a.startswith(f + "="):
                vals.append(a[len(f) + 1:])
            elif len(f) == 2 and a.startswith(f) and len(a) > 2 and not a.startswith("--"):
                vals.append(a[2:])
    return vals


def runner_package(args, package_flags, value_flags):
    """npx/bunx/dlx: explizite --package-Werte, sonst das erste Positionsargument.

    Alles nach dem ersten Positionsargument gehoert dem gestarteten Programm.
    """
    head, skip = [], False
    for a in args:
        if skip:
            head.append(a)
            skip = False
            continue
        if a in package_flags or a in value_flags:
            head.append(a)
            skip = True
            continue
        if a.startswith("-"):
            head.append(a)
            continue
        explicit = flag_values(head, package_flags)
        return explicit or [a]
    return flag_values(head, package_flags)


def npm_name(spec):
    spec = as_word(spec)
    if spec.dynamic or not spec or spec.startswith((".", "/", "~")) or ":" in spec:
        return None
    if spec.endswith((".tgz", ".tar.gz")):
        return None
    if spec.startswith("@"):
        scope, _, rest = spec.partition("/")
        name = scope + "/" + rest.split("@", 1)[0] if rest else None
    elif "/" in spec:  # github-Kurzform user/repo
        return None
    else:
        name = spec.split("@", 1)[0]
    return name if name and NAME_RE["npm"].match(name) else None


def pypi_name(spec):
    spec = as_word(spec)
    if spec.dynamic or not spec or "://" in spec or spec.startswith(("git+", ".", "/", "~")):
        return None
    if spec.endswith((".whl", ".tar.gz", ".zip")):
        return None
    name = re.split(r"[\[<>=!~;@\s]", spec, maxsplit=1)[0].strip()
    return name if name and NAME_RE["pypi"].match(name) else None


def cargo_name(spec):
    spec = as_word(spec)
    if spec.dynamic:
        return None
    name = spec.split("@", 1)[0]
    return name if name and NAME_RE["crates"].match(name) else None


def read_lines(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return []


def requirements(path, depth=0):
    """Paketnamen aus einer requirements-Datei, inklusive -r/--requirement-Verweisen.

    Liefert None, wenn die Datei einen eigenen Index setzt.
    """
    names = []
    for line in read_lines(path):
        line = line.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(PIP_CUSTOM_INDEX):
            return None
        nested = flag_values(line.split(), ("-r", "--requirement"))
        if nested:
            if depth >= 5:
                return None  # zu tief verschachtelt: lieber nicht pruefen als privat abfragen
            sub = requirements(os.path.join(os.path.dirname(path), nested[0]), depth + 1)
            if sub is None:
                return None
            names += sub
            continue
        if line.startswith("-"):
            continue
        n = pypi_name(line)
        if n:
            names.append(n)
    return names


def ancestors(cwd):
    d = os.path.abspath(cwd)
    while True:
        yield d
        parent = os.path.dirname(d)
        if parent == d:
            return
        d = parent


def npmrc_text(cwd):
    files = [os.path.join(d, ".npmrc") for d in ancestors(cwd)] + [os.path.expanduser("~/.npmrc")]
    return "\n".join("\n".join(read_lines(f)) for f in files)


def npm_private(name, npmrc):
    """True, wenn das Paket ueber eine eigene Registry kommt (globale oder Scope-Registry)."""
    for line in npmrc.splitlines():
        line = line.strip()
        m = re.match(r"^registry\s*=\s*(\S+)", line)
        if m and "registry.npmjs.org" not in m.group(1):
            return True
        if name.startswith("@") and re.match(re.escape(name.split("/")[0]) + r":registry\s*=", line):
            return True
    return False


def python_index_configured(cwd, assigns):
    if any(os.environ.get(k) or assigns.get(k) for k in PY_INDEX_ENV):
        return True
    configs = [
        os.path.expanduser("~/.config/pip/pip.conf"),
        os.path.expanduser("~/.pip/pip.conf"),
        os.path.expanduser("~/Library/Application Support/pip/pip.conf"),
        "/etc/pip.conf",
        os.path.expanduser("~/.config/uv/uv.toml"),
    ]
    for source in (os.environ, assigns):
        if source.get("PIP_CONFIG_FILE"):
            configs.append(os.path.join(cwd, os.path.expanduser(source["PIP_CONFIG_FILE"])))
    if any(source.get(k) for source in (os.environ, assigns) for k in ("UV_CONFIG_FILE",)):
        return True
    for f in configs:
        if re.search(r"^\s*(extra-)?index(-url)?\s*=|^\s*\[\[index\]\]", "\n".join(read_lines(f)), re.M):
            return True
    for d in ancestors(cwd):
        text = "\n".join(read_lines(os.path.join(d, "pyproject.toml")) + read_lines(os.path.join(d, "uv.toml")))
        if re.search(r"\[\[tool\.uv\.index\]\]|\[\[tool\.poetry\.source\]\]|^\s*\[\[index\]\]", text, re.M):
            return True
    return False


def packages_in(words, cwd):
    """Liefert (registry, name)-Paare fuer einen einfachen Befehl."""
    words, assigns = strip_prefix(words)
    if not words or "FAKTENCHECK_OK" in assigns and assigns["FAKTENCHECK_OK"] == "1":
        return []
    tool = os.path.basename(words[0])
    rest = list(words[1:])

    if tool in {"python", "python3"} and rest[:2] == ["-m", "pip"]:
        tool, rest = "pip", rest[2:]
    if tool == "uv" and rest[:1] == ["pip"]:
        tool, rest = "pip", rest[1:]

    found = []
    if tool in {"npm", "pnpm", "yarn", "bun"}:
        if has_flag(rest, ("--registry",)):
            return []
        pos = positional(rest, NPM_VALUE_FLAGS)
        if not pos:
            return []
        sub = pos[0]
        args = rest[rest.index(sub) + 1:]
        install = {"add"} if tool == "yarn" else {"install", "i", "add", "isntall", "in"}
        if sub in install:
            found += [("npm", n) for n in map(npm_name, positional(args, NPM_VALUE_FLAGS))]
        elif (tool in {"pnpm", "yarn"} and sub == "dlx") or (tool == "bun" and sub == "x"):
            found += [("npm", npm_name(p)) for p in runner_package(args, {"--package", "-p"}, set())]
    elif tool in {"npx", "bunx", "pnpx"}:
        if has_flag(rest, ("--registry",)):
            return []
        pkgs = runner_package(rest, {"--package", "-p"}, {"-c", "--call"})
        if has_flag(rest, ("-c", "--call")):
            pkgs = flag_values(rest, ("--package", "-p"))
        found += [("npm", npm_name(p)) for p in pkgs]
    elif tool in {"pip", "pip3"}:
        if rest[:1] != ["install"]:
            return []
        args = rest[1:]
        if has_flag(args, PIP_CUSTOM_INDEX) or python_index_configured(cwd, assigns):
            return []
        for req in flag_values(args, ("-r", "--requirement")):
            names = requirements(req if os.path.isabs(req) else os.path.join(cwd, req))
            if names is None:
                return []
            found += [("pypi", n) for n in names]
        rest_args, skip = [], False
        for a in args:
            if skip:
                skip = False
            elif a in ("-r", "--requirement"):
                skip = True
            elif not a.startswith(("-r", "--requirement=")):
                rest_args.append(a)
        found += [("pypi", pypi_name(n)) for n in positional(rest_args, PIP_VALUE_FLAGS)]
    elif tool in {"uv", "poetry"} and rest[:1] == ["add"]:
        args = rest[1:]
        if has_flag(args, PIP_CUSTOM_INDEX) or python_index_configured(cwd, assigns):
            return []
        found += [("pypi", pypi_name(n)) for n in positional(args, PIP_VALUE_FLAGS)]
    elif tool == "pipx" and rest[:1] in (["install"], ["run"]) or tool == "uvx":
        args = rest[1:] if tool == "pipx" else rest
        if has_flag(args, PIP_CUSTOM_INDEX) or python_index_configured(cwd, assigns):
            return []
        main_pkg = flag_values(args, ("--from", "--spec")) or positional(args, PIP_VALUE_FLAGS | {"--from", "--spec"})[:1]
        found += [("pypi", pypi_name(p)) for p in main_pkg + flag_values(args, ("--with",))]
    elif tool == "cargo" and rest[:1] in (["add"], ["install"]):
        args = rest[1:]
        if has_flag(args, CARGO_CUSTOM):
            return []
        found += [("crates", cargo_name(n)) for n in positional(args, CARGO_VALUE_FLAGS)]

    # Ein Wort, das als Datei oder Ordner existiert, ist ein Pfad, kein Paketname.
    found = [(r, n) for r, n in found if n and not os.path.exists(os.path.join(cwd, n))]
    if any(r == "npm" for r, _ in found):
        for source in (os.environ, assigns):
            for key, value in source.items():
                if key.lower() == "npm_config_registry" and "registry.npmjs.org" not in value:
                    return [(r, n) for r, n in found if r != "npm"]
        rc = npmrc_text(cwd)
        for extra in flag_values(rest, ("--userconfig",)) + [
                v for source in (os.environ, assigns) for k, v in source.items() if k.lower() == "npm_config_userconfig"]:
            rc += "\n" + "\n".join(read_lines(os.path.join(cwd, os.path.expanduser(extra))))
        found = [(r, n) for r, n in found if r != "npm" or not npm_private(n, rc)]
    return found


def collect(command, cwd):
    """Alle zu pruefenden Pakete eines Bash-Befehls, cd-Wechsel eingerechnet.

    Ein cd innerhalb einer ( )-Subshell gilt nur bis zu deren Ende.
    """
    dirs = {(): cwd or os.getcwd()}

    def dir_for(scope):
        if scope not in dirs:
            dirs[scope] = dir_for(scope[:-1])  # neue Subshell startet im Verzeichnis der Eltern
        return dirs[scope]

    pairs = []
    for words in tokenize(command):
        scope = getattr(words, "scope", ())
        here = dir_for(scope)
        stripped, _ = strip_prefix(words)
        if stripped and stripped[0] == "cd":
            target = [w for w in stripped[1:] if not w.startswith("-") or w == "-"]
            if target and target[0] != "-" and not target[0].dynamic:
                dirs[scope] = os.path.join(here, os.path.expanduser(target[0]))
            continue
        for pair in packages_in(words, here):
            if pair not in pairs:
                pairs.append(pair)
    return pairs


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = resp.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        return "gross"
    return json.loads(body.decode("utf-8"))


def parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def check(pair):
    """None = in Ordnung oder nicht pruefbar, sonst Text mit dem Befund."""
    registry, name = pair
    if registry == "npm":
        url = "https://registry.npmjs.org/" + urllib.parse.quote(name, safe="@")
    elif registry == "pypi":
        url = f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json"
    else:
        url = f"https://crates.io/api/v1/crates/{urllib.parse.quote(name)}"
    try:
        doc = fetch(url)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return f"`{name}` gibt es auf {registry} nicht."
        return None
    except Exception:
        return None
    if doc == "gross" or not isinstance(doc, dict):
        return None

    created = None
    if registry == "npm":
        created = parse_time((doc.get("time") or {}).get("created"))
    elif registry == "pypi":
        times = [parse_time(f.get("upload_time_iso_8601"))
                 for files in (doc.get("releases") or {}).values() for f in files]
        times = [t for t in times if t]
        created = min(times) if times else None
    else:
        created = parse_time((doc.get("crate") or {}).get("created_at"))
    if created is None:
        return None
    age = (datetime.now(timezone.utc) - created).days
    if age < MIN_AGE_DAYS:
        return f"`{name}` ist erst {age} Tage auf {registry} (Grenze {MIN_AGE_DAYS})."
    return None


def safe_check(pair):
    """Ein Fehler bei einem Paket darf die Befunde der anderen nicht verwerfen."""
    try:
        return check(pair)
    except Exception:
        return None


def main():
    if os.environ.get("FAKTENCHECK_AUS") == "1":
        return 0
    data = json.load(sys.stdin)
    if data.get("tool_name") != "Bash":
        return 0
    command = (data.get("tool_input") or {}).get("command", "")
    if not command:
        return 0
    pairs = collect(command, data.get("cwd"))[:MAX_PACKAGES]
    if not pairs:
        return 0
    with ThreadPoolExecutor(max_workers=len(pairs)) as pool:
        findings = [f for f in pool.map(safe_check, pairs) if f]
    if not findings:
        return 0
    sys.stderr.write(
        "Paket-Check hat die Installation angehalten:\n- " + "\n- ".join(findings) + "\n"
        "Erfundene oder frisch registrierte Paketnamen sind ein bekannter Angriffsweg (Slopsquatting). "
        "Pruefe den Namen in der offiziellen Doku oder Registry, bevor du weitermachst. "
        "Ist das Paket richtig und gewollt, stelle der Installation `FAKTENCHECK_OK=1` voran "
        "(z. B. `FAKTENCHECK_OK=1 npm install x`) und sag dem Nutzer, warum.\n"
    )
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
