"""Tests fuer beide Hooks. Laufen ohne Netz: Registry-Antworten werden gemockt.

    python3 -m unittest discover -s tests
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "hooks" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


paket = load("paket-check")
beleg = load("beleg-stopp")


def iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


class FakeRegistry:
    """Beantwortet fetch() aus einer Tabelle {name: alter_in_tagen | None (=404)}."""

    def __init__(self, table):
        self.table = table
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        name = url.rstrip("/").split("/")[-1]
        if name == "json":
            name = url.rstrip("/").split("/")[-2]
        name = name.replace("%2F", "/").replace("%2f", "/")
        if name not in self.table or self.table[name] is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        age = self.table[name]
        if age == "gross":
            return "gross"
        if "registry.npmjs.org" in url:
            return {"time": {"created": iso(age)}}
        if "pypi.org" in url:
            return {"releases": {"1.0": [{"upload_time_iso_8601": iso(age)}]}}
        return {"crate": {"created_at": iso(age)}}


def run_paket(command, table, cwd=None, env=None):
    fake = FakeRegistry(table)
    cwd = cwd or tempfile.gettempdir()
    stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}))
    err = io.StringIO()
    with mock.patch.object(paket, "fetch", fake), mock.patch.object(sys, "stdin", stdin), \
            mock.patch.object(sys, "stderr", err), mock.patch.dict(os.environ, env or {}, clear=False), \
            mock.patch.object(paket, "python_index_configured", lambda cwd, assigns: False), \
            mock.patch.object(paket, "npmrc_text", lambda cwd: ""):
        code = paket.main()
    return code, err.getvalue(), fake


class PackageParsing(unittest.TestCase):
    def names(self, command, cwd=None):
        with mock.patch.object(paket, "python_index_configured", lambda cwd, assigns: False), \
                mock.patch.object(paket, "npmrc_text", lambda cwd: ""):
            return paket.collect(command, cwd or tempfile.gettempdir())

    def test_npm_variants(self):
        self.assertEqual(self.names("npm i -D @types/node lodash@4.17.21"),
                         [("npm", "@types/node"), ("npm", "lodash")])
        self.assertEqual(self.names("pnpm add zod && yarn add react"), [("npm", "zod"), ("npm", "react")])
        self.assertEqual(self.names("npx -y create-next-app@latest my-app"), [("npm", "create-next-app")])
        self.assertEqual(self.names("bunx --bun vite"), [("npm", "vite")])
        self.assertEqual(self.names("npm --prefix /tmp/p install left-pad"), [("npm", "left-pad")])

    def test_npx_package_flag_and_program_args(self):
        self.assertEqual(self.names("npx --package=typescript tsc --version"), [("npm", "typescript")])
        self.assertEqual(self.names("npx -p typescript tsc"), [("npm", "typescript")])
        self.assertEqual(self.names("npx cowsay -p hallo"), [("npm", "cowsay")])
        self.assertEqual(self.names("pnpm dlx create-vite app"), [("npm", "create-vite")])

    def test_npm_ignores_non_registry_specs(self):
        self.assertEqual(self.names("npm install ./local-pkg ../x.tgz github:user/repo user/repo"), [])
        self.assertEqual(self.names("npm install"), [])
        self.assertEqual(self.names("npm run build && npm ci"), [])
        self.assertEqual(self.names("npm install --registry=https://npm.example.org @firma/intern"), [])

    def test_shell_syntax(self):
        self.assertEqual(self.names("printf x\nnpm install fehlt"), [("npm", "fehlt")])
        self.assertEqual(self.names('echo ";" npm install fehlt'), [])
        self.assertEqual(self.names("echo 'npm install fake && x'"), [])
        self.assertEqual(self.names("npm install react # Kommentar"), [("npm", "react")])
        self.assertEqual(self.names("npm install react > install.log 2>&1"), [("npm", "react")])
        self.assertEqual(self.names('PKG=react; npm install "$PKG" `echo x`'), [])
        self.assertEqual(self.names("npm install \\\n  react"), [("npm", "react")])

    def test_round_two_shell_cases(self):
        self.assertEqual(self.names("sudo -n npm install fehlt"), [("npm", "fehlt")])
        self.assertEqual(self.names("nice -n 5 pip install rich"), [("pypi", "rich")])
        self.assertEqual(self.names("cat <<'EOF'\nnpm install fehlt\nEOF\nnpm i react"), [("npm", "react")])
        self.assertEqual(self.names("cat <<-EOF > x.txt\n\tnpm install fehlt\n\tEOF"), [])
        self.assertEqual(self.names("npm install &>install.log fehlt"), [("npm", "fehlt")])
        self.assertEqual(self.names("grep x <<< 'npm install fehlt'"), [])
        self.assertEqual(self.names("npm_config_registry=https://npm.example.org npm i @firma/intern"), [])
        self.assertEqual(self.names("pip install --client-cert c.pem requests"), [("pypi", "requests")])

    def test_cd_variants(self):
        with tempfile.TemporaryDirectory() as d:
            for sub, pkg in (("app", "httpx"), ("other", "rich")):
                Path(d, sub).mkdir()
                Path(d, sub, "requirements.txt").write_text(pkg + "\n")
            Path(d, "requirements.txt").write_text("numpy\n")
            self.assertEqual(self.names("cd -- app && pip install -r requirements.txt", d), [("pypi", "httpx")])
            self.assertEqual(self.names("(cd app); pip install -r requirements.txt", d), [("pypi", "numpy")])
            self.assertEqual(self.names("(cd other && pip install -r requirements.txt)", d), [("pypi", "rich")])
            self.assertEqual(self.names("(cd app && npm ci) && (cd other && pip install -r requirements.txt)", d),
                             [("pypi", "rich")])

    def test_local_files_are_not_packages(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "local-client-cert.pem").write_text("x")
            self.assertEqual(self.names("pip install --unknown-flag local-client-cert.pem requests", d),
                             [("pypi", "requests")])

    def test_npm_userconfig_with_private_registry(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "private.npmrc").write_text("registry=https://npm.example.org\n")
            with mock.patch.object(paket, "python_index_configured", lambda cwd, assigns: False), \
                    mock.patch.dict(os.environ, {"HOME": d}):
                self.assertEqual(paket.collect("npm --userconfig private.npmrc i @firma/intern", d), [])

    def test_wrappers_and_override(self):
        self.assertEqual(self.names("sudo -u root npm install fehlt"), [("npm", "fehlt")])
        self.assertEqual(self.names("sudo -E cargo add serde tokio@1"), [("crates", "serde"), ("crates", "tokio")])
        self.assertEqual(self.names("CI=1 npm install left-pad"), [("npm", "left-pad")])
        self.assertEqual(self.names("FAKTENCHECK_OK=1 npm install fehlt"), [])
        self.assertEqual(self.names("echo 'FAKTENCHECK_OK=1'; npm install fehlt"), [("npm", "fehlt")])

    def test_python_variants(self):
        self.assertEqual(self.names("pip install 'requests[socks]>=2' flask==3.0"),
                         [("pypi", "requests"), ("pypi", "flask")])
        self.assertEqual(self.names("python3 -m pip install -U httpx"), [("pypi", "httpx")])
        self.assertEqual(self.names("uv pip install rich"), [("pypi", "rich")])
        self.assertEqual(self.names("uv add pydantic && poetry add --group dev pytest"),
                         [("pypi", "pydantic"), ("pypi", "pytest")])
        self.assertEqual(self.names("uvx ruff check ."), [("pypi", "ruff")])
        self.assertEqual(self.names("uvx --from httpie http --help"), [("pypi", "httpie")])
        self.assertEqual(self.names("pip install --only-binary :all: requests"), [("pypi", "requests")])
        self.assertEqual(self.names("pip install -e . git+https://x/y.git"), [])
        self.assertEqual(self.names("pip install -i https://pypi.example.org/simple intern"), [])

    def test_requirements_files(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "req.txt").write_text("# kommentar\nrequests==2.0\n-e .\n-r more.txt\nnumpy>=1 ; python_version>'3'\n")
            Path(d, "more.txt").write_text("rich\n")
            expected = [("pypi", "requests"), ("pypi", "rich"), ("pypi", "numpy")]
            for cmd in ("pip install -r req.txt", "pip install --requirement=req.txt", "pip install -rreq.txt"):
                self.assertEqual(self.names(cmd, d), expected, cmd)
            sub = Path(d, "projekt")
            sub.mkdir()
            Path(sub, "requirements.txt").write_text("httpx\n")
            self.assertEqual(self.names("cd projekt && pip install -r requirements.txt", d), [("pypi", "httpx")])
            Path(d, "privat.txt").write_text("--index-url https://pypi.example.org/simple\nintern\n")
            self.assertEqual(self.names("pip install -r privat.txt", d), [])

    def test_private_npm_scope(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, ".npmrc").write_text("@firma:registry=https://npm.example.org\n")
            with mock.patch.object(paket, "python_index_configured", lambda cwd, assigns: False):
                self.assertEqual(paket.collect("npm i @firma/intern react", d), [("npm", "react")])

    def test_private_python_index(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "pyproject.toml").write_text("[[tool.uv.index]]\nurl = 'https://pypi.example.org'\n")
            self.assertTrue(paket.python_index_configured(d, {}))
            self.assertTrue(paket.python_index_configured(tempfile.gettempdir(), {"PIP_INDEX_URL": "x"}))
            Path(d, "privat.conf").write_text("[global]\nindex-url = https://pypi.example.org/simple\n")
            self.assertTrue(paket.python_index_configured(d, {"PIP_CONFIG_FILE": "privat.conf"}))


class PackageHook(unittest.TestCase):
    def test_known_packages_pass(self):
        code, err, _ = run_paket("npm install react && pip install requests", {"react": 4000, "requests": 5000})
        self.assertEqual(code, 0, err)

    def test_missing_package_blocks(self):
        code, err, _ = run_paket("npm install react-supr-hooks-pro", {})
        self.assertEqual(code, 2)
        self.assertIn("does not exist on npm", err)

    def test_young_package_blocks(self):
        code, err, _ = run_paket("pip install brandnew", {"brandnew": 3})
        self.assertEqual(code, 2)
        self.assertIn("only 3 days old", err)

    def test_large_document_counts_as_established(self):
        code, _, _ = run_paket("npm install next", {"next": "gross"})
        self.assertEqual(code, 0)

    def test_override_and_off_switch(self):
        self.assertEqual(run_paket("FAKTENCHECK_OK=1 npm install nope", {})[0], 0)
        self.assertEqual(run_paket("npm install nope", {}, env={"FAKTENCHECK_AUS": "1"})[0], 0)

    def test_network_error_fails_open(self):
        def boom(url):
            raise TimeoutError()
        stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "npm i x"}}))
        with mock.patch.object(paket, "fetch", boom), mock.patch.object(sys, "stdin", stdin):
            self.assertEqual(paket.main(), 0)

    def test_bad_timestamp_does_not_hide_other_findings(self):
        def mixed(url):
            if url.endswith("/react"):
                return {"time": {"created": "2020-01-01"}}
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "npm i react fehlt"}}))
        with mock.patch.object(paket, "fetch", mixed), mock.patch.object(sys, "stdin", stdin), \
                mock.patch.object(sys, "stderr", io.StringIO()), mock.patch.object(paket, "npmrc_text", lambda c: ""):
            self.assertEqual(paket.main(), 2)

    def test_deep_requirements_nesting_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            names = ["a", "b", "c", "d", "e", "f", "g"]
            for cur, nxt in zip(names, names[1:]):
                Path(d, cur + ".txt").write_text(f"pkg-{cur}\n-r {nxt}.txt\n")
            Path(d, "g.txt").write_text("--index-url https://pypi.example.org/simple\n")
            self.assertIsNone(paket.requirements(os.path.join(d, "a.txt")))

    def test_lookups_run_in_parallel(self):
        import threading
        import time
        lock, active, peak = threading.Lock(), [0], [0]

        def slow(url):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.2)
            with lock:
                active[0] -= 1
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "npm i a b c d e"}}))
        with mock.patch.object(paket, "fetch", slow), mock.patch.object(sys, "stdin", stdin), \
                mock.patch.object(sys, "stderr", io.StringIO()), mock.patch.object(paket, "npmrc_text", lambda c: ""):
            self.assertEqual(paket.main(), 2)
        self.assertGreater(peak[0], 1)

    def test_scoped_name_is_url_encoded(self):
        _, _, fake = run_paket("npm i @scope/pkg", {"@scope/pkg": 400})
        self.assertIn("registry.npmjs.org/@scope%2Fpkg", fake.urls[0])

    def test_non_bash_tools_are_ignored(self):
        stdin = io.StringIO(json.dumps({"tool_name": "Write", "tool_input": {"content": "npm install x"}}))
        with mock.patch.object(sys, "stdin", stdin):
            self.assertEqual(paket.main(), 0)


def user(text):
    return {"type": "user", "message": {"content": text}}


def tool(name, **inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


def say(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


class StopHook(unittest.TestCase):
    def test_edit_without_check_blocks(self):
        r = beleg.verdict([user("fix it"), tool("Edit", file_path="src/app.ts"), say("Erledigt.")])
        self.assertIn("app.ts", r)

    def test_edit_then_test_passes(self):
        r = beleg.verdict([user("fix"), tool("Edit", file_path="a.py"), tool("Bash", command="pytest -q"),
                           say("Erledigt, Tests gruen.")])
        self.assertIsNone(r)

    def test_check_before_edit_does_not_count(self):
        r = beleg.verdict([user("fix"), tool("Bash", command="npm test"), tool("Edit", file_path="a.ts"), say("ok")])
        self.assertIsNotNone(r)

    def test_docs_edit_needs_no_check(self):
        self.assertIsNone(beleg.verdict([user("x"), tool("Edit", file_path="README.md"), say("ok")]))

    def test_claim_without_any_check_blocks(self):
        r = beleg.verdict([user("geht das?"), say("Ja, alle Tests sind gruen und es ist live.")])
        self.assertIn("Tests sind gruen", r)

    def test_claim_with_check_passes(self):
        r = beleg.verdict([user("geht das?"), tool("Bash", command="curl -sI https://x"), say("Ist live.")])
        self.assertIsNone(r)

    def test_mentions_are_not_checks(self):
        for cmd in ("echo pytest", "cat /tmp/npm.log", "true # pytest", "grep test src", "echo 'x; pytest'",
                    "true # Hinweis; pytest", "cat <<EOF\npytest\nEOF"):
            r = beleg.verdict([user("fix"), tool("Edit", file_path="a.py"), tool("Bash", command=cmd), say("ok")])
            self.assertIsNotNone(r, cmd)
        for cmd in ("cd app && npm test", "CI=1 pytest -q", "./scripts/check.sh", "bash -n install.sh",
                    "sudo -u root pytest -q", "cat <<EOF > x\nhallo\nEOF\npytest",
                    "# Tests ausfuehren\nnpm test", '"./node_modules/.bin/tsc" --noEmit'):
            r = beleg.verdict([user("fix"), tool("Edit", file_path="a.py"), tool("Bash", command=cmd), say("ok")])
            self.assertIsNone(r, cmd)

    def test_negated_claims_pass(self):
        for text in ("Nicht getestet. Nicht verifiziert.", "Das ist noch nicht live.", "Not yet tested.",
                     "Ohne Zugang konnte ich das nicht verifiziert bekommen.", "Weder getestet noch verifiziert."):
            self.assertIsNone(beleg.verdict([user("x"), say(text)]), text)
        self.assertIsNotNone(beleg.verdict([user("x"), say("Ohne Probleme getestet.")]))

    def test_plain_answer_passes(self):
        self.assertIsNone(beleg.verdict([user("was ist x?"), say("x ist eine Bibliothek fuer y.")]))

    def test_only_current_turn_counts(self):
        entries = [user("a"), tool("Bash", command="npm test"), say("ok"), user("b"),
                   say("All tests pass.")]
        self.assertIsNotNone(beleg.verdict(entries))

    def test_last_assistant_message_field_wins(self):
        r = beleg.verdict([user("x"), say("neutral")], last_message="Successfully deployed.")
        self.assertIsNotNone(r)

    def test_main_respects_stop_hook_active(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            for e in [user("x"), say("Tests sind gruen.")]:
                fh.write(json.dumps(e) + "\n")
        try:
            for active, expect_output in ((True, False), (False, True)):
                out = io.StringIO()
                stdin = io.StringIO(json.dumps({"transcript_path": fh.name, "stop_hook_active": active}))
                with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", out):
                    beleg.main()
                self.assertEqual(bool(out.getvalue()), expect_output)
                if expect_output:
                    self.assertEqual(json.loads(out.getvalue())["decision"], "block")
        finally:
            os.unlink(fh.name)


if __name__ == "__main__":
    unittest.main()
