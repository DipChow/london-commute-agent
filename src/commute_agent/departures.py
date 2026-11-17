"""Show live bus arrivals at Dunton Road, stop WN."""

import math
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from commute_agent.tfl_client import get_bus_arrivals

STOP_ID = "490006266WN"


def main():
    try:
        arrivals = get_bus_arrivals(STOP_ID)
    except (requests.RequestException, ValueError):
        print("Could not retrieve bus arrivals. Please try again shortly.")
        sys.exit(1)

    checked_at = datetime.now(ZoneInfo("Europe/London")).strftime("%H:%M:%S")

    print("\nDunton Road — stop WN")
    print(f"Checked at {checked_at}")
    print("Destination for our project: Paddington station\n")

    if not arrivals:
        print("TfL returned no arrival predictions for this stop.")
        return

    arrivals.sort(key=lambda bus: bus["timeToStation"])

    for bus in arrivals[:15]:
        minutes = math.ceil(bus["timeToStation"] / 60)
        wait = "Due" if minutes == 0 else f"{minutes} min"

        print(
            f"{bus['lineName']:>4} | "
            f"{bus['destinationName']} | "
            f"{wait}"
        )


if __name__ == "__main__":
    main()