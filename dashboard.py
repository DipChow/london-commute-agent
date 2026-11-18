"""Local Streamlit dashboard. Run from the project root."""

from copy import deepcopy
from datetime import datetime, time
from zoneinfo import ZoneInfo

import streamlit as st
from openai import OpenAIError

from commute_agent import storage
from commute_agent.agent import run_agent
from commute_agent.commute import (
    DAYS,
    baseline,
    check,
    get_plan,
    local_time,
    profile_key,
    travel_date,
)


st.set_page_config(
    page_title="London Commutes",
    page_icon="🚇",
    layout="wide",
)

st.title("London Commutes")
st.caption(
    "Morning journeys · London time · "
    "Transport for London journey and service information"
)


def now_for(profile):
    return datetime.now(ZoneInfo(profile["timezone"]))


def show_journeys(plan, profile):
    zone = ZoneInfo(profile["timezone"])

    for number, journey in enumerate(plan.get("journeys", []), 1):
        departure = local_time(journey["startDateTime"], zone)
        arrival = local_time(journey["arrivalDateTime"], zone)

        label = (
            f"Option {number} · leave {departure:%H:%M} "
            f"→ arrive {arrival:%H:%M} · {journey['duration']} min"
        )

        with st.expander(label, expanded=number == 1):
            for leg in journey.get("legs", []):
                mode = leg.get("mode", {}).get("name", "")
                instruction = leg.get("instruction", {}).get("summary", "")
                duration = leg.get("duration", "?")
                st.write(f"{mode} · {instruction} · {duration} min")

            legs = journey.get("legs", [])
            if legs:
                st.write(
                    "TfL resolved starting point:",
                    legs[0].get("departurePoint", {}),
                )
                st.write(
                    "TfL resolved destination:",
                    legs[-1].get("arrivalPoint", {}),
                )

    if plan.get("diagnostics"):
        with st.expander("Location matches / unsuccessful samples"):
            st.json(plan["diagnostics"])


try:
    profiles = storage.load_profiles()
    if not profiles:
        raise ValueError("No commuter profiles found.")
except (OSError, ValueError, KeyError):
    st.error(
        "Unable to load commuter profiles. Check "
        "config/commuters.local.json and run from the project folder."
    )
    st.stop()

profiles_by_id = {profile["id"]: profile for profile in profiles}

with st.sidebar:
    commuter_id = st.selectbox(
        "Commuter",
        options=list(profiles_by_id),
        format_func=lambda value: profiles_by_id[value]["name"],
        key="selected_commuter",
    )

p = storage.load_profile(commuter_id)

notice = st.session_state.pop("settings_notice", None)
if notice:
    st.success(notice)

with st.sidebar:
    st.header("Commute settings")

    # Separate widget keys prevent one person's form values
    # appearing in another person's settings.
    prefix = f"settings_{commuter_id}"

    with st.form(prefix):
        name = st.text_input(
            "Name",
            value=p["name"],
            key=f"{prefix}_name",
        )
        origin = st.text_input(
            "Home address",
            value=p["origin"]["address"],
            key=f"{prefix}_origin",
        )
        destination = st.text_input(
            "Destination address",
            value=p["destination"]["address"],
            key=f"{prefix}_destination",
        )
        start = st.time_input(
            "Arrive from",
            value=time.fromisoformat(p["time_window"]["start"]),
            key=f"{prefix}_start",
        )
        end = st.time_input(
            "Arrive by",
            value=time.fromisoformat(p["time_window"]["end"]),
            key=f"{prefix}_end",
        )
        days = st.multiselect(
            "Travel days",
            options=DAYS,
            default=p["travel_days"],
            key=f"{prefix}_days",
        )
        warning = st.number_input(
            "Check minutes before leaving home",
            min_value=0,
            max_value=180,
            value=int(p["advance_warning_minutes"]),
            key=f"{prefix}_warning",
        )

        enabled = st.checkbox(
            "Enable automatic monitoring and morning messages",
            value=p.get("enabled", False),
            key=f"{prefix}_enabled",
        )

        save_settings = st.form_submit_button("Save settings")

    if save_settings:
        if (
            not name.strip()
            or not origin.strip()
            or not destination.strip()
            or not days
            or end <= start
        ):
            st.error(
                "Enter a name, both addresses, at least one travel day "
                "and an end time after the start."
            )
        else:
            updated = deepcopy(p)
            origin_changed = origin.strip() != p["origin"]["address"]
            destination_changed = (
                destination.strip() != p["destination"]["address"]
            )

            updated["name"] = name.strip()
            updated["enabled"] = enabled
            updated["origin"]["address"] = origin.strip()
            updated["destination"]["address"] = destination.strip()
            updated["time_window"] = {
                "type": "arrival",
                "start": start.strftime("%H:%M"),
                "end": end.strftime("%H:%M"),
            }
            updated["travel_days"] = days
            updated["advance_warning_minutes"] = int(warning)

            # Coordinates resolved for an old address must not be reused.
            for section, changed in (
                ("origin", origin_changed),
                ("destination", destination_changed),
            ):
                if changed:
                    for field in (
                        "journey_location",
                        "resolved_address",
                        "resolved_name",
                    ):
                        updated[section].pop(field, None)

            if origin_changed:
                updated["origin"]["stop_id"] = None

            if origin_changed or destination_changed:
                updated["interchange_search"] = None
                updated["rail_line_ids"] = []

            storage.save_profile(updated)
            routes_changed = profile_key(updated) != profile_key(p)
            st.session_state["settings_notice"] = (
                f"Settings saved for {updated['name']}."
                + (
                    " Preview and save a fresh baseline."
                    if routes_changed
                    else ""
                )
            )
            st.rerun()

    st.info(
        "Automatic messages require the background worker running "
        "with --generate. External delivery is not connected."
    )

st.subheader(f"{p['name']}'s commute")
st.write(f"**{p['origin']['address']} → {p['destination']['address']}**")

a, b, c = st.columns(3)
a.metric(
    "Arrival window",
    f"{p['time_window']['start']}–{p['time_window']['end']}",
)
b.metric("Advance warning", f"{p['advance_warning_minutes']} min")
c.metric("Commuters", len(profiles))
st.caption("Travel days: " + ", ".join(day.title() for day in p["travel_days"]))

left, right = st.columns(2)

with left:
    if st.button("Preview morning journeys", type="primary"):
        with st.spinner("Checking journeys across the arrival window…"):
            try:
                current = now_for(p)
                preview = get_plan(p, travel_date(p, current))
                storage.write("preview", preview, commuter_id=commuter_id)
            except Exception:
                st.error(
                    "Unable to retrieve journeys. Check the addresses "
                    "and retry. Your saved baseline was not changed."
                )

with right:
    if st.button("Fetch and save route baseline"):
        with st.spinner("Fetching journeys and saving this commuter's baseline…"):
            try:
                baseline(p, now_for(p))
                storage.write("daily_plan", {}, commuter_id=commuter_id)
                st.success(f"Baseline saved for {p['name']}.")
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error("TfL lookup failed. Retry shortly.")

base = storage.read("baseline", {}, commuter_id=commuter_id)
baseline_valid = bool(base and base.get("key") == profile_key(p))

if base and not baseline_valid:
    st.warning("Settings changed. Save a fresh baseline for this commuter.")
elif not base:
    st.info("Preview the journeys, inspect the address matches, then save a baseline.")

preview = storage.read("preview", {}, commuter_id=commuter_id)
if preview.get("key") != profile_key(p):
    preview = {}

plan = preview or (base if baseline_valid else {})

if plan:
    st.subheader(f"Journey options · {plan['date']}")
    st.caption(
        "Sampled across the arrival window. Only arrivals inside the "
        "window are shown; this is not an exhaustive timetable."
    )
    if plan.get("check_from"):
        monitoring_start = local_time(
            plan["check_from"],
            ZoneInfo(p["timezone"]),
        )
        st.write(
            "Proposed monitoring start:",
            monitoring_start.strftime("%A %d %B, %H:%M"),
        )

    show_journeys(plan, p)
    st.caption(
        "Inspect the resolved starting point and destination before "
        "using these journeys. Address matching may resolve to a street "
        "rather than a particular entrance."
    )

st.subheader("Service monitor")

if st.button(
    "Check reported service status now",
    disabled=not baseline_valid,
):
    with st.spinner("Checking this commuter's transport lines…"):
        try:
            check(p, now_for(p), manual=True)
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error("Unable to check TfL right now.")


@st.fragment(run_every=30)
def monitor_panel(selected_id):
    profile = storage.load_profile(selected_id)
    current = now_for(profile)

    worker = storage.read("worker", {}, commuter_id=selected_id)

    if worker:
        age = (
            current - datetime.fromisoformat(worker["at"])
        ).total_seconds()
        running = 0 <= age < 300

        st.write(
            "Worker:",
            "Recent heartbeat" if running else "Stopped or stale",
            "·",
            worker["state"],
        )
        st.caption(f"Last heartbeat: {worker['at']}")

        if worker.get("check_from"):
            st.write("Scheduled check time:", worker["check_from"])

        st.caption(
            "Automatic AI generation: "
            + ("on" if worker.get("automatic_messages") else "off")
        )

        if worker.get("error"):
            st.warning(
                "Last worker problem: " + worker["error"]
            )
    else:
        st.info("No worker heartbeat recorded for this commuter yet.")

    st.caption(
        "The existing background worker monitors Tim only. "
        "Other commuters currently use the manual buttons."
    )

    snap = storage.read("snapshot", {}, commuter_id=selected_id)
    if not snap:
        st.info("No service check saved for this commuter.")
        return

    if snap.get("profile_key") != profile_key(profile):
        st.warning(
            "This service check belongs to older settings. "
            "Save a fresh baseline and check again."
        )
        return

    age = (
        current - datetime.fromisoformat(snap["at"])
    ).total_seconds()
    fresh = 0 <= age <= 300
    st.caption(f"Service evidence checked: {snap['at']}")

    if not fresh:
        st.warning(
            "These service results are stale and do not establish "
            "current conditions."
        )
    elif snap["state"] == "clear":
        st.success(
            "No disruptions reported on the checked lines. "
            "This does not guarantee every service is running."
        )
    elif snap["state"] == "unknown":
        st.warning("Unable to check all monitored services.")
    else:
        st.warning(
            "Disruption reported on a monitored line. "
            "Impact on this journey's section is unconfirmed."
        )

    for issue in snap.get("issues", []):
        st.write(f"**{issue['line']} · {issue['status']}**")
        st.write(issue["reason"])
        st.caption(issue["scope"])

    if snap.get("failures"):
        st.write("Unavailable:", ", ".join(snap["failures"]))

    if snap.get("alternatives_error"):
        st.warning(snap["alternatives_error"])


monitor_panel(commuter_id)

st.subheader("AI commute message")
st.caption(
    "Each click checks service status and then requests one AI message. "
    "This uses your OpenAI API credit."
)

if st.button(
    f"Generate message for {p['name']}",
    disabled=not baseline_valid,
    type="primary",
):
    with st.spinner("Checking services and preparing the commute message…"):
        try:
            # Refresh evidence immediately before asking the agent.
            check(p, now_for(p), manual=True)
            run_agent(commuter_id)
            st.success("Message saved. It appears in the shared feed below.")
        except ValueError as error:
            st.error(str(error))
        except OpenAIError:
            st.error(
                "The OpenAI request failed. Check your API configuration "
                "or credit before retrying."
            )
        except Exception:
            st.error("Unable to generate a message. Check the terminal for details.")

st.subheader("Everyone's commute messages")
st.caption(
    "Saved messages appear newest first. They describe the evidence "
    "available when generated; they are not continuously updated."
)


@st.fragment(run_every=30)
def message_feed():
    current_profiles = {
        profile["id"]: profile for profile in storage.load_profiles()
    }
    history = storage.events(commuter_id=None, limit=200)
    messages = [
        event for event in history
        if event.get("type") == "commute_message"
    ]

    if not messages:
        st.info("No AI messages saved yet. Generate the first one above.")
        return

    for event in messages:
        result = event.get("result", {})
        person_id = event["commuter_id"]
        person = current_profiles.get(person_id)
        person_name = (
            person["name"]
            if person
            else result.get("commuter_name", person_id)
        )

        with st.container(border=True):
            st.write(f"**{person_name} · {result.get('travel_date', '')}**")
            st.caption(
                f"Generated: {result.get('generated_at', event['at'])} "
                f"· {result.get('mode', 'manual')}"
            )

            if person and result.get("profile_key") != profile_key(person):
                st.warning(
                    "This message was generated before this person's "
                    "latest settings change."
                )

            st.text(result.get("message", "Message text unavailable."))


message_feed()

if baseline_valid:
    with st.expander("Saved connections and monitoring limits"):
        discovery = base.get("discovery", {})
        candidates = discovery.get("candidates", [])

        if candidates:
            st.dataframe(candidates, width="stretch")
            st.caption(
                "These are geographic bus connections, not confirmed "
                "departures for the travel window."
            )
        else:
            st.write(
                "Monitoring uses the transport lines identified in "
                "saved and daily journey options. Wider bus-corridor "
                "discovery is not configured for this commuter."
            )

        if discovery.get("failures"):
            st.warning(
                "Wider bus discovery incomplete: "
                + ", ".join(discovery["failures"])
            )

        st.write(
            "Journey options are sampled, so monitoring does not cover "
            "every possible route. Service reports are line-wide; "
            "impact on a particular journey section is unconfirmed."
        )