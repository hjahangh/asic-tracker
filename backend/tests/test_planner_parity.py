"""Compare Python availability with frozen outputs from the original JS demo.

All reference cases are synthetic. They include shipment FIFO, historical creation
boundaries, allocation baselines, shortages, overdue supply, and partial receipts.
The fixture was captured only after the legacy regression assertions passed.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.planning import allocation_plan


FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "planner-parity.json").read_text())
KEYS = {"requestAvailability": "requests", "allocationRows": "allocations", "supplyRows": "supply", "supplySummary": "inventory"}


def case_id(case):
    return f"{case['suite']}-{case['index']:03d}-{case['method']}-{case['name']}"


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=case_id)
def test_planner_matches_legacy_javascript(case):
    # Some original engine fixtures intentionally contain only an events array.
    state = {"events": [], "projects": [], "asics": [], **deepcopy(case["state"])}
    before = deepcopy(state)
    options = case["options"]
    result = allocation_plan(state, options["asOf"])[KEYS[case["method"]]]
    if case["method"] in {"supplyRows", "supplySummary"} and options.get("asicId"):
        result = [row for row in result if row["asicId"] == options["asicId"]]
    assert state == before, "The authoritative planner must leave stored records unchanged."
    assert result == case["expected"]


def test_reference_suite_assertions_all_passed_before_capture():
    assert len(FIXTURE["suites"]) == 3
    assert sum(suite["captures"] for suite in FIXTURE["suites"]) == len(FIXTURE["cases"])
    assert {case["method"] for case in FIXTURE["cases"]} == set(KEYS)
    assert all(suite["assertions"] == len(suite["checks"]) and suite["assertions"] > 0 for suite in FIXTURE["suites"])
