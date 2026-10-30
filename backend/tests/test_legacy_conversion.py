from copy import deepcopy
import csv
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "convert_legacy_backup.py"
SPEC = importlib.util.spec_from_file_location("convert_legacy_backup", SCRIPT)
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)


def reviewed_rows(workspace):
    rows = converter.review_template_rows(workspace)
    for row in rows:
        row.update(proposed_project_family_id="family", proposed_project_family_name="Family",
            family_business_entity_id="be", family_funding_source_id="fund", approved_by="Reviewer", approval_date="2026-10-29")
    return rows


def legacy_state(workspace):
    result = deepcopy(workspace)
    result["projectFamilies"] = []
    project = result["projects"][0]
    project.pop("projectFamilyId")
    project.update(businessEntityId="be", entity="Business", fundingSourceId="fund", funding="Funding", phase="Prototype")
    return result


def test_conversion_requires_review_and_never_guesses_families(workspace):
    source = legacy_state(workspace)
    with pytest.raises(ValueError, match="every project"):
        converter.convert_backup(source, [])
    rows = reviewed_rows(source)
    rows[0]["approved_by"] = ""
    with pytest.raises(ValueError, match="approved_by"):
        converter.convert_backup(source, rows)
    rows = reviewed_rows(source)
    rows[0]["proposed_project_family_id"] = ""
    with pytest.raises(ValueError, match="explicit proposed"):
        converter.convert_backup(source, rows)


def test_conversion_preserves_ids_frozen_history_and_baselines_archiving_only_recovery(workspace, event):
    source = legacy_state(workspace)
    source["events"] = [event("r", "request", 9, "2026-11-01", requestId="req-alias"),
        event("a1", "expected_fulfilment", 9, "2026-11-01", requestId="r", priorShipmentIds=["old-shipment"], createdAt="2026-10-01"),
        event("shipment", "actual_ship", 1, "2026-10-29", requestId="r")]
    source["forecastVersions"] = [{"id": "v", "month": "2026-09", "name": "Saved", "createdAt": "2026-09-01", "lines": [
        {"asicId": "deleted", "asicName": "Frozen ASIC", "projectId": "deleted-project", "projectName": "Frozen project", "category": "Frozen entity", "phase": "Frozen phase", "type": "request", "month": "2026-11", "qty": 17}]}]
    source["snapshots"] = [{"id": "legacy", "label": "Before deletion", "date": "2026-09-01", "data": {"projects": [{"id": "deleted-project"}]}}]
    original = deepcopy(source)
    converted, sidecar = converter.convert_backup(source, reviewed_rows(source))
    assert source == original
    assert converted["events"] == source["events"]
    assert converted["forecastVersions"] == source["forecastVersions"]
    assert converted["asics"] == source["asics"]
    assert converted["projects"][0]["id"] == "p"
    assert converted["projects"][0]["projectFamilyId"] == "family"
    assert "prototype" not in converted["projects"][0]
    assert converted["snapshots"] == []
    assert sidecar["snapshots"] == source["snapshots"]


def test_ownership_changes_need_resolution_and_existing_master_ids(workspace):
    source = legacy_state(workspace)
    source["businessEntities"].append({"id": "other", "name": "Other business"})
    rows = reviewed_rows(source)
    rows[0]["family_business_entity_id"] = "other"
    with pytest.raises(ValueError, match="resolution_notes"):
        converter.convert_backup(source, rows)
    rows[0]["resolution_notes"] = "Approved transfer to Other business."
    converted, _ = converter.convert_backup(source, rows)
    assert converted["projects"][0]["entity"] == "Other business"
    rows[0]["family_business_entity_id"] = "missing"
    with pytest.raises(ValueError, match="existing business/funding"):
        converter.convert_backup(source, rows)


def test_csv_rejects_inconsistent_family_ownership_and_stale_project_names(workspace):
    source = legacy_state(workspace)
    second = deepcopy(source["projects"][0])
    second.update(id="p2", name="Second project")
    source["projects"].append(second)
    rows = reviewed_rows(source)
    rows[1]["proposed_project_family_name"] = "Conflicting family label"
    with pytest.raises(ValueError, match="inconsistent name or ownership"):
        converter.convert_backup(source, rows)
    rows = reviewed_rows(source)
    rows[0]["current_project_name"] = "Another backup's project"
    with pytest.raises(ValueError, match="does not match this backup"):
        converter.convert_backup(source, rows)


def test_label_based_legacy_ownership_uses_explicit_approved_family(workspace):
    source = legacy_state(workspace)
    source["projects"][0].pop("businessEntityId")
    source["projects"][0].pop("fundingSourceId")
    converted, _ = converter.convert_backup(source, reviewed_rows(source))
    assert converted["projects"][0]["businessEntityId"] == "be"
    assert converted["projects"][0]["fundingSourceId"] == "fund"


def test_cli_writes_review_template_and_two_json_files_without_overwriting_inputs(tmp_path, workspace):
    source = legacy_state(workspace)
    source_path = tmp_path / "old.json"
    original_text = json.dumps(source)
    source_path.write_text(original_text)
    mapping_path = tmp_path / "family-map.csv"
    assert converter.main([str(source_path), "--template", "--output", str(mapping_path)]) == 0
    with mapping_path.open(newline="") as stream:
        assert csv.DictReader(stream).fieldnames == converter.CSV_COLUMNS
    with mapping_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=converter.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(reviewed_rows(source))
    output_path = tmp_path / "converted.json"
    args = [str(source_path), "--mapping", str(mapping_path), "--output", str(output_path)]
    assert converter.main(args) == 0
    assert output_path.exists()
    assert (tmp_path / "converted.legacy-recovery.json").exists()
    assert json.loads(output_path.read_text())["projects"][0]["projectFamilyId"] == "family"
    with pytest.raises(SystemExit) as rejected:
        converter.main(args)
    assert rejected.value.code == 2
    assert converter.main(args + ["--force"]) == 0
    with pytest.raises(SystemExit):
        converter.main([str(source_path), "--mapping", str(mapping_path), "--output", str(source_path), "--force"])
    assert source_path.read_text() == original_text


def test_prior_template_header_is_compatible():
    path = SCRIPT.parent / "project-family-mapping-template.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        assert next(csv.reader(stream)) == converter.CSV_COLUMNS
