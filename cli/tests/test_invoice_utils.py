from agent.invoice_utils import parse_invoice_prompt
from agent.scheduler import cron_for_frequency


def test_parse_invoice_prompt_extracts_core_fields():
    prompt = "Create a monthly sales invoice of €1200 with reverse charge VAT IE6388047V."
    slots = parse_invoice_prompt(prompt)

    assert slots["amount"] == 1200.0
    assert slots["currency"] == "EUR"
    assert slots["period"] == "monthly"
    assert slots["tax_rule"] == "reverse_charge"
    assert slots["vat_id"] == "IE6388047V"


def test_cron_frequency_mappings():
    assert cron_for_frequency("weekly") == "0 9 * * 1"
    assert cron_for_frequency("monthly") == "0 9 1 * *"
    assert cron_for_frequency("quarterly") == "0 9 1 */3 *"
    assert cron_for_frequency("annual") == "0 9 1 1 *"


def test_parse_invoice_prompt_avoids_false_vat_match():
    prompt = "Create a quarterly invoice for ACME with reduced tax."
    slots = parse_invoice_prompt(prompt)
    assert "vat_id" not in slots
