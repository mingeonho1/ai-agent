#!/usr/bin/env python3
"""Tests for the fable orchestration gate + the fable on/off/status switch.
fable 오케스트레이션 게이트 + fable on/off/status 스위치 테스트.

Stdlib unittest, temp directories only. CLAUDE_CONFIG_DIR points at a temp path so
the real ~/.claude is never touched.
표준 라이브러리 unittest, 임시 디렉터리만 사용. CLAUDE_CONFIG_DIR 를 임시 경로로
지정해 실제 ~/.claude 를 건드리지 않는다.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FABLE_SRC = Path(__file__).resolve().parent.parent
GATE = FABLE_SRC / "hooks" / "orchestration-gate.py"


class GateTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Path(tempfile.mkdtemp(prefix="fable-gate-"))

    def tearDown(self):
        shutil.rmtree(self.cfg, ignore_errors=True)

    def set_state(self, state):
        (self.cfg / ".fable-state").write_text(state)

    def run_gate(self, payload, raw=None):
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = str(self.cfg)
        stdin = raw if raw is not None else json.dumps(payload)
        return subprocess.run([sys.executable, str(GATE)], input=stdin,
                              capture_output=True, text=True, env=env)

    def edit(self, path, session="s1", prompt="p1"):
        return {"tool_name": "Edit",
                "tool_input": {"file_path": path},
                "session_id": session, "prompt_id": prompt}

    def bash(self, cmd):
        return {"tool_name": "Bash", "tool_input": {"command": cmd},
                "session_id": "s1", "prompt_id": "p1"}

    def test_state_off_allows(self):
        self.set_state("off")
        r = self.run_gate(self.edit("a.py"))
        self.assertEqual(r.returncode, 0)

    def test_no_state_file_allows(self):
        # No state file → treated as off → pass
        # 상태 파일 없음 → off 취급 → 통과
        r = self.run_gate(self.edit("a.py"))
        self.assertEqual(r.returncode, 0)

    def test_third_code_edit_denied(self):
        self.set_state("on")
        self.assertEqual(self.run_gate(self.edit("a.py")).returncode, 0)
        self.assertEqual(self.run_gate(self.edit("b.py")).returncode, 0)
        r3 = self.run_gate(self.edit("c.py"))
        self.assertEqual(r3.returncode, 2)
        self.assertIn("[fable", r3.stderr)

    def test_same_file_not_counted(self):
        self.set_state("on")
        self.run_gate(self.edit("a.py"))
        self.run_gate(self.edit("b.py"))
        # Re-editing an already-counted file does not count toward the limit → pass
        # 이미 센 파일 재수정은 한도에 안 들어감 → 통과
        self.assertEqual(self.run_gate(self.edit("a.py")).returncode, 0)

    def test_bash_inplace_denied(self):
        self.set_state("on")
        p = {"tool_name": "Bash",
             "tool_input": {"command": "sed -i 's/a/b/' x.py"},
             "session_id": "s1", "prompt_id": "p1"}
        r = self.run_gate(p)
        self.assertEqual(r.returncode, 2)

    def test_bash_quoted_redirect_denied(self):
        self.set_state("on")
        # Quoted targets containing spaces are also denied as redirect writes.
        # 공백이 든 따옴표 대상도 리다이렉트 쓰기로 차단한다.
        for cmd in ('echo hi > "my file.py"', "printf x > 'a b.ts'"):
            p = {"tool_name": "Bash", "tool_input": {"command": cmd},
                 "session_id": "s1", "prompt_id": "p1"}
            r = self.run_gate(p)
            self.assertEqual(r.returncode, 2, cmd)

    def test_bash_redirect_denied(self):
        self.set_state("on")
        # Redirects/in-place edits into code files stay denied.
        # 코드 파일로의 리다이렉트/in-place 수정은 계속 차단한다.
        for cmd in (
            "echo hi > x.py",
            "cat > x.ts <<EOF",
            "cat >> app.js",
            "tee -a f.py",
            'echo hi > "my file.py"',
            "echo hi > 'a b.ts'",
            "sed -i 's/a/b/' x.py",
            "perl -i -pe 's/a/b/' y.py",
        ):
            r = self.run_gate(self.bash(cmd))
            self.assertEqual(r.returncode, 2, cmd)

    def test_bash_quoted_content_allowed(self):
        self.set_state("on")
        # A > or code filename inside a string literal is not a redirect, so it must pass.
        # 문자열 리터럴 안의 > / 코드 파일명은 리다이렉트가 아니므로 통과해야 한다.
        for cmd in (
            'echo "a > b.py"',
            "echo 'done > a.py'",
            'echo "x >> y.ts"',
            'git commit -m "fix > out.py handling"',
        ):
            r = self.run_gate(self.bash(cmd))
            self.assertEqual(r.returncode, 0, cmd)

    def test_bash_harmless_redirect_allowed(self):
        self.set_state("on")
        # Redirects/commands that do not write code files pass.
        # 코드 파일을 쓰지 않는 리다이렉트/명령은 통과한다.
        for cmd in (
            "git log > /dev/null",
            "make 2>&1 | tee build.log",
            "cmd 2>&1",
            "python s.py > out.json",
            "git status",
        ):
            r = self.run_gate(self.bash(cmd))
            self.assertEqual(r.returncode, 0, cmd)

    def test_bash_heredoc(self):
        self.set_state("on")
        # Heredoc bodies are data: a "> x.py" inside the body must not block,
        # but a redirect on the header line still must.
        # heredoc 본문은 데이터: 본문 안의 "> x.py" 는 통과, 헤더 줄 리다이렉트는 차단.
        cases = (
            ("cat <<'EOF'\nsee > report.py for details\nEOF", 0),
            ("git commit -F - <<EOF\nwrite output > report.py\nEOF\ngit log", 0),
            ("cat <<EOF > x.py\nprint(1)\nEOF", 2),
            ("cat > y.py <<'EOF'\nprint(1)\nEOF", 2),
            ("echo hi > z.py", 2),
            ("ls -la", 0),
        )
        for cmd, code in cases:
            r = self.run_gate(self.bash(cmd))
            self.assertEqual(r.returncode, code, cmd)

    def test_new_prompt_id_resets_counter(self):
        self.set_state("on")
        # Turn p1: up to 2 allowed, the 3rd denied.
        # p1 턴: 2개까지 허용, 3개째 차단.
        self.assertEqual(self.run_gate(self.edit("a.py", prompt="p1")).returncode, 0)
        self.assertEqual(self.run_gate(self.edit("b.py", prompt="p1")).returncode, 0)
        self.assertEqual(self.run_gate(self.edit("c.py", prompt="p1")).returncode, 2)
        # New turn (p2): counter resets → allowed again.
        # 새 턴(p2): 카운터 리셋 → 다시 허용.
        self.assertEqual(self.run_gate(self.edit("c.py", prompt="p2")).returncode, 0)

    def test_empty_prompt_id_never_denies(self):
        self.set_state("on")
        # Empty prompt_id (turn boundary unknown): no session-wide accumulation, always pass.
        # prompt_id 가 비면(턴 경계 모름) 세션 전체로 누적하지 않고 항상 통과.
        for name in ("a.py", "b.py", "c.py", "d.py"):
            r = self.run_gate(self.edit(name, prompt=""))
            self.assertEqual(r.returncode, 0, name)

    def test_subagent_allowed(self):
        self.set_state("on")
        # Subagents pass even on the 3rd file
        # 서브에이전트는 3개째여도 통과
        p = self.edit("z.py")
        p["agent_id"] = "sub-123"
        for _ in range(3):
            r = self.run_gate(p)
        self.assertEqual(r.returncode, 0)

    def test_non_code_file_allowed(self):
        self.set_state("on")
        for _ in range(3):
            r = self.run_gate(self.edit("README.md"))
        self.assertEqual(r.returncode, 0)

    def test_malformed_stdin_fail_open(self):
        self.set_state("on")
        r = self.run_gate(None, raw="this is not json")
        self.assertEqual(r.returncode, 0)


class FableSwitchTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Path(tempfile.mkdtemp(prefix="fable-switch-"))
        shutil.copytree(FABLE_SRC, self.cfg / "fable")
        self.fable = self.cfg / "fable" / "bin" / "fable"

    def tearDown(self):
        shutil.rmtree(self.cfg, ignore_errors=True)

    def run_fable(self, arg):
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = str(self.cfg)
        # Run explicitly via sh to avoid depending on +x
        # +x 의존을 피하려 명시적으로 sh 로 실행
        return subprocess.run(["sh", str(self.fable), arg],
                              capture_output=True, text=True, env=env)

    def test_on(self):
        r = self.run_fable("on")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.cfg / ".fable-state").read_text().strip(), "on")
        self.assertEqual((self.cfg / "fable" / "active.md").read_text(),
                         (self.cfg / "fable" / "fable.md").read_text())

    def test_off(self):
        self.run_fable("on")
        r = self.run_fable("off")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.cfg / ".fable-state").read_text().strip(), "off")
        self.assertEqual((self.cfg / "fable" / "active.md").read_text(),
                         (self.cfg / "fable" / "empty.md").read_text())

    def test_status(self):
        self.run_fable("off")
        r = self.run_fable("status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("off", r.stdout)
        self.run_fable("on")
        r = self.run_fable("status")
        self.assertIn("on", r.stdout)


if __name__ == "__main__":
    unittest.main()
