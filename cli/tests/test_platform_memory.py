from agent import platform_memory as pm


def test_platform_memory_merge_and_persist(monkeypatch, tmp_path):
    monkeypatch.setattr(pm, "STATE_PLATFORM_DIR", tmp_path / "platform_maps")

    platform_id = "envoice"
    data = pm.load_platform_map(platform_id)
    assert data["platform_id"] == platform_id

    events = [
        {
            "type": "click",
            "selector": "button.save",
            "url": "https://app.envoice.eu/desktop/sale/add",
            "ts": 1,
        },
        {
            "type": "input",
            "selector": "input#sales_invoice__invoice_date",
            "value": "22.02.2026",
            "url": "https://app.envoice.eu/desktop/sale/add",
            "ts": 2,
        },
    ]
    merged = pm.merge_platform_signals(
        platform_map=data,
        base_url="https://app.envoice.eu",
        interaction_events=events,
        skill_id="envoice.sales_invoice.existing",
        source="mine",
    )
    saved = pm.save_platform_map(platform_id, merged)
    assert saved.exists()

    reloaded = pm.load_platform_map(platform_id)
    assert reloaded["signals"]["actions"]["click"] == 1
    assert reloaded["signals"]["selectors"]["button.save"] == 1
    assert reloaded["skills"][0]["id"] == "envoice.sales_invoice.existing"
    digest = pm.platform_map_digest(reloaded, top_n=5)
    assert "top_selectors" in digest
    assert "/desktop/sale/add" in digest["top_paths"]
