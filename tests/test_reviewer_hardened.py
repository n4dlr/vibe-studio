import pytest
from vibe_studio.agents.reviewer_agent import ReviewerAgent, ReviewSeverity, ReviewIssue, ReviewResult


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


def test_reviewer_detects_credentials():
    reviewer = ReviewerAgent()
    diff = """--- a/config.py
+++ b/config.py
@@ -1,2 +1,3 @@
+API_KEY = "sk-1234567890abcdef1234567890"
+PASSWORD = "super_secret_password"
"""
    res = reviewer.review_diff(diff)
    assert not res.passed
    assert res.score < 70
    assert any(i.rule_id == "S001" for i in res.issues)
    assert any(i.severity == ReviewSeverity.ERROR for i in res.issues)


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


def test_reviewer_file_review(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("import os\n\ndef run():\n    try:\n        eval('1+1')\n    except:\n        print('bad')\n")
    reviewer = ReviewerAgent()
    res = reviewer.review_file(f)
    assert res.score < 100
    assert len(res.issues) >= 2
    report = res.format_report()
    assert "Score:" in report
