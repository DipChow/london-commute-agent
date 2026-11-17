"""Find candidate bus connections for Tim's commute."""

import json
import sys
from pathlib import Path

import requests

from commute_agent.tfl_client import (
    get_route_sequence,
    get_stop_details,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = PROJECT_ROOT / "config" / "commuters.local.json"


def main():
    with PROFILE_PATH.open() as file:
        profiles = json.load(file)["commuters"]

    commuter = next(person for person in profiles if person["id"] == "tim")
    origin_id = commuter["origin"]["stop_id"]
    interchange = commuter["interchange_search"].casefold()

    print(f"\n{commuter['name']}")
    print(f"Finding bus connections to {commuter['interchange_search']}...\n")

    try:
        origin = get_stop_details(origin_id)
    except (requests.RequestException, ValueError):
        print("Could not retrieve the origin stop.")
        sys.exit(1)


    bus_ids = {
        line_id
        for group in origin.get("lineModeGroups", [])
        if group.get("modeName") == "bus"
        for line_id in group.get("lineIdentifier", [])
    }

    bus_lines = {
        line["id"]: line.get("name", line["id"])
        for line in origin.get("lines", [])
        if line["id"] in bus_ids
    }

    if not bus_lines:
        print("No bus lines were returned for the origin stop.")
        return

    candidates = set()
    failures = []

    for line_id, line_name in sorted(bus_lines.items()):
        for direction in ["inbound", "outbound"]:
            try:
                route = get_route_sequence(line_id, direction)
            except (requests.RequestException, ValueError):
                failures.append(f"{line_name} ({direction})")
                continue

            for sequence in route.get("stopPointSequences", []):
                stops = sequence.get("stopPoint", [])

                for index, stop in enumerate(stops):
                    if stop.get("id") != origin_id:
                        continue

                    for later_stop in stops[index + 1:]:
                        name = later_stop.get("name", "")

                        if interchange in name.casefold():
                            candidates.add((
                                line_name,
                                direction,
                                name,
                                later_stop["id"],
                            ))

    print("Candidate connections — interchange walks still need checking:\n")

    for line, direction, name, stop_id in sorted(candidates):
        print(f"{line:>4} | {direction} | {name} | {stop_id}")

    if not candidates:
        print("No matching connections found in the returned stop sequences.")

    print(f"\nChecked {len(bus_lines)} bus routes in both directions.")

    if failures:
        print("\nSome lookups failed; results are incomplete:")
        for failure in failures:
            print(f"  {failure}")

    print("\nThese are route connections, not a check of service at your travel time.")


if __name__ == "__main__":
    main()