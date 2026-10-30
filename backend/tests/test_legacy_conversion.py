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


@pytest.mark.parametrize("keep_existing_family", [False, True])
def test_template_can_convert_valid_whitespace_padded_live_names(workspace, keep_existing_family):
    source = deepcopy(workspace) if keep_existing_family else legacy_state(workspace)
    source["projects"][0]["name"] = " Project "
    source["businessEntities"][0]["name"] = " Business "
    source["fundingSources"][0]["name"] = " Funding "
    if keep_existing_family:
        source["projectFamilies"][0]["name"] = " Family "
    rows = reviewed_rows(source)
    rows[0].update(family_business_entity_name=" Business ", family_funding_source_name=" Funding ")
    converted, _ = converter.convert_backup(source, rows)
    assert converted["projects"][0]["name"] == "Project"
    assert converted["businessEntities"][0]["name"] == "Business"
    assert converted["fundingSources"][0]["name"] == "Funding"
    assert converted["projectFamilies"][0]["name"] == "Family"


def test_template_rejects_malformed_family_collection_without_a_type_error(workspace):
    source = deepcopy(workspace)
    source["projectFamilies"] = None
    with pytest.raises(ValueError, match="projectFamilies must be an array"):
        converter.review_template_rows(source)


@pytest.mark.parametrize("project_name", ['=HYPERLINK("https://example.invalid","demo")', "+Project", "-Project", "@Project", " \t=Project", "'=Intentional apostrophe"])
def test_cli_formula_safe_template_roundtrips_original_names_keys_and_ids(tmp_path, workspace, project_name):
    source = legacy_state(workspace)
    source["projects"][0].update(id="-2-1", name=project_name, key="+1-1", businessEntityId="-business", fundingSourceId="-funding")
    source["businessEntities"][0].update(id="-business", name="@Business")
    source["fundingSources"][0].update(id="-funding", name="-Funding")
    input_path, mapping_path, output_path = (tmp_path / name for name in ("original.json", "mapping.csv", "converted.json"))
    input_path.write_text(json.dumps(source))
    assert converter.main([str(input_path), "--template", "--output", str(mapping_path)]) == 0
    with mapping_path.open(newline="") as stream:
        row = next(csv.DictReader(stream))
    for field in ("current_project_id", "current_project_key", "current_business_entity_id", "current_business_entity_name", "current_funding_source_id", "current_funding_source_name"):
        assert row[field].startswith("'")
        assert not row[field].lstrip().startswith(("=", "+", "-", "@"))
    assert row["current_project_name"] == (project_name if project_name.startswith("'") else "'" + project_name)
    row.update(proposed_project_family_id="family", proposed_project_family_name="Family",
        family_business_entity_id=row["current_business_entity_id"], family_business_entity_name=row["current_business_entity_name"],
        family_funding_source_id=row["current_funding_source_id"], family_funding_source_name=row["current_funding_source_name"],
        approved_by="Reviewer", approval_date="2026-10-29")
    with mapping_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=converter.CSV_COLUMNS)
        writer.writeheader()
        writer.writerow(row)
    assert converter.main([str(input_path), "--mapping", str(mapping_path), "--output", str(output_path)]) == 0
    converted = json.loads(output_path.read_text())
    assert converted["projects"][0]["id"] == "-2-1"
    assert converted["projects"][0]["name"] == project_name.strip()
    assert converted["projects"][0]["key"] == "+1-1"
    assert converted["projects"][0]["businessEntityId"] == "-business"
    assert converted["businessEntities"][0]["name"] == "@Business"
    assert converted["fundingSources"][0]["name"] == "-Funding"


@pytest.mark.parametrize("original_name", ["=Existing family", "'=Intentional family"])
def test_escaped_existing_family_label_does_not_add_or_remove_intentional_apostrophe(workspace, original_name):
    source = deepcopy(workspace)
    source["projectFamilies"][0]["name"] = original_name
    rows = reviewed_rows(source)
    rows[0]["proposed_project_family_name"] = converter._csv_literal(original_name)
    converted, _ = converter.convert_backup(source, rows)
    assert converted["projectFamilies"][0]["name"] == original_name
