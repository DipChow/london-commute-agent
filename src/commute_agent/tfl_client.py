"""Small HTTP client for the TfL Unified API."""

import os

import requests

BASE_URL = "https://api.tfl.gov.uk"


def _api_params() -> dict[str, str]:
    """Include an API key if one has been configured."""
    key = os.getenv("TFL_APP_KEY")
    return {"app_key": key} if key else {}


def get_line_status(line_ids: list[str]) -> list[dict]:
    """Fetch status for line IDs such as 'victoria' or 'central'."""
    ids = ",".join(line_ids)
    response = requests.get(
        f"{BASE_URL}/Line/{ids}/Status",
        params=_api_params(),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def get_bus_arrivals(stop_id: str) -> list[dict]:
    """Fetch live arrival predictions for a TfL stop ID."""
    response = requests.get(
        f"{BASE_URL}/StopPoint/{stop_id}/Arrivals",
        params=_api_params(),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def plan_journey(origin_id: str, destination_id: str) -> dict:
    """Fetch journey options departing now."""
    params = _api_params()
    params["timeIs"] = "Departing"

    response = requests.get(
        f"{BASE_URL}/Journey/JourneyResults/{origin_id}/to/{destination_id}",
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()