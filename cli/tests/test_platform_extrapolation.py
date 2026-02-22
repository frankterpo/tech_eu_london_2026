from agent.platform_extrapolation import extrapolate_skill_from_platform_map


def test_extrapolate_skill_from_platform_map_builds_sales_invoice_flow():
    platform_map = {
        "base_urls": ["https://app.envoice.eu"],
        "signals": {
            "selectors": {
                "span#select2-buyerCompanyID-container": 12,
                "input#sales_invoice__invoice_date": 10,
                "input#sales_invoice__transaction_date": 9,
                "input#sales_invoice__due_days": 8,
                "input[name='sales_invoice__row[0][description]']": 8,
                "input[name='sales_invoice__row[0][item_amount]']": 7,
                "button.btn.btn-warning": 5,
            },
            "paths": {
                "/desktop/sale/add": 10,
                "/desktop/sale/index": 3,
            },
        },
    }
    skill = extrapolate_skill_from_platform_map(
        prompt="Create a sales invoice for ACME for 5000 EUR",
        platform_map=platform_map,
        skill_id="envoice.auto.sales_test",
        default_base_url="https://app.envoice.eu",
    )

    assert skill["id"] == "envoice.auto.sales_test"
    assert skill["steps"][0]["action"] == "goto"
    assert skill["steps"][0]["value"].endswith("/desktop/sale/add")
    actions = [s["action"] for s in skill["steps"]]
    assert "select2" in actions
    assert "fill_date" in actions
    assert "fill" in actions
    assert "fill_if_visible" in actions
    assert actions[-2:] == ["check_validation", "screenshot"]
    required = set(skill["slots_schema"]["required"])
    assert {"customer", "invoice_date", "description", "amount"}.issubset(required)


def test_extrapolate_canonicalizes_ambiguous_row_selectors():
    platform_map = {
        "base_urls": ["https://app.envoice.eu"],
        "signals": {
            "selectors": {
                "table > tbody > tr.invoice-row > td:nth-of-type(1) > input[name='sales_invoice__row[0]']": 10,
                "table > tbody > tr.invoice-row > td:nth-of-type(2) > input[name='sales_invoice__row[0]']": 9,
                "input#due_days": 8,
            },
            "paths": {"/desktop/sale/add": 10},
        },
    }
    skill = extrapolate_skill_from_platform_map(
        prompt="Create sales invoice",
        platform_map=platform_map,
        skill_id="envoice.auto.canonical",
        default_base_url="https://app.envoice.eu",
    )
    fills = [s for s in skill["steps"] if s.get("action") == "fill"]
    fills_if_visible = [s for s in skill["steps"] if s.get("action") == "fill_if_visible"]
    selectors = [s.get("selector") for s in fills]
    selectors_if_visible = [s.get("selector") for s in fills_if_visible]
    assert "input#sales_invoice__due_days" in selectors_if_visible
    assert "input[name='sales_invoice__row[0][description]']:visible" in selectors
    assert "input[name='sales_invoice__row[0][item_amount]']:visible" in selectors
    assert "input[name='sales_invoice__row[0][item_qty]']:visible" in selectors_if_visible
