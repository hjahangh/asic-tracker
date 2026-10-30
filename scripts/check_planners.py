#!/usr/bin/env python3
"""Check planner conservation and browser/Python agreement using synthetic data.

Run from the repository root with its Python runtime dependencies installed:
    python scripts/check_planners.py
Use --node /path/to/node or NODE_BINARY when Node.js 22+ is not on PATH.
No browser, database, user records, or generated repository files are used.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, timedelta
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONSERVATION_SEED, PARITY_SEED = 20261029, 20261030
CONSERVATION_CASES, PARITY_CASES = 3000, 400
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "backend"))


class CheckFailed(Exception):
    def __init__(self, stage, message, *, seed=None, case=None, state=None):
        self.report = {"passed": False, "stage": stage, "message": message}
        if seed is not None:
            self.report.update(seed=seed, case=case, input=state)
        super().__init__(message)


def conservation_checks(allocation_plan):
    rng, as_of = random.Random(CONSERVATION_SEED), "2026-10-29"
    for index in range(CONSERVATION_CASES):
        state = {"asics": [{"id": "a"}, {"id": "b"}], "projects": [{"id": "p"}, {"id": "q"}], "events": []}
        events = state["events"]
        for number in range(rng.randint(1, 30)):
            kind = rng.choice(["request", "expected_ship", "expected_fulfilment", "actual_ship", "actual_fulfilment"])
            day = (date(2026, 10, 29) + timedelta(days=rng.randint(-8, 8))).isoformat()
            event = {"id": f"e{number}", "type": kind, "asicId": rng.choice(["a", "b"]),
                     "projectId": "" if kind == "expected_ship" else rng.choice(["p", "q"]),
                     "qty": rng.randint(1, 100), "date": day,
                     "createdAt": f"2026-10-{rng.randint(1, 29):02d}T12:00:00Z"}
            if kind == "expected_ship":
                event["supplyStatus"] = rng.choice(["available", "incoming"])
            if kind == "request":
                event.update(shipDays=0, requestedShipDate=day, requestId=rng.choice(["shared", f"e{number}", ""]))
            if kind == "expected_fulfilment":
                event["availableShipDate"] = day
            if kind in ("actual_ship", "expected_fulfilment"):
                event["requestId"] = rng.choice(["", "shared"] + [row["id"] for row in events if row["type"] == "request"])
            events.append(event)
        before = deepcopy(state)

        def check(condition, message):
            if not condition:
                raise CheckFailed("conservation", message, seed=CONSERVATION_SEED, case=index, state=before)

        try:
            result = allocation_plan(state, as_of)
            check(state == before, "Planner mutated its input.")
            for row in result["requests"]:
                check(row["qty"] == row["shippedQty"] + row["remainingQty"], "Request shipment quantities do not conserve demand.")
                check(0 <= row["allocatedAvailableByShipBy"] <= row["allocatedQty"] <= row["remainingQty"], "Request allocation quantities are inconsistent.")
                check(0 <= row["availableByShipBy"] <= row["remainingQty"], "Request coverage exceeds remaining demand.")
                check(row["shortfallQty"] == row["remainingQty"] - row["availableByShipBy"], "Request shortage is inconsistent.")
            for row in result["allocations"]:
                check(row["qty"] == row["remainingQty"] + row["shippedQty"], "Allocation shipment quantities do not conserve commitments.")
                check(row["remainingQty"] == row["reservedSupplyQty"] + row["unbackedQty"], "Allocation backing quantities are inconsistent.")
            for row in result["inventory"]:
                check(0 <= row["reservedQty"] <= row["onHandQty"], "Reservations exceed on-hand inventory.")
                check(row["freeQty"] == row["onHandQty"] - row["reservedQty"], "Free inventory is inconsistent.")
                check(row["onHandQty"] == max(0, row["receivedQty"] - row["shippedQty"]), "On-hand inventory does not account for shipments once.")
                for collection in ("requests", "allocations"):
                    credited = sum(item["shippedQty"] for item in result[collection] if item["asicId"] == row["asicId"])
                    check(credited <= row["shippedQty"], f"{collection} reuse completed shipment units.")
                usable = sum(event["qty"] for event in events if event["type"] == "expected_ship"
                             and event["asicId"] == row["asicId"]
                             and not (event.get("supplyStatus") == "incoming" and event["date"] < as_of))
                covered = sum(item["availableByShipBy"] for item in result["requests"] if item["asicId"] == row["asicId"])
                check(covered <= max(0, usable - row["shippedQty"]), "Request coverage reuses physical supply.")
        except CheckFailed:
            raise
        except Exception as error:
            raise CheckFailed("conservation", str(error), seed=CONSERVATION_SEED, case=index, state=before) from error


def parity_cases():
    rng, cases = random.Random(PARITY_SEED), []
    for index in range(PARITY_CASES):
        state = {"asics": [{"id": "a"}, {"id": "b"}],
                 "projects": [{"id": "p", "leadDays": 0}, {"id": "q", "leadDays": 2}], "events": []}
        for number in range(rng.randint(2, 28)):
            kind = rng.choice(["request", "expected_ship", "expected_fulfilment", "actual_ship", "actual_fulfilment"])
            day = (date(2026, 10, 29) + timedelta(days=rng.randint(-3, 6))).isoformat()
            event = {"id": rng.choice(["a", "B", "c_", "D-"]) + str(number), "type": kind,
                     "asicId": rng.choice(["a", "b"]), "projectId": "" if kind == "expected_ship" else rng.choice(["p", "q"]),
                     "date": day, "qty": rng.randint(1, 100)}
            created = rng.choice([None, "2026-10-28", "2026-10-29", "2026-10-29T02:00:00Z",
                                  "2026-10-29T11:00:00-07:00", "2026-10-29T12:00:00Z", "2026-10-29T12:00:00.0009Z"])
            if created is not None:
                event["createdAt"] = created
            if kind == "request":
                event.update(shipDays=rng.randint(0, 2), requestId=rng.choice(["shared", "a", "B", ""]))
            if kind == "expected_ship" and rng.choice([False, True]):
                event["supplyStatus"] = rng.choice(["incoming", "available"])
            if kind == "expected_fulfilment" and rng.choice([False, True]):
                event["availableShipDate"] = day
            state["events"].append(event)
        request_ids = [event["id"] for event in state["events"] if event["type"] == "request"]
        shipment_ids = [event["id"] for event in state["events"] if event["type"] == "actual_ship"]
        for event in state["events"]:
            if event["type"] == "request" and request_ids and rng.random() < .2:
                event["requestId"] = rng.choice(request_ids)
            if event["type"] in ("actual_ship", "expected_fulfilment"):
                event["requestId"] = rng.choice(["", "shared", "a", "B", *request_ids])
            if event["type"] == "expected_fulfilment" and shipment_ids and rng.random() < .3:
                event["priorShipmentIds"] = [rng.choice(shipment_ids)]
        cases.append({"index": index, "state": state, "asOf": rng.choice(["2026-10-29", "2026-10-30"])})
    return cases


NODE_CHECK = r"""
const fs=require('node:fs'),vm=require('node:vm');
const cases=JSON.parse(fs.readFileSync(0,'utf8')),sandbox={window:{},Intl,Date,console};
const results=[];let failure=null;
try {
  vm.createContext(sandbox);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
  const tracker=sandbox.window.Tracker;
  for(const test of cases) {
    try {
      const before=JSON.stringify(test.state),options={asOf:test.asOf};
      const result={requests:tracker.requestAvailability(test.state,options),
        allocations:tracker.allocationRows(test.state,options),
        supply:tracker.supplyRows(test.state,options),inventory:tracker.supplySummary(test.state,options)};
      if(before!==JSON.stringify(test.state))throw new Error('Client mutated its input.');
      results.push(result);
    } catch(error) {failure={case:test.index,message:String(error.message||error)};break;}
  }
} catch(error) {failure={case:null,message:String(error.message||error)};}
process.stdout.write(JSON.stringify(failure?{failure}:{results}));
if(failure)process.exitCode=1;
"""


def parity_checks(allocation_plan, node):
    cases = parity_cases()
    try:
        result = subprocess.run([node, "-e", NODE_CHECK, str(ROOT / "frontend/data.js")],
                                input=json.dumps(cases), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        raise CheckFailed("parity", str(error), seed=PARITY_SEED) from error
    try:
        payload = json.loads(result.stdout)
    except ValueError as error:
        raise CheckFailed("parity", "Node did not return JSON: " + result.stderr[-2000:], seed=PARITY_SEED) from error
    if result.returncode or payload.get("failure"):
        failure = payload.get("failure", {})
        index = failure.get("case")
        state = cases[index] if type(index) is int and 0 <= index < len(cases) else None
        raise CheckFailed("parity", failure.get("message", result.stderr[-2000:]), seed=PARITY_SEED, case=index, state=state)
    client = payload.get("results", [])
    if len(client) != len(cases):
        raise CheckFailed("parity", "Client returned an unexpected number of cases.", seed=PARITY_SEED)
    for index, case in enumerate(cases):
        before = deepcopy(case["state"])
        try:
            server = allocation_plan(case["state"], case["asOf"])
        except Exception as error:
            raise CheckFailed("parity", str(error), seed=PARITY_SEED, case=index, state=case) from error
        if case["state"] != before:
            raise CheckFailed("parity", "Python planner mutated its input.", seed=PARITY_SEED, case=index, state=case)
        if server != client[index]:
            models = [key for key in ("requests", "allocations", "supply", "inventory") if server[key] != client[index][key]]
            raise CheckFailed("parity", "Client/Python mismatch in: " + ", ".join(models), seed=PARITY_SEED, case=index, state=case)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--node", default=os.environ.get("NODE_BINARY") or shutil.which("node"),
                        help="Node.js executable (default: NODE_BINARY, then node on PATH)")
    args = parser.parse_args()
    if not args.node:
        parser.error("Node.js 22+ is required. Install it, pass --node /path/to/node, or set NODE_BINARY.")
    try:
        version = subprocess.run([args.node, "--version"], capture_output=True, text=True, check=True, timeout=15).stdout.strip()
        match = re.fullmatch(r"v(\d+)\.\d+\.\d+.*", version)
        if not match or int(match.group(1)) < 22:
            raise CheckFailed("setup", "Node.js 22+ is required; found " + version)
        from app.planning import allocation_plan
        conservation_checks(allocation_plan)
        parity_checks(allocation_plan, args.node)
        print(json.dumps({"passed": True, "node_version": version,
                          "conservation": {"cases": CONSERVATION_CASES, "seed": CONSERVATION_SEED},
                          "parity": {"cases": PARITY_CASES, "read_models_per_case": 4,
                                     "exact_comparisons": PARITY_CASES * 4, "seed": PARITY_SEED}}))
        return 0
    except CheckFailed as error:
        print(json.dumps(error.report))
    except (ImportError, OSError, KeyError, subprocess.SubprocessError) as error:
        print(json.dumps({"passed": False, "stage": "setup", "message": str(error)}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
