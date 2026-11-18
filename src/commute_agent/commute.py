"""Journey baselines, wider bus discovery and conservative disruption assessment."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
from commute_agent import storage, tfl_client as api

DAYS = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']

def local_time(value, zone):
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=zone) if dt.tzinfo is None else dt.astimezone(zone)

def profile_key(p):
    route_settings = {
        key: value
        for key, value in p.items()
        if key not in {"name", "enabled"}
    }
    return hashlib.sha256(
        json.dumps(route_settings, sort_keys=True).encode()
    ).hexdigest()

def travel_date(p, now):
    if not p['travel_days']: raise ValueError('Choose at least one travel day.')
    day = now.date()
    end = datetime.strptime(p['time_window']['end'], '%H:%M').time()
    if now.time().replace(tzinfo=None) > end: day += timedelta(days=1)
    while DAYS[day.weekday()] not in p['travel_days']: day += timedelta(days=1)
    return day

def get_plan(p, day):
    zone = ZoneInfo(p['timezone'])
    window = p['time_window']
    start = datetime.fromisoformat(f'{day}T{window["start"]}').replace(tzinfo=zone)
    end = datetime.fromisoformat(f'{day}T{window["end"]}').replace(tzinfo=zone)
    if end <= start: raise ValueError('Arrival end must be after arrival start.')
    journeys, diagnostics, seen = [], [], set()
    for target in [start, start + (end-start)/2, end]:
        origin = p['origin']
        destination = p['destination']
        origin_query = origin.get('journey_location') if origin.get('resolved_address') == origin['address'] else None
        destination_query = destination.get('journey_location') if destination.get('resolved_address') == destination['address'] else None
        result = api.plan_journey(origin_query or origin['address'], destination_query or destination['address'],
            date=day.strftime('%Y%m%d'), time=target.strftime('%H%M'), time_is='Arriving')
        if not result.get('journeys'):
            diagnostics.append({k:result.get(k) for k in ['fromLocationDisambiguation','toLocationDisambiguation','$type']})
        for j in result.get('journeys', []):
            arrival = local_time(j['arrivalDateTime'], zone)
            signature = json.dumps([j['startDateTime'], j['arrivalDateTime'], j.get('legs')], sort_keys=True)
            if start <= arrival <= end and signature not in seen:
                seen.add(signature)
                journeys.append(j)
    journeys.sort(key=lambda j: j['arrivalDateTime'])
    departures = [local_time(j['startDateTime'], zone) for j in journeys]
    return {'date':str(day), 'journeys':journeys, 'diagnostics':diagnostics,
        'check_from':(min(departures)-timedelta(minutes=p['advance_warning_minutes'])).isoformat() if departures else None,
        'key':profile_key(p), 'sampled':True}

def discover(p):
    origin_id = p.get("origin", {}).get("stop_id")
    interchange = p.get("interchange_search")

    if not origin_id or not interchange:
        return {
            "candidates": [],
            "failures": [],
            "key": profile_key(p),
            "coverage": "saved_journeys_only",
        }
    origin = api.get_stop_details(origin_id)
    ids = {i for g in origin.get('lineModeGroups', []) if g.get('modeName') == 'bus' for i in g.get('lineIdentifier', [])}
    candidates, failures = [], []
    def fetch(pair):
        line_id, direction = pair
        try: return line_id, direction, api.get_route_sequence(line_id, direction)
        except (requests.RequestException, ValueError): return line_id, direction, None
    pairs = [(i,d) for i in sorted(ids) for d in ['inbound','outbound']]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(fetch, pairs))
    for line_id, direction, route in results:
            if route is None:
                failures.append(f'{line_id} {direction}')
                continue
            for sequence in route.get('stopPointSequences', []):
                stops = sequence.get('stopPoint', [])
                for index, stop in enumerate(stops):
                    if stop.get('id') != origin_id: continue
                    for later in stops[index+1:]:
                        if p['interchange_search'].casefold() in later.get('name','').casefold():
                            candidate = {'line':line_id, 'direction':direction, 'stop_id':later['id'], 'stop':later['name']}
                            if candidate not in candidates: candidates.append(candidate)
    if not ids: failures.append('No bus mode grouping returned for origin stop')
    return {'candidates':candidates, 'failures':failures, 'key':profile_key(p)}

def line_ids(plan):
    ids = set()
    for journey in plan.get('journeys', []):
        for leg in journey.get('legs', []):
            for option in leg.get('routeOptions', []):
                identifier = option.get('lineIdentifier', {})
                if isinstance(identifier, dict) and identifier.get('id'):
                    ids.add(identifier['id'])
    return ids

def baseline(p, now):
    commuter_id = p["id"]
    day = travel_date(p, now)
    plan = get_plan(p, day)
    if not plan['journeys']: raise ValueError('No journeys within the window. Inspect address matches in Journey preview.')
    buses = discover(p)
    result = {**plan, 'discovery':buses, 'created_at':now.isoformat()}
    storage.write('baseline', result, commuter_id=commuter_id)
    return result

def status_issues(lines, now):
    issues = []
    for line in lines:
        for status in line.get('lineStatuses', []):
            periods = status.get('validityPeriods', [])
            if periods:
                active = False
                for period in periods:
                    left, right = period.get('fromDate'), period.get('toDate')
                    if (not left or local_time(left, now.tzinfo) <= now) and (not right or now <= local_time(right, now.tzinfo)):
                        active = True
                if not active: continue
            description = status.get('statusSeverityDescription', 'Unknown')
            if description.casefold() not in {'good service', 'no issues'}:
                issues.append({'line':line['id'], 'status':description,
                    'reason':status.get('reason',''), 'scope':'Line-wide report; impact on the saved journey section is unconfirmed.'})
    return issues

def check(p, now, manual=False):
    commuter_id = p["id"]
    base = storage.read('baseline', commuter_id=commuter_id)
    if not base or base['key'] != profile_key(p): raise ValueError('Save a route baseline for the current settings first.')
    day = travel_date(p, now)
    daily = storage.read('daily_plan', {}, commuter_id=commuter_id)
    if daily.get('date') != str(day) or daily.get('key') != profile_key(p):
        daily = get_plan(p, day)
        storage.write('daily_plan', daily, commuter_id=commuter_id)
    start = daily.get('check_from')
    end = datetime.fromisoformat(f'{day}T{p["time_window"]["end"]}').replace(tzinfo=now.tzinfo)
    in_window = bool(start and local_time(start, now.tzinfo) <= now <= end)
    if not manual and not in_window:
        return {'state':'waiting', 'check_from':start, 'date':str(day)}
    ids = (
        set(p.get("rail_line_ids", []))
        | line_ids(base)
        | line_ids(daily)
    )
    ids |= {c['line'] for c in base['discovery']['candidates'] if not c['line'].lower().startswith('n')}
    lines = []
    failures = [] if ids else ["No transport lines identified for monitoring"]
    ordered = sorted(ids)
    for offset in range(0,len(ordered),15):
        batch = ordered[offset:offset+15]
        try:
            received = api.get_line_status(batch)
            lines.extend(received)
            failures.extend(f'{i}: no status returned' for i in set(batch)-{l['id'] for l in received if l.get('lineStatuses')})
        except (requests.RequestException, ValueError): failures.extend(batch)
    issues = status_issues(lines, now)
    state = 'unknown' if failures else 'warning' if issues else 'clear'
    snapshot = {'at':now.isoformat(), 'state':state, 'issues':issues, 'failures':failures,
        'lines':lines, 'check_from':start, 'date':str(day), 'manual':manual,
        'discovery_incomplete':bool(base['discovery']['failures'])}
    if issues:
        try:
            alternatives = get_plan(p, day)
            storage.write(
                "alternatives",
                {**alternatives, "checked_at": now.isoformat()},
                commuter_id=commuter_id,
            )
        except (requests.RequestException, ValueError):
            snapshot['alternatives_error'] = 'Unable to retrieve fresh journey alternatives.'
    snapshot["profile_key"] = profile_key(p)
    storage.write('snapshot', snapshot, commuter_id=commuter_id)
    # Manual previews never send or change scheduled alert state.
    if in_window and not manual:
        signature = json.dumps([state,issues,failures], sort_keys=True)
        previous = storage.read('alert_state', {}, commuter_id=commuter_id)
        if signature != previous.get('signature'):
            if state != 'clear' or previous.get('state') in {'warning','unknown'}:
                storage.event(
                    now.isoformat(),
                    {
                        "state": state,
                        "issues": issues,
                        "failures": failures,
                        "message": (
                            "Reported service change"
                            if state == "warning"
                            else "Status recovered"
                            if state == "clear"
                            else "Unable to check all services"
                        ),
                    },
                    commuter_id=commuter_id,
                )
            storage.write('alert_state', {'signature':signature,'state':state}, commuter_id=commuter_id)
    return snapshot
