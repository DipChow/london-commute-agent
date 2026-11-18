"""Format commute messages and save them for the dashboard."""

from datetime import datetime

from commute_agent import storage


def format_commute_message(summary, journeys, travel_date):
    """Build a friendly message using TfL's source timings."""
    day = datetime.fromisoformat(travel_date).strftime("%A %d %B")

    lines = [
        f"Good morning! Here are your suggested commutes for {day}.",
        summary,
    ]

    if journeys:
        lines.extend(
            [
                "",
                "Based on current schedules, "
                "your suggested routes to work are:",
            ]
        )

    for number, journey in enumerate(journeys, start=1):
        departure = datetime.fromisoformat(journey["leave_home"])
        arrival = datetime.fromisoformat(journey["reach_destination"])

        transport_steps = [
            leg["instruction"]
            for leg in journey["legs"]
            if leg["mode"] != "walking"
        ]

        lines.extend(
            [
                "",
                (
                    f"{number}. Leave home {departure:%H:%M} "
                    f"→ arrive {arrival:%H:%M} "
                    f"({journey['duration_minutes']} min, including walking)"
                ),
                "   " + " → ".join(transport_steps),
            ]
        )

    return "\n".join(lines)


def save_commute_message(result):
    """Save the latest message and append it to the person's history."""
    commuter_id = result["commuter_id"]

    storage.write(
        "agent_message",
        result,
        commuter_id=commuter_id,
    )

    storage.event(
        result["generated_at"],
        {
            "type": "commute_message",
            "result": result,
        },
        commuter_id=commuter_id,
    )