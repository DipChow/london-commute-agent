"""Print current TfL line status."""

import sys

import requests

from commute_agent.tfl_client import get_line_status


def main():
    watched_lines = ["victoria", "central"]

    try:
        lines = get_line_status(watched_lines)
    except (requests.RequestException, ValueError):
        print("Could not retrieve TfL status. Please try again shortly.")
        sys.exit(1)

    for line in lines:
        print(f"\n{line['name']}")

        for status in line.get("lineStatuses", []):
            print(f"  {status['statusSeverityDescription']}")

            reason = status.get("reason")
            if reason:
                print(f"  {reason.strip()}")


if __name__ == "__main__":
    main()