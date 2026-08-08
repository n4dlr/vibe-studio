"""Hardened ReviewerAgent tests — full rule coverage."""
import pytest
from vibe_studio.agents.reviewer_agent import ReviewerAgent, ReviewSeverity, ReviewIssue, ReviewResult


# ── Helpers ──────────────────────────────────────────────────────────────────

def _diff(added_lines: list, start: int = 1) -> str:
    """Build a minimal unified diff with the given added lines."""
    header = f"@@ -0,0 +{start},{len(added_lines)} @@\n"
    body = "".join(f"+{line}\n" for line in added_lines)
    return f"--- a/x.py\n+++ b/x.py\n{header}{body}"


# ── Rule E001: bare except ────────────────────────────────────────────────────

def test_reviewer_passes_clean_diff():
    reviewer = ReviewerAgent()
    diff = """--- a/clean.py
+++ b/clean.py
@@ -1,3 +1,3 @@
 def add(a: int, b: int) -> int:
-    return a - b
+    return a + b
"""
    res = reviewer.review_diff(diff)
    assert res.passed
    assert res.score == 100
    assert len(res.issues) == 0


def test_reviewer_detects_bare_except():
    reviewer = ReviewerAgent()
    diff = _diff(["try:", "    do_something()", "except:", "    pass"])
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "E001" for i in res.issues)
    assert any(i.severity == ReviewSeverity.ERROR for i in res.issues)
    assert res.score < 100


def test_noqa_suppresses_bare_except():
    reviewer = ReviewerAgent()
    diff = _diff(["except:  # noqa"])
    res = reviewer.review_diff(diff)
    assert not any(i.rule_id == "E001" for i in res.issues)


# ── Rule W001: print statements ───────────────────────────────────────────────

def test_reviewer_detects_print():
    reviewer = ReviewerAgent()
    diff = _diff(["print('debug')"])
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "W001" for i in res.issues)
    # Only reported once per diff even if multiple print() calls
    diff2 = _diff(["print('a')", "print('b')", "print('c')"])
    res2 = reviewer.review_diff(diff2)
    w001 = [i for i in res2.issues if i.rule_id == "W001"]
    assert len(w001) == 1


def test_noqa_suppresses_print():
    reviewer = ReviewerAgent()
    diff = _diff(["print('debug')  # noqa"])
    res = reviewer.review_diff(diff)
    assert not any(i.rule_id == "W001" for i in res.issues)


# ── Rule W002: TODO/FIXME markers ────────────────────────────────────────────

def test_reviewer_detects_todo():
    reviewer = ReviewerAgent()
    diff = _diff(["# TODO: fix this later"])
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "W002" for i in res.issues)
    diff2 = _diff(["# TODO: fix a", "# FIXME: fix b"])
    res2 = reviewer.review_diff(diff2)
    w002 = [i for i in res2.issues if i.rule_id == "W002"]
    assert len(w002) == 1


# ── Rule S001: hardcoded credentials ─────────────────────────────────────────

def test_reviewer_detects_credentials():
    reviewer = ReviewerAgent()
    diff = _diff(['API_KEY = "sk-1234567890abcdef1234567890"', 'PASSWORD = "super_secret_password"'])
    res = reviewer.review_diff(diff)
    assert not res.passed
    assert res.score < 70
    assert any(i.rule_id == "S001" for i in res.issues)
    assert any(i.severity == ReviewSeverity.ERROR for i in res.issues)


def test_reviewer_detects_aws_token():
    reviewer = ReviewerAgent()
    diff = _diff(["aws_key = 'AKIAIOSFODNN7EXAMPLE'"])
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "S001" for i in res.issues)


def test_reviewer_detects_ghp_token():
    reviewer = ReviewerAgent()
    diff = _diff(["token = 'ghp_" + "A" * 36 + "'"])
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "S001" for i in res.issues)


# ── Rule S002: dangerous patterns ────────────────────────────────────────────

def test_reviewer_detects_eval():
    reviewer = ReviewerAgent()
    diff = _diff(["result = eval(user_input)"])
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "S002" for i in res.issues)


def test_reviewer_detects_exec():
    reviewer = ReviewerAgent()
    diff = _diff(["exec(code)"])
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "S002" for i in res.issues)


def test_reviewer_detects_shell_true():
    reviewer = ReviewerAgent()
    diff = _diff(["subprocess.run(cmd, shell=True)"])
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "S002" for i in res.issues)


def test_noqa_suppresses_dangerous():
    reviewer = ReviewerAgent()
    diff = _diff(["result = eval(x)  # noqa"])
    res = reviewer.review_diff(diff)
    assert not any(i.rule_id == "S002" for i in res.issues)


# ── Rule S003: SQL f-string injection ────────────────────────────────────────

def test_reviewer_detects_sql_injection():
    reviewer = ReviewerAgent()
    diff = _diff(['cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'])
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "S003" for i in res.issues)
    assert any(i.severity == ReviewSeverity.ERROR for i in res.issues)


# ── Rule R001: naming conventions ────────────────────────────────────────────

def test_reviewer_detects_lowercase_class():
    reviewer = ReviewerAgent()
    diff = _diff(["class myhandler:"])
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "R001" for i in res.issues)


def test_reviewer_allows_camel_case_class():
    reviewer = ReviewerAgent()
    diff = _diff(["class MyHandler:"])
    res = reviewer.review_diff(diff)
    assert not any(i.rule_id == "R001" for i in res.issues)


# ── Rule R002: missing return annotations ────────────────────────────────────

def test_reviewer_detects_missing_annotations():
    reviewer = ReviewerAgent()
    lines = [
        "def foo(x):",
        "def bar(y):",
        "def baz(z):",
        "def qux():",
    ]
    diff = _diff(lines)
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "R002" for i in res.issues)
    assert all(i.severity == ReviewSeverity.INFO for i in res.issues if i.rule_id == "R002")


def test_reviewer_no_annotation_rule_below_threshold():
    reviewer = ReviewerAgent()
    diff = _diff(["def foo(x):", "def bar(y):"])
    res = reviewer.review_diff(diff)
    assert not any(i.rule_id == "R002" for i in res.issues)


# ── Rule C001: nesting depth ─────────────────────────────────────────────────

def test_reviewer_detects_high_nesting():
    reviewer = ReviewerAgent()
    lines = [
        "def process():",
        "    if a:",
        "        for x in y:",
        "            if b:",
        "                while c:",
        "                    if d:",
        "                        return x",
    ]
    diff = _diff(lines)
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "C001" for i in res.issues)


# ── Score clamping & pass/fail ────────────────────────────────────────────────

def test_score_never_goes_below_zero():
    reviewer = ReviewerAgent()
    lines = [
        'PASSWORD = "hardcoded_pass_xyz"',
        "result = eval(user_data)",
        "except:",
        'cursor.execute(f"SELECT * FROM t WHERE id = {uid}")',
        "print('debug')",
    ]
    diff = _diff(lines)
    res = reviewer.review_diff(diff)
    assert res.score >= 0


def test_empty_diff_always_passes():
    reviewer = ReviewerAgent()
    res = reviewer.review_diff("")
    assert res.passed
    assert res.score == 100


def test_empty_diff_whitespace_only():
    reviewer = ReviewerAgent()
    res = reviewer.review_diff("   \n  ")
    assert res.passed
    assert res.score == 100


# ── ReviewResult properties ───────────────────────────────────────────────────

def test_review_result_summary_pass():
    reviewer = ReviewerAgent()
    res = reviewer.review_diff(_diff(["x = 1"]))
    assert "passed" in res.summary.lower() or "\u2713" in res.summary


def test_review_result_summary_fail():
    reviewer = ReviewerAgent()
    diff = _diff(['PASSWORD = "abc123xyz"'])
    res = reviewer.review_diff(diff)
    if not res.passed:
        assert "failed" in res.summary.lower() or "\u2717" in res.summary


def test_format_report_contains_score():
    reviewer = ReviewerAgent()
    diff = _diff(["print('debug')"])
    res = reviewer.review_diff(diff)
    report = res.format_report()
    assert "Score:" in report
    assert "W001" in report


def test_format_report_line_numbers():
    reviewer = ReviewerAgent()
    diff = """--- a/x.py
+++ b/x.py
@@ -0,0 +5,3 @@
+try:
+    pass
+except:
+    pass
"""
    res = reviewer.review_diff(diff)
    report = res.format_report()
    assert "Score" in report


# ── review_file ───────────────────────────────────────────────────────────────

def test_reviewer_file_review(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("import os\n\ndef run():\n    try:\n        eval('1+1')\n    except:\n        print('bad')\n")
    reviewer = ReviewerAgent()
    res = reviewer.review_file(f)
    assert res.score < 100
    assert len(res.issues) >= 2
    report = res.format_report()
    assert "Score:" in report


def test_reviewer_file_review_missing_file(tmp_path):
    reviewer = ReviewerAgent()
    res = reviewer.review_file(tmp_path / "nonexistent.py")
    assert not res.passed
    assert res.score == 0


def test_reviewer_file_review_with_content(tmp_path):
    reviewer = ReviewerAgent()
    f = tmp_path / "good.py"
    f.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")
    res = reviewer.review_file(f, content="def add(a: int, b: int) -> int:\n    return a + b\n")
    assert res.passed
    assert res.score == 100


# ── errors / warnings properties ─────────────────────────────────────────────

def test_review_result_errors_and_warnings_properties():
    reviewer = ReviewerAgent()
    diff = _diff([
        'API_KEY = "sk-abcdefghij1234567890"',
        "print('debug')",
    ])
    res = reviewer.review_diff(diff)
    assert len(res.errors) > 0
    assert all(i.severity == ReviewSeverity.ERROR for i in res.errors)
    assert all(i.severity == ReviewSeverity.WARNING for i in res.warnings)

# ── detect bare except and print together ──────────────────────────────────

def test_reviewer_detects_bare_except_and_print():
    reviewer = ReviewerAgent()
    diff = """--- a/utils.py
+++ b/utils.py
@@ -1,5 +1,7 @@
 def process():
     try:
         do_work()
-    except ValueError:
-        pass
+    except:
+        print("error happened")
"""
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "E001" for i in res.issues)
    assert any(i.rule_id == "W001" for i in res.issues)


def test_reviewer_detects_dangerous_patterns():
    reviewer = ReviewerAgent()
    diff = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
+result = eval(user_input)
"""
    res = reviewer.review_diff(diff)
    assert any(i.rule_id == "S002" for i in res.issues)
