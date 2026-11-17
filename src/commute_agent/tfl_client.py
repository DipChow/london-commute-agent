"""TfL requests with bounded timeouts; never print credential-bearing URLs."""
import os
from urllib.parse import quote
import requests

BASE_URL = 'https://api.tfl.gov.uk'

def _api_params():
    key = os.getenv('TFL_APP_KEY')
    return {'app_key': key} if key else {}

def _get(path, **params):
    response = requests.get(BASE_URL + path, params={**_api_params(), **params}, timeout=30)
    response.raise_for_status()
    return response.json()

def get_line_status(line_ids):
    return _get(f'/Line/{",".join(line_ids)}/Status', detail='true')

def get_bus_arrivals(stop_id):
    return _get(f'/StopPoint/{stop_id}/Arrivals')

def get_stop_details(stop_id):
    return _get(f'/StopPoint/{stop_id}')

def get_route_sequence(line_id, direction):
    return _get(f'/Line/{line_id}/Route/Sequence/{direction}', serviceTypes='Regular,Night')

def plan_journey(origin_id, destination_id, *, date=None, time=None, time_is='Departing'):
    params = {'timeIs': time_is, 'includeAlternativeRoutes': 'true'}
    if date: params['date'] = date
    if time: params['time'] = time
    return _get(f'/Journey/JourneyResults/{quote(origin_id, safe="")}/to/{quote(destination_id, safe="")}', **params)
