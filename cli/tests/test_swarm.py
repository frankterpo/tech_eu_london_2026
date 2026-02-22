from agent.commands.swarm import SwarmTask, _command_for_task, _normalize_tasks


def test_normalize_tasks_from_dict_payload():
    payload = {
        "tasks": [
            {"id": "t1", "prompt": "Create invoice"},
            {"id": "t2", "skill_id": "envoice.sales_invoice.existing"},
            {"id": "invalid"},
        ]
    }
    tasks = _normalize_tasks(payload, default_prompt_task_type="extrapolate")
    assert len(tasks) == 2
    assert tasks[0].id == "t1"
    assert tasks[0].prompt == "Create invoice"
    assert tasks[0].task_type == "extrapolate"
    assert tasks[1].skill_id == "envoice.sales_invoice.existing"
    assert tasks[1].task_type == "run"


def test_command_for_prompt_task():
    task = SwarmTask(
        id="p1", prompt="Create invoice", task_type="ask", platform_id="envoice"
    )
    cmd = _command_for_task(task)
    assert cmd[:3] == ["agent", "ask", "Create invoice"]
    assert "--yes" in cmd
    assert "--auto-acquire" in cmd
    assert "--learn" in cmd


def test_command_for_run_task():
    task = SwarmTask(
        id="r1",
        skill_id="envoice.sales_invoice.existing",
        task_type="run",
        input_file=".state/bench_inputs/invoice_smoke.json",
    )
    cmd = _command_for_task(task)
    assert cmd[0:3] == ["agent", "run", "envoice.sales_invoice.existing"]
    assert cmd[-1] == ".state/bench_inputs/invoice_smoke.json"


def test_command_for_prompt_learning_task():
    task = SwarmTask(
        id="learn1",
        prompt="Create invoice",
        task_type="extrapolate",
        platform_id="envoice",
    )
    cmd = _command_for_task(task)
    assert cmd[0:2] == ["agent", "extrapolate"]
    assert "--skill-id" in cmd
