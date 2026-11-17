"""Display TfL journeys from Dunton Road WN to Paddington."""

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import json

from commute_agent.tfl_client import plan_journey

ORIGIN_ID = "490006266WN" 
DESTINATION_ID = "1000174"  # Paddington Underground station


def main():
    print("\nDunton Road WN → Paddington Underground")
    print("Finding journeys departing now...\n")

    try:
        result = plan_journey(ORIGIN_ID, DESTINATION_ID)
    except (requests.RequestException, ValueError):
        print("Could not retrieve journeys. Please try again shortly.")
        sys.exit(1)

    journeys = result.get("journeys", [])


    if not journeys:
        print("TfL needs us to clarify the journey locations.")

        for key in [
            "fromLocationDisambiguation",
            "toLocationDisambiguation",
        ]:
            print(f"\n{key}:")
            print(json.dumps(result.get(key), indent=2))

        return    

    checked_at = datetime.now(
        ZoneInfo("Europe/London")
    ).strftime("%H:%M:%S")
    print(f"Checked at {checked_at}")

    for number, journey in enumerate(journeys[:3], start=1):
        print(f"\nOption {number}: {journey['duration']} minutes")
        departure = datetime.fromisoformat(
                journey["startDateTime"]
        ).strftime("%H:%M")

        arrival = datetime.fromisoformat(
                journey["arrivalDateTime"]
        ).strftime("%H:%M")

        print(f"  Depart: {departure} | Arrive: {arrival}")

        for leg in journey.get("legs", []):
            mode = leg.get("mode", {}).get("name", "Unknown")
            instruction = leg.get("instruction", {}).get(
                "summary", "No instruction provided"
            )
            duration = leg.get("duration", "?")

            print(f"  {mode}: {instruction} ({duration} min)")


if __name__ == "__main__":
    main()