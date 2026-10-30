#!/usr/bin/env python3
"""Convert a browser backup using an explicitly reviewed project-family CSV.

From the repository root, using the backend Python environment:
  python scripts/convert_legacy_backup.py old.json --template --output family-map.csv
  # Fill proposed family/ownership columns, resolution notes, approver and date.
  python scripts/convert_legacy_backup.py old.json --mapping family-map.csv --output converted.json

The CSV is compatible with the earlier Project-Family-Mapping-Template.csv.
Every live project requires a reviewed row; family membership is never inferred.
Changed or unknown prior ownership requires resolution_notes. Prototype values
are preserved, never inferred from engineering phase. Legacy recovery snapshots
are archived unchanged in converted.legacy-recovery.json and removed from the
live import because historical deleted projects may need separate family review.
Both JSON outputs must be retained. Review converted.json before an administrator
imports it through Data & recovery. Input files are never overwritten; --force
permits overwriting existing output files only. This command never accesses a DB.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import io
import json
import os
from pathlib import Path
import sys
import tempfile

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from app.domain import DomainError, valid_id, validate_workspace  # noqa: E402
from app.planning import valid_date  # noqa: E402

CSV_COLUMNS = [
    "current_project_id", "current_project_name", "current_project_key", "current_parent_project_id",
    "current_business_entity_id", "current_business_entity_name", "current_funding_source_id", "current_funding_source_name",
    "proposed_project_family_id", "proposed_project_family_name", "family_business_entity_id", "family_business_entity_name",
    "family_funding_source_id", "family_funding_source_name", "business_funding_conflict", "resolution_notes", "approved_by", "approval_date",
]


def _masters(state: dict, collection: str) -> dict:
    if not isinstance(state, dict):
        raise ValueError("Backup must be a workspace JSON object.")
    rows = state.get(collection)
    if not isinstance(rows, list) or any(not isinstance(row, dict) or not valid_id(row.get("id")) or not isinstance(row.get("name"), str) or not row["name"].strip() for row in rows):
        raise ValueError(f"{collection} must contain records with valid IDs and names.")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError(f"{collection} contains duplicate IDs.")
    return {row["id"]: row for row in rows}


def _prior_ownership(project: dict, state: dict, field: str, collection: str, label: str) -> tuple[str, str]:
    masters = _masters(state, collection)
    identifier = project.get(field, "")
    if identifier:
        if not isinstance(identifier, str):
            raise ValueError(f"Project {project['id']}: {field} must be text.")
        return identifier, str(masters.get(identifier, {}).get("name", project.get(label, "")))
    families = {row["id"]: row for row in state.get("projectFamilies", []) if isinstance(row, dict) and valid_id(row.get("id"))}
    family = families.get(project.get("projectFamilyId"), {}) if isinstance(project.get("projectFamilyId"), str) else {}
    if family.get(field):
        identifier = family[field]
        if not isinstance(identifier, str):
            raise ValueError(f"Project {project['id']}: existing family {field} must be text.")
        return identifier, str(masters.get(identifier, {}).get("name", ""))
    name = project.get(label, "")
    if not isinstance(name, str):
        raise ValueError(f"Project {project['id']}: {label} must be text.")
    matches = [row for row in masters.values() if isinstance(row.get("name"), str) and row["name"].strip().casefold() == name.strip().casefold()]
    # Resolving an existing ownership label does not infer a project family.
    return (matches[0]["id"], matches[0]["name"]) if name.strip() and len(matches) == 1 else ("", name)


def review_template_rows(state: dict) -> list[dict[str, str]]:
    projects = _masters(state, "projects")
    rows = []
    for project in projects.values():
        business_id, business_name = _prior_ownership(project, state, "businessEntityId", "businessEntities", "entity")
        funding_id, funding_name = _prior_ownership(project, state, "fundingSourceId", "fundingSources", "funding")
        row = dict.fromkeys(CSV_COLUMNS, "")
        row.update(current_project_id=project["id"], current_project_name=str(project.get("name", "")),
            current_project_key=str(project.get("key", "")), current_parent_project_id=str(project.get("parentId", "")),
            current_business_entity_id=business_id, current_business_entity_name=business_name,
            current_funding_source_id=funding_id, current_funding_source_name=funding_name)
        rows.append(row)
    return rows


def convert_backup(payload: dict, mapping_rows: list[dict[str, str]]) -> tuple[dict, dict]:
    """Return validated live state and an unchanged legacy recovery sidecar."""
    if not isinstance(payload, dict) or payload.get("version") != 2:
        raise ValueError("Input must be a version 2 workspace JSON backup, not a database dump or API envelope.")
    state = deepcopy(payload)
    projects = _masters(state, "projects")
    business = _masters(state, "businessEntities")
    funding = _masters(state, "fundingSources")
    state.setdefault("projectFamilies", [])
    families = _masters(state, "projectFamilies")
    reviewed = {}
    for index, raw in enumerate(mapping_rows, start=2):
        if not isinstance(raw, dict) or any(value is not None and not isinstance(value, str) for value in raw.values()):
            raise ValueError(f"CSV row {index}: every cell must be text.")
        row = {key: (raw.get(key) or "").strip() for key in CSV_COLUMNS}
        if not any(row.values()):
            continue
        project_id = row["current_project_id"]
        if project_id not in projects:
            raise ValueError(f"CSV row {index}: unknown current_project_id {project_id!r}.")
        if project_id in reviewed:
            raise ValueError(f"CSV row {index}: duplicate mapping for project {project_id}.")
        project = projects[project_id]
        if row["current_project_name"] and row["current_project_name"] != project.get("name"):
            raise ValueError(f"Project {project_id}: current_project_name does not match this backup.")
        if not row["approved_by"] or not valid_date(row["approval_date"]):
            raise ValueError(f"Project {project_id}: approved_by and a valid YYYY-MM-DD approval_date are required.")
        family_id, family_name = row["proposed_project_family_id"], row["proposed_project_family_name"]
        if not valid_id(family_id) or not family_name:
            raise ValueError(f"Project {project_id}: explicit proposed_project_family_id and name are required.")
        target_business, target_funding = row["family_business_entity_id"], row["family_funding_source_id"]
        if target_business not in business or target_funding not in funding:
            raise ValueError(f"Project {project_id}: family ownership IDs must reference existing business/funding masters.")
        for field, expected in (("family_business_entity_name", business[target_business].get("name")), ("family_funding_source_name", funding[target_funding].get("name"))):
            if row[field] and row[field] != expected:
                raise ValueError(f"Project {project_id}: {field} does not match its master ID.")
        old_business, _ = _prior_ownership(project, state, "businessEntityId", "businessEntities", "entity")
        old_funding, _ = _prior_ownership(project, state, "fundingSourceId", "fundingSources", "funding")
        for field, actual in (("current_business_entity_id", old_business), ("current_funding_source_id", old_funding)):
            if row[field] and row[field] != actual:
                raise ValueError(f"Project {project_id}: {field} does not match this backup.")
        if (old_business != target_business or old_funding != target_funding) and not row["resolution_notes"]:
            raise ValueError(f"Project {project_id}: changed or unknown prior ownership requires resolution_notes.")
        existing = families.get(family_id)
        if existing is not None and (existing.get("name") != family_name or existing.get("businessEntityId") != target_business or existing.get("fundingSourceId") != target_funding):
            raise ValueError(f"Project {project_id}: family {family_id} has inconsistent name or ownership across reviewed rows/existing records.")
        if existing is None:
            existing = {"id": family_id, "name": family_name, "businessEntityId": target_business, "fundingSourceId": target_funding, "description": ""}
            families[family_id] = existing
            state["projectFamilies"].append(existing)
        reviewed[project_id] = row
        project.update(projectFamilyId=family_id, businessEntityId=target_business, fundingSourceId=target_funding,
            entity=business[target_business]["name"], funding=funding[target_funding]["name"])
    missing = sorted(set(projects) - set(reviewed))
    if missing:
        raise ValueError("An explicitly reviewed family mapping is required for every project. Missing: " + ", ".join(missing[:20]))
    legacy_snapshots = state.get("snapshots", [])
    if not isinstance(legacy_snapshots, list):
        raise ValueError("Legacy snapshots must be an array.")
    sidecar = {"format": "asic-tracker-legacy-recovery", "version": 1, "snapshots": deepcopy(legacy_snapshots)}
    state["snapshots"] = []
    # This conversion changes no forecast IDs/labels, event dates, request links,
    # shipment baselines, part IDs, or prototype flags. Domain validation derives
    # only the explicitly approved family ownership compatibility fields.
    return validate_workspace(state), sidecar


def _write_files(contents: dict[Path, str], *, protected: set[Path], force: bool) -> None:
    resolved = [path.resolve() for path in contents]
    if len(set(resolved)) != len(resolved) or set(resolved) & {path.resolve() for path in protected}:
        raise ValueError("Output paths must be distinct and must never overwrite an input or mapping file.")
    for path in contents:
        if path.exists() and not force:
            raise ValueError(f"Output already exists: {path}. Choose another path or use --force.")
        if not path.parent.is_dir():
            raise ValueError(f"Output directory does not exist: {path.parent}")
    temporary = []
    try:
        for path, content in contents.items():
            descriptor, name = tempfile.mkstemp(prefix=".asic-conversion-", dir=path.parent)
            temporary.append((Path(name), path))
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for temporary_path, output_path in temporary:
            if force:
                os.replace(temporary_path, output_path)
            else:
                # The final creation is also exclusive, so another process
                # cannot appear after the existence check and be overwritten.
                os.link(temporary_path, output_path)
    finally:
        for path, _ in temporary:
            path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Original version 2 JSON backup")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mapping", type=Path, help="Completed, explicitly approved family mapping CSV")
    mode.add_argument("--template", action="store_true", help="Write a populated review CSV without converting")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true", help="Replace existing output files, never inputs")
    args = parser.parse_args(argv)
    try:
        if args.input.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Backup exceeds the 32 MiB conversion limit.")
        payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
        if args.template:
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(review_template_rows(payload))
            _write_files({args.output: stream.getvalue()}, protected={args.input}, force=args.force)
            print(f"Review template written: {args.output}")
        else:
            with args.mapping.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if not reader.fieldnames or any(column not in reader.fieldnames for column in CSV_COLUMNS):
                    raise ValueError("Mapping CSV must use the provided 18-column project-family review template.")
                rows = list(reader)
            converted, sidecar = convert_backup(payload, rows)
            sidecar_path = args.output.with_name(args.output.stem + ".legacy-recovery.json")
            contents = {args.output: json.dumps(converted, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                sidecar_path: json.dumps(sidecar, ensure_ascii=False, allow_nan=False, indent=2) + "\n"}
            _write_files(contents, protected={args.input, args.mapping}, force=args.force)
            print(f"Validated import written: {args.output}")
            print(f"Legacy recovery archive written: {sidecar_path} ({len(sidecar['snapshots'])} snapshots)")
    except (ValueError, OSError, DomainError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
