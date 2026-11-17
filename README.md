# London Commute Agent

A personal project that uses TfL data to monitor commute disruptions, check journey alternatives and explain what a service change may mean for your route.

## First version

- Show live status for selected TfL lines.
- Look up live bus arrivals at selected stops.
- Add journey planning and a disruption history.
- Later, add an assistant that explains relevant changes using TfL's results.

## Data source

This project uses the [TfL Unified API](https://api.tfl.gov.uk/).

## Set up

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .