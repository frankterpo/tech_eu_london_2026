from agent.commands.eval_cmd import _heuristic_evaluation


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
