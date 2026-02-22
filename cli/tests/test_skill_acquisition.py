from agent.skill_acquisition import _has_ambiguous_invoice_row_selector


def test_detects_ambiguous_invoice_row_selector():
    spec = {
        "steps": [
            {
                "action": "fill",
                "selector": "input[name='sales_invoice__row[0]']",
                "value": "{{description}}",
            }
        ]
    }
    assert _has_ambiguous_invoice_row_selector(spec) is True


def test_ignores_explicit_invoice_row_selector():
    spec = {
        "steps": [
            {
                "action": "fill",
                "selector": "input[name='sales_invoice__row[0][description]']",
                "value": "{{description}}",
            },
            {
                "action": "fill_if_visible",
                "selector": "input[name='sales_invoice__row[0][item_amount]']",
                "value": "{{amount}}",
            },
        ]
    }
    assert _has_ambiguous_invoice_row_selector(spec) is False
