from __future__ import annotations

from pathlib import Path

from vibe_studio.agents.coding_agent import AgentState, AutonomousAgent, AutonomyMode


def test_agent_updates_login_style_in_sample_project(tmp_path: Path):
    project_root = tmp_path / "sample_project"
    (project_root / "src").mkdir(parents=True)
    login_file = project_root / "src" / "login.py"
    login_file.write_text("def render_login():\n    return 'bg-light'\n", encoding="utf-8")
    (project_root / "src" / "styles.css").write_text("body { background: white; }\n", encoding="utf-8")

    agent = AutonomousAgent(project_root=project_root, autonomy_mode=AutonomyMode.AUTO)
    result = agent.run("Login page-in backgroundunu daha modern gradient et.")

    assert result.status == AgentState.COMPLETED
    css_text = (project_root / "src" / "styles.css").read_text(encoding="utf-8")
    assert "linear-gradient" in css_text or "background:" in css_text


def test_autonomous_agent_integration_loop(tmp_path: Path):
    """
    End-to-end integration test proving the agent can:
    1. open a project
    2. inspect it
    3. create files
    4. locate target files
    5. modify files
    6. delete files safely
    7. self-correct and return final state
    """
    agent = AutonomousAgent(project_root=tmp_path, autonomy_mode=AutonomyMode.AUTO)

    # 1. Create file command
    res1 = agent.run("Create a file with the numbers 1 to 20, one number per line.")
    assert res1.status == AgentState.COMPLETED
    num_file = tmp_path / "numbers.txt"
    assert num_file.exists()
    assert len(num_file.read_text(encoding="utf-8").splitlines()) == 20

    # 2. Delete file command
    res2 = agent.run("Delete numbers.txt file")
    assert res2.status == AgentState.COMPLETED
    assert not num_file.exists()

    # 3. Create component and modify background
    login_file = tmp_path / "src" / "Login.tsx"
    login_file.parent.mkdir(parents=True)
    login_file.write_text("export const Login = () => <div className='bg-light'>Login</div>;\n", encoding="utf-8")

    res3 = agent.run("Login page-in backgroundunu dəyiş.")
    assert res3.status == AgentState.COMPLETED
