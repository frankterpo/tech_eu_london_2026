from agent.skill_spec_utils import normalize_skill_spec


def test_normalize_skill_spec_flattens_params_and_aliases():
    skill = {
        "steps": [
            {"action": "goto", "args": {"url": "https://app.envoice.eu"}},
            {
                "action": "wait_for_selector",
                "params": {"selector": "#save-btn", "timeout": "2500"},
            },
            {
                "action": "wait_for_url",
                "args": {"url": "https://app.envoice.eu/desktop/user/login"},
            },
            {"action": "open_url", "params": {"url": "https://app.envoice.eu/dashboard"}},
            {
                "action": "foreach",
                "params": {
                    "items": "{{rows}}",
                    "skill": "envoice.sales_invoice.existing",
                    "optional": True,
                    "skip_if_exists": False,
                },
            },
        ]
    }
    normalized = normalize_skill_spec(
        skill,
        default_id="envoice.auto.test",
        default_base_url="https://app.envoice.eu",
    )

    assert normalized["id"] == "envoice.auto.test"
    assert normalized["base_url"] == "https://app.envoice.eu"

    first = normalized["steps"][0]
    assert first["action"] == "goto"
    assert first["value"] == "https://app.envoice.eu"

    second = normalized["steps"][1]
    assert second["action"] == "wait"
    assert second["selector"] == "#save-btn"
    assert second["timeout"] == 2500

    third = normalized["steps"][2]
    assert third["action"] == "wait_for_url"
    assert third["value"] == "https://app.envoice.eu/desktop/user/login"

    fourth = normalized["steps"][3]
    assert fourth["action"] == "goto"
    assert fourth["value"] == "https://app.envoice.eu/dashboard"

    fifth = normalized["steps"][4]
    assert fifth["action"] == "foreach"
    assert fifth["items"] == "{{rows}}"
    assert fifth["skill"] == "envoice.sales_invoice.existing"
    assert fifth["optional"] is True
    assert fifth["skip_if_exists"] is False


def test_normalize_skill_spec_builds_slots_schema_from_arguments():
    skill = {
        "arguments": [
            {"name": "customer", "type": "string", "description": "Customer name"},
            {"name": "amount", "type": "number", "required": False},
            {"name": "priority", "type": "unsupported"},
        ],
        "steps": [{"action": "screenshot"}],
    }
    normalized = normalize_skill_spec(
        skill,
        default_id="envoice.auto.args",
        default_base_url="https://app.envoice.eu",
    )

    schema = normalized["slots_schema"]
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"customer", "priority"}
    assert schema["properties"]["customer"]["type"] == "string"
    assert schema["properties"]["amount"]["type"] == "number"
    assert schema["properties"]["priority"]["type"] == "string"
