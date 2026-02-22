from agent.seed_sync import _seed_storage_path


def test_seed_storage_path_sanitizes_slashes():
    assert (
        _seed_storage_path("envoice/sales/invoice")
        == "artifacts/seeds/envoice__sales__invoice.json"
    )
    assert _seed_storage_path("envoice.sales_invoice.existing") == (
        "artifacts/seeds/envoice.sales_invoice.existing.json"
    )
