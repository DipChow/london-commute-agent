# Tim's commute: first dashboard and monitor

This is a separate runnable copy. Keep your existing london-commute-agent folder intact. TfL returned named matches for 44 MARCIA ROAD, Southwark and 5 MERCHANT SQUARE, Westminster (London); their coordinates are saved in the private profile. Changing an address invalidates that endpoint’s saved coordinates. The supplied private profile contains Tim's addresses and the updated 08:50–09:10 weekday arrival window. Do not publish the ZIP or add commuters.local.json to Git.

Unzip, open the extracted tim-update folder in VS Code, then run in its terminal:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m streamlit run dashboard.py --server.address 127.0.0.1
```

Open the localhost URL printed by Streamlit. Choose **Preview morning journeys**. Expand an option and inspect TfL's resolved start/end names and coordinates. Then choose **Save current routes as baseline**. This saves the returned raw locations and route legs plus wider candidate bus connections. It does not establish that an address resolves to the exact building entrance. Correct the address and preview again if the location is wrong.

In a second VS Code terminal, from this same folder:

```bash
source .venv/bin/activate
python -m commute_agent.worker
```

Keep that process running. The worker samples the arrival-window start, midpoint and end to derive the earliest sampled leave-home time, starts service checks 30 minutes before that, and polls every two minutes through the arrival-window end. It prepares the next travel day's schedule outside the window. Ctrl+C stops it. A sleeping or shut-down Mac cannot monitor. This version is local, not deployed or configured as a login service.

## What works

- Editable addresses, arrival times, weekdays and advance warning for Tim only.
- Address-to-address journey samples including walking and returned location evidence.
- Explicit saved route baseline; subsequent journey previews never silently replace it.
- Wider Dunton Road WN to Elephant & Castle bus discovery, with direction and downstream stop checks.
- Current line status, partial-fetch errors, timestamps and stale-worker indication.
- A separate scheduled monitoring worker and persistent, deduplicated local alert events, including recovery. Manual previews do not create alert events.
- SQLite local storage, API timeouts, bounded request batches; optional TFL_APP_KEY environment variable. Existing .env files are not automatically loaded: export TFL_APP_KEY in each relevant terminal if required.

## Deliberate first-version limits

Line status warnings are conservative and line-wide; they do not prove Tim's section is disrupted. Bus candidates are not an exhaustive timetable and their interchange walks are not individually validated. A saved journey validates only its own returned connection. No bus arrival predictions are used to infer service failure. Night candidates are retained for review and excluded from the wider daytime watch list. Exact building/entrance geocoding, automatic section matching, SMS delivery, hosted execution and additional commuters are future steps. Reported warnings trigger fresh journey suggestions without replacing the saved baseline. These may still use affected lines and are not guaranteed disruption-free.

The monitor is deterministic Python code using TfL evidence. No LLM or OpenAI API key is required for this first agent. The dashboard explicitly distinguishes unknown, stale and reported-warning states.

Tests: `python -m unittest discover -s tests -v`.

## Integrating into your existing repository later

After checking this copy, copy dashboard.py and the src/commute_agent Python modules into your existing project; add streamlit>=1.40,<2 to pyproject.toml dependencies and merge .gitignore entries. Preserve your other scripts. Back up any files before replacing them. The profile is local-only. The GitHub integration in this session allowed reads but returned 403 for branch creation, so no repository changes were pushed.

Data: https://api.tfl.gov.uk/swagger/docs/v1
Powered by the Transport for London Journey Planner API.
