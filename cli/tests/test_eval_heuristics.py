from agent.commands.eval_cmd import _apply_strict_gate, _heuristic_evaluation


def test_heuristic_marks_validation_errors_as_failure():
    report = {
        "status": "success",
        "skill_id": "envoice.sales_invoice.existing",
        "validation_errors": ["Mandatory field is empty"],
    }
    result = _heuristic_evaluation(report)
    assert result["decision"] == "failure"
    assert result["failure_class"] == "validation_error"


def test_heuristic_marks_missing_created_record_as_failure():
    report = {
        "status": "success",
        "skill_id": "envoice.sales_invoice.existing",
        "validation_errors": [],
        "final_url": "https://app.envoice.eu/desktop/sale/add",
    }
    result = _heuristic_evaluation(report)
    assert result["decision"] == "failure"
    assert result["failure_class"] == "missing_created_record"


def test_heuristic_keeps_success_when_record_created():
    report = {
        "status": "success",
        "skill_id": "envoice.sales_invoice.existing",
        "created_invoice_id": "12084978",
        "validation_errors": [],
    }
    result = _heuristic_evaluation(report)
    assert result["decision"] == "success"


def test_strict_gate_overrides_dust_success_when_report_failed():
    report = {
        "status": "failed",
        "skill_id": "envoice.sales_invoice.existing",
        "error": "Timeout filling selector",
        "validation_errors": [],
    }
    dust_eval = {
        "decision": "success",
        "failure_class": "ui_obstructed",
        "reasons": ["Model believed issue is recoverable."],
        "patch": [],
    }
    result = _apply_strict_gate(dust_eval, report)
    assert result["decision"] == "failure"
    assert result["failure_class"] == "ui_obstructed"
    assert any("Strict gate override" in r for r in result["reasons"])
