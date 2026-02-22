from agent.commands.benchmark import summarize_benchmark_results


def test_summarize_benchmark_results_counts_success_and_failures():
    runs = [
        {"run_id": "a", "decision": "success"},
        {"run_id": "b", "decision": "failure", "failure_class": "validation_error"},
        {"run_id": "c", "decision": "failure", "failure_class": "validation_error"},
        {"run_id": "d", "decision": "failure", "failure_class": "runtime_error"},
    ]
    summary = summarize_benchmark_results(
        skill_id="envoice.sales_invoice.existing",
        runs=runs,
        started_at="2026-02-22T00:00:00Z",
        ended_at="2026-02-22T00:01:00Z",
    )
    assert summary["total_runs"] == 4
    assert summary["success_count"] == 1
    assert summary["failure_count"] == 3
    assert summary["success_rate"] == 0.25
    assert summary["failure_classes"]["validation_error"] == 2
    assert summary["failure_classes"]["runtime_error"] == 1
