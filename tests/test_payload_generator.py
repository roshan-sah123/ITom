"""Snapshot/export helper tests call the production payload generator."""
import json
import pytest
from src.sync.payload_generator import PayloadGenerator, calculate_metrics, normalize_manufacturer


@pytest.mark.parametrize("raw,expected", [("DELL INC.", "Dell"), ("LENOVO", "Lenovo"), (None, "Other")])
def test_manufacturer_normalization(raw, expected):
    assert normalize_manufacturer(raw) == expected


def devices():
    return [
        {"id":"one", "deviceName":"ONE", "manufacturer":"DELL INC.", "operatingSystem":"Windows", "complianceState":"compliant", "totalStorageSpaceInBytes":100, "freeStorageSpaceInBytes":20},
        {"id":"two", "deviceName":"TWO", "manufacturer":"LENOVO", "operatingSystem":"Windows", "complianceState":"noncompliant", "totalStorageSpaceInBytes":300, "freeStorageSpaceInBytes":240},
    ]


def test_storage_is_weighted_by_capacity_and_compliance_reconciles():
    metrics = calculate_metrics(devices())
    assert metrics["total_managed_devices"] == 2
    assert metrics["compliance_rate_pct"] == 50
    assert metrics["avg_storage_used_pct"] == 35
    assert metrics["compliant_devices"] + metrics["noncompliant_devices"] + metrics["other_compliance"] == 2


def test_generator_roundtrip_and_sample_limit(tmp_path):
    source, target = tmp_path / "raw.json", tmp_path / "summary.json"
    source.write_text(json.dumps({"devices": devices()}), encoding="utf-8")
    generator = PayloadGenerator()
    payload = generator.generate(input_file=str(source), output_file=str(target), sample_size=1)
    assert json.loads(target.read_text(encoding="utf-8")) == payload
    assert len(payload["sample_devices"]) == 1
    assert sum(payload["manufacturer_breakdown"].values()) == 2
    assert generator.validate_payload(payload)


def test_empty_file_cannot_generate_plausible_fleet(tmp_path):
    source, target = tmp_path / "empty.json", tmp_path / "summary.json"
    source.write_text('{"devices": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="0 devices"):
        PayloadGenerator().generate(input_file=str(source), output_file=str(target))
    assert not target.exists()
