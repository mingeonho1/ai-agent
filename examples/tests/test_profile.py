"""Tests for the example-profile renderer (examples/render.py) and the patsol example.

Stdlib unittest only. No network. Everything renders into temp dirs; the real
~/.claude is never touched.

Run from the repo root:
    python3 -m unittest discover -s examples/tests -v
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

EXAMPLES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_DIR = EXAMPLES_DIR
RENDER = os.path.join(PROFILES_DIR, "render.py")
PROFILE = "patsol"
PROFILE_DIR = os.path.join(PROFILES_DIR, PROFILE)
PROFILE_JSON = os.path.join(PROFILE_DIR, "profile.json")

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")
HOOK_COMMAND_FRAGMENT = "worklog/bin/wandsol_track_hook.py"


def run_render(args):
    """Run render.py with args; return (returncode, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, RENDER] + args,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def load_profile():
    with open(PROFILE_JSON, encoding="utf-8") as f:
        return json.load(f)


def asked_variables(prof):
    return [v for v in prof["variables"] if not v.get("auto")]


def full_answers(prof):
    """A value for every asked variable (example, else a synthetic value)."""
    ans = {}
    for v in asked_variables(prof):
        val = v.get("example") or v.get("default")
        if not val:
            val = "VAL_" + v["name"]
        ans[v["name"]] = val
    return ans


def iter_profile_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".pyc") or ".bak" in fn:
                continue
            yield os.path.join(dirpath, fn)


def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


class TempDirCase(unittest.TestCase):
    """Base: a temp dir with an `out` subdir, removed afterwards."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="example-test-")
        self.out = os.path.join(self.tmp, "home")
        os.makedirs(self.out)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_answers(self, answers, name="answers.json"):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(answers, f)
        return path


class ListQuestionsTest(unittest.TestCase):
    def test_list_questions_is_valid_json_with_all_variables(self):
        rc, out, err = run_render([PROFILE, "--list-questions"])
        self.assertEqual(rc, 0, err)
        data = json.loads(out)  # must be valid JSON
        self.assertIsInstance(data, list)
        prof = load_profile()
        expected = {v["name"] for v in asked_variables(prof)}
        got = {q["name"] for q in data}
        self.assertEqual(got, expected)
        for q in data:
            self.assertIn("question", q)
            self.assertIn("required", q)


class FullRenderTest(TempDirCase):
    def setUp(self):
        super().setUp()
        self.answers_path = self.write_answers(full_answers(load_profile()))

    def _render(self):
        return run_render([PROFILE, "--out", self.out,
                           "--answers", self.answers_path, "--yes"])

    def test_full_render_leaves_no_placeholder(self):
        rc, out, err = self._render()
        self.assertEqual(rc, 0, err)
        leftover = []
        for path in iter_profile_files(self.out):
            text = read_text(path)
            if text and PLACEHOLDER_RE.search(text):
                leftover.append(path)
        self.assertEqual(leftover, [], "placeholders remain in: %s" % leftover)

    def test_expected_files_exist(self):
        rc, out, err = self._render()
        self.assertEqual(rc, 0, err)
        expected = [
            os.path.join(self.out, "commands", "new-task.md"),
            os.path.join(self.out, "commands", "apply-review.md"),
            os.path.join(self.out, "agents", "toss-senior-challenger.md"),
            os.path.join(self.out, "skills", "jev-scope", "jev.py"),
            os.path.join(self.out, "worklog", "bin", "wandsol_track_hook.py"),
            os.path.join(self.out, "worklog", "config.json"),
            os.path.join(self.out, "settings.json"),
            os.path.join(self.out, "example-profiles", PROFILE, "scripts", "new-task.py"),
            os.path.join(self.out, "example-profiles", PROFILE, "routines",
                         "slack-digest", "SKILL.md"),
            os.path.join(self.out, "example-profiles", PROFILE, "answers.json"),
        ]
        for p in expected:
            self.assertTrue(os.path.isfile(p), "missing: %s" % p)

    def test_settings_hook_points_into_out_dir(self):
        rc, out, err = self._render()
        self.assertEqual(rc, 0, err)
        with open(os.path.join(self.out, "settings.json"), encoding="utf-8") as f:
            settings = json.load(f)
        cmds = _all_hook_commands(settings)
        wandsol = [c for c in cmds if HOOK_COMMAND_FRAGMENT in c]
        self.assertEqual(len(wandsol), 1, cmds)
        self.assertIn(os.path.abspath(self.out), wandsol[0])


class SettingsMergeTest(TempDirCase):
    def setUp(self):
        super().setUp()
        self.answers_path = self.write_answers(full_answers(load_profile()))
        # Pre-existing user settings with an unrelated key and an unrelated hook.
        self.preexisting = {
            "model": "opus",
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command",
                                "command": "python3 /my/own/hook.py",
                                "timeout": 3}]}
                ]
            },
        }
        with open(os.path.join(self.out, "settings.json"), "w", encoding="utf-8") as f:
            json.dump(self.preexisting, f)

    def _render(self):
        return run_render([PROFILE, "--out", self.out,
                           "--answers", self.answers_path, "--yes"])

    def test_merge_idempotent_and_preserves_user_keys(self):
        rc1, _o1, e1 = self._render()
        self.assertEqual(rc1, 0, e1)
        rc2, _o2, e2 = self._render()  # second run must not duplicate
        self.assertEqual(rc2, 0, e2)

        with open(os.path.join(self.out, "settings.json"), encoding="utf-8") as f:
            settings = json.load(f)

        # user key preserved
        self.assertEqual(settings.get("model"), "opus")
        cmds = _all_hook_commands(settings)
        # pre-existing unrelated hook preserved
        self.assertIn("python3 /my/own/hook.py", cmds)
        # profile hook present exactly once after two runs
        wandsol = [c for c in cmds if HOOK_COMMAND_FRAGMENT in c]
        self.assertEqual(len(wandsol), 1, cmds)


class MissingRequiredTest(TempDirCase):
    def test_missing_required_exits_nonzero_and_writes_nothing(self):
        prof = load_profile()
        required = [v for v in asked_variables(prof)
                    if v.get("required") and not v.get("default")]
        self.assertTrue(required, "profile should declare at least one required var")
        drop = required[0]["name"]
        answers = full_answers(prof)
        del answers[drop]
        apath = self.write_answers(answers, "partial.json")

        rc, out, err = run_render([PROFILE, "--out", self.out,
                                   "--answers", apath, "--yes"])
        self.assertNotEqual(rc, 0)
        # nothing written
        self.assertFalse(os.path.exists(os.path.join(self.out, "settings.json")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "skills")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "commands")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "example-profiles")))


class PlaceholderDeclarationTest(unittest.TestCase):
    """Every {{VAR}} used under examples/patsol is declared in profile.json,
    and every declared variable is actually used."""

    def test_used_equals_declared(self):
        prof = load_profile()
        declared = {v["name"] for v in prof["variables"]}

        used = set()
        for path in iter_profile_files(PROFILE_DIR):
            if os.path.abspath(path) == os.path.abspath(PROFILE_JSON):
                continue
            text = read_text(path)
            if text:
                used.update(PLACEHOLDER_RE.findall(text))

        undeclared = used - declared
        unused = declared - used
        self.assertEqual(undeclared, set(),
                         "used but not declared in profile.json: %s" % sorted(undeclared))
        self.assertEqual(unused, set(),
                         "declared but never used: %s" % sorted(unused))


class InvalidProfileNameTest(unittest.TestCase):
    def test_path_traversal_names_rejected(self):
        for bad in ("../x", "a/b", "/abs", "..", "x/../y"):
            rc, out, err = run_render([bad, "--list-questions"])
            self.assertNotEqual(rc, 0, "accepted bad profile name %r" % bad)
            self.assertIn("invalid profile name", (out + err).lower())


class RepoPrefixDefaultsComposeTest(unittest.TestCase):
    """profile.json defaults must compose with the sibling-repo glob
    `{{REPO_PREFIX}}-*`: the backend/frontend repo-name defaults have to start
    with the REPO_PREFIX default, or that glob never matches them."""

    def test_repo_name_defaults_start_with_prefix(self):
        prof = load_profile()
        defaults = {v["name"]: v.get("default") for v in prof["variables"]}
        prefix = defaults.get("REPO_PREFIX")
        self.assertTrue(prefix, "REPO_PREFIX must declare a default")
        for name in ("BACKEND_REPO_NAME", "FRONTEND_REPO_NAME"):
            val = defaults.get(name)
            self.assertTrue(val, "%s must declare a default" % name)
            self.assertTrue(
                val.startswith(prefix + "-"),
                "%s default %r must start with REPO_PREFIX default %r + '-' "
                "so the `%s-*` glob matches it" % (name, val, prefix, prefix))


class EmptyOptionalVarWarningTest(TempDirCase):
    """render.py warns (without failing) when a routine references an optional
    variable left empty — e.g. SLACK_USER_ID -> an empty `<@>` mention."""

    def test_warns_about_empty_routine_var(self):
        answers = full_answers(load_profile())
        answers["SLACK_USER_ID"] = ""  # referenced by the slack-digest routine
        apath = self.write_answers(answers)
        rc, out, err = run_render([PROFILE, "--out", self.out,
                                   "--answers", apath, "--yes"])
        self.assertEqual(rc, 0, err)  # warning, not a failure
        combined = out + err
        self.assertIn("SLACK_USER_ID", combined)
        self.assertIn("warning", combined)  # default --lang en


class StandaloneTest(TempDirCase):
    """The example must not depend on claudi being installed."""

    def test_no_claudi_only_paths_left(self):
        bad = []
        for path in iter_profile_files(PROFILE_DIR):
            text = read_text(path)
            if text and ("claudi-profiles" in text or "claudi/lang.md" in text
                         or "monitor/bin" in text):
                bad.append(path)
        self.assertEqual(bad, [])

    def test_rendered_python_scripts_compile(self):
        import py_compile
        apath = self.write_answers(full_answers(load_profile()))
        rc, _o, err = run_render([PROFILE, "--out", self.out,
                                  "--answers", apath, "--yes"])
        self.assertEqual(rc, 0, err)
        count = 0
        for path in iter_profile_files(self.out):
            if path.endswith(".py"):
                py_compile.compile(path, cfile=os.path.join(self.tmp, "x.pyc"),
                                   doraise=True)
                count += 1
        self.assertGreater(count, 0)


def _all_hook_commands(settings):
    out = []
    for _event, groups in (settings.get("hooks") or {}).items():
        for g in groups:
            for h in (g.get("hooks") or []):
                if h.get("type") == "command" and "command" in h:
                    out.append(h["command"])
    return out


def _load_render_module():
    """Load render.py as a fresh module instance (so we can retarget HERE).
    render.py 를 새 모듈 인스턴스로 로드한다(HERE 재지정용)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("render_under_test", RENDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RenderLangTest(unittest.TestCase):
    """render.py selects question_ko for --lang ko (fallback to question), and
    --list-questions emits both fields. Uses a temp fake profile so it does not
    depend on the real patsol profile.json."""

    def setUp(self):
        self.mod = _load_render_module()
        self.tmp = tempfile.mkdtemp(prefix="example-test-")
        self.mod.HERE = self.tmp  # retarget the profile root at the temp dir
        os.makedirs(os.path.join(self.tmp, "fake"))
        prof = {
            "name": "fake",
            "description": "fake",
            "variables": [
                {"name": "WITH_KO", "question": "English question",
                 "question_ko": "한국어 질문", "required": False},
                {"name": "NO_KO", "question": "Only English", "required": False},
            ],
        }
        with open(os.path.join(self.tmp, "fake", "profile.json"), "w",
                  encoding="utf-8") as f:
            json.dump(prof, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _var(self, name):
        _pdir, prof = self.mod.load_profile("fake")
        for v in prof["variables"]:
            if v["name"] == name:
                return v
        raise AssertionError("no such var: %s" % name)

    def test_question_for_picks_ko_and_falls_back(self):
        self.assertEqual(self.mod.question_for(self._var("WITH_KO"), "ko"),
                         "한국어 질문")
        self.assertEqual(self.mod.question_for(self._var("WITH_KO"), "en"),
                         "English question")
        # fallback to English question when question_ko is absent
        self.assertEqual(self.mod.question_for(self._var("NO_KO"), "ko"),
                         "Only English")

    def test_prompt_one_shows_ko_question(self):
        import builtins
        captured = {}
        orig = builtins.input

        def fake_input(prompt=""):
            captured["p"] = prompt
            return "value"

        builtins.input = fake_input
        try:
            self.mod.set_lang("ko")
            self.mod.prompt_one(self._var("WITH_KO"), None, "ko")
        finally:
            builtins.input = orig
        self.assertIn("한국어 질문", captured["p"])

    def test_list_questions_includes_both_fields(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = self.mod.main(["fake", "--list-questions", "--lang", "ko"])
        self.assertEqual(rc, 0)
        data = {q["name"]: q for q in json.loads(buf.getvalue())}
        self.assertEqual(data["WITH_KO"]["question"], "English question")
        self.assertEqual(data["WITH_KO"]["question_ko"], "한국어 질문")
        self.assertIsNone(data["NO_KO"]["question_ko"])


if __name__ == "__main__":
    unittest.main()
