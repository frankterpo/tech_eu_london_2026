from agent.trace_mining import infer_skill_from_events


def test_infer_skill_from_events_builds_steps_and_slots():
    events = [
        {"type": "page_loaded", "url": "https://app.envoice.eu/desktop/sale/add"},
        {
            "type": "click",
            "selector": "input#sales_invoice__invoice_date",
            "text": "",
            "url": "https://app.envoice.eu/desktop/sale/add",
        },
        {
            "type": "input",
            "selector": "input#sales_invoice__invoice_date",
            "value": "22.02.2026",
            "tag": "input",
            "url": "https://app.envoice.eu/desktop/sale/add",
        },
        {
            "type": "input",
            "selector": "input[name='sales_invoice__row[0][description]']",
            "value": "Consulting",
            "tag": "input",
            "url": "https://app.envoice.eu/desktop/sale/add",
        },
        {
            "type": "click",
            "selector": "button.btn-primary",
            "text": "Save",
            "url": "https://app.envoice.eu/desktop/sale/add",
        },
    ]

    skill = infer_skill_from_events(
        skill_id="envoice.auto.test",
        base_url="https://app.envoice.eu",
        interaction_events=events,
    )
    assert skill["id"] == "envoice.auto.test"
    assert isinstance(skill.get("steps"), list)
    assert skill["steps"][0]["action"] == "goto"
    assert any(step.get("action") == "fill_date" for step in skill["steps"])
    assert any(step.get("action") == "fill" for step in skill["steps"])
    assert skill["slots_schema"]["required"]
