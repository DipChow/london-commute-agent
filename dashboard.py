"""Local-only Streamlit dashboard. Run from the project root."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
from commute_agent import storage
from commute_agent.commute import DAYS, baseline, check, get_plan, profile_key, travel_date

st.set_page_config(page_title="Tim's Commute", page_icon='🚇', layout='wide')
st.title("Tim's Commute")
st.caption('Morning travel · London time · Powered by the Transport for London Journey Planner API')
try: p = storage.load_profile()
except (OSError, ValueError, StopIteration):
    st.error('Missing Tim profile. Run from the project folder with config/commuters.local.json present.')
    st.stop()

with st.sidebar:
    st.header('Commute settings')
    with st.form('settings'):
        origin = st.text_input('Home address', p['origin']['address'])
        destination = st.text_input('Destination address', p['destination']['address'])
        start = st.time_input('Arrive from', time.fromisoformat(p['time_window']['start']))
        end = st.time_input('Arrive by', time.fromisoformat(p['time_window']['end']))
        days = st.multiselect('Travel days', DAYS, default=p['travel_days'])
        warning = st.number_input('Check minutes before leaving home', min_value=0, max_value=180, value=p['advance_warning_minutes'])
        if st.form_submit_button('Save settings'):
            if not origin.strip() or not destination.strip() or not days or end <= start:
                st.error('Enter both addresses, at least one day and an end time after the start.')
            else:
                p['origin']['address'], p['destination']['address'] = origin.strip(), destination.strip()
                p['time_window'] = {'type':'arrival','start':start.strftime('%H:%M'),'end':end.strftime('%H:%M')}
                p['travel_days'], p['advance_warning_minutes'] = days, int(warning)
                storage.save_profile(p)
                st.success('Saved. Preview and save a new baseline before monitoring.')
    st.caption('The bus corridor is still Dunton Road WN → Elephant & Castle. Changing addresses does not automatically discover other corridors.')
    st.info('Alerts appear here and in the local history. SMS is not connected.')

now = datetime.now(ZoneInfo(p['timezone']))
a,b,c = st.columns(3)
a.metric('Arrive at destination', f'{p["time_window"]["start"]}–{p["time_window"]["end"]}')
b.metric('Advance warning', f'{p["advance_warning_minutes"]} min')
c.metric('Commuters', '1')
st.write(f'**{p["origin"]["address"]} → {p["destination"]["address"]}**')

left,right = st.columns(2)
with left:
    if st.button('Preview morning journeys', type='primary'):
        with st.spinner('Checking the beginning, middle and end of the arrival window…'):
            try: storage.write('preview', get_plan(p, travel_date(p, now)))
            except Exception: st.error('TfL journey request failed. Retry shortly; no saved baseline was changed.')
with right:
    if st.button('Save current routes as baseline'):
        with st.spinner('Saving journeys and discovering wider bus connections…'):
            try:
                baseline(p, now)
                storage.write('daily_plan', {})
                st.success('Baseline saved. The worker will monitor these services.')
            except Exception as error:
                st.error(str(error) if isinstance(error, ValueError) else 'TfL lookup failed. Retry shortly.')

base = storage.read('baseline', {})
if base and base.get('key') != profile_key(p):
    st.warning('Settings changed. Monitoring is paused until you save a new baseline.')
if not base: st.info('Preview the journeys and resolved locations, then save the baseline to enable monitoring.')

preview = storage.read('preview', {})
if preview.get('key') != profile_key(p): preview = {}
plan = preview or (base if base.get('key') == profile_key(p) else {})
if plan:
    st.subheader(f'Journey options · {plan["date"]}')
    st.caption('Sampled at the beginning, middle and end of the arrival window; only arrivals inside the window are shown. This is not an exhaustive timetable.')
    if plan.get('check_from'): st.write('Proposed monitoring start:', datetime.fromisoformat(plan['check_from']).strftime('%H:%M'))
    for i,j in enumerate(plan.get('journeys', []),1):
        depart, arrive = datetime.fromisoformat(j['startDateTime']), datetime.fromisoformat(j['arrivalDateTime'])
        with st.expander(f'Option {i} · leave {depart:%H:%M} → arrive {arrive:%H:%M} · {j["duration"]} min', expanded=i==1):
            for leg in j.get('legs', []):
                st.write(f'{leg.get("mode",{}).get("name","")} · {leg.get("instruction",{}).get("summary","")} · {leg.get("duration","?")} min')
            legs = j.get('legs', [])
            if legs:
                st.write('TfL resolved starting point:', legs[0].get('departurePoint', {}))
                st.write('TfL resolved destination:', legs[-1].get('arrivalPoint', {}))
    if plan.get('diagnostics'):
        with st.expander('Location matches / unsuccessful samples'): st.json(plan['diagnostics'])
    st.caption('Inspect the resolved point names and coordinates. A successful address search may resolve to a street rather than a specific entrance. Saved raw journey points retain that evidence.')

st.subheader('Service monitor')
if st.button('Check reported service status now'):
    try: check(p, now, manual=True)
    except Exception as error: st.error(str(error) if isinstance(error, ValueError) else 'Unable to check TfL right now.')

@st.fragment(run_every=30)
def monitor_panel():
    current = datetime.now(ZoneInfo(p['timezone']))
    worker = storage.read('worker', {})
    if worker:
        age = (current-datetime.fromisoformat(worker['at'])).total_seconds()
        st.write('Worker:', 'Running' if age < 300 else 'Stopped or stale', '·', worker['state'], '· last heartbeat', worker['at'])
        if worker.get('check_from'): st.write('Next monitoring window starts:', worker['check_from'])
        if worker.get('error'): st.error(worker['error'])
    else: st.warning('Worker has not started. Start it in a second terminal; opening this page does not start scheduled monitoring.')
    snap = storage.read('snapshot', {})
    if snap:
        age = (current-datetime.fromisoformat(snap['at'])).total_seconds()
        st.caption(f'Last service check: {snap["at"]} · {"manual preview" if snap["manual"] else "scheduled"}')
        if age > 300: st.warning('Service results are stale. They do not establish current conditions.')
        if snap['state'] == 'clear': st.success('No active disruptions reported on the checked lines. This does not guarantee every bus is running.')
        elif snap['state'] == 'unknown': st.error('Unable to check all services.')
        else: st.warning('Reported disruption on a monitored line. Tim’s section may be affected.')
        for issue in snap['issues']:
            st.write(f'**{issue["line"]} · {issue["status"]}**')
            st.write(issue['reason'])
            st.caption(issue['scope'])
        if snap['failures']: st.write('Unavailable:', ', '.join(snap['failures']))
        if snap.get('alternatives_error'): st.warning(snap['alternatives_error'])
        alternatives = storage.read('alternatives', {})
        if snap['issues'] and alternatives.get('key') == profile_key(p) and alternatives.get('date') == snap['date']:
            with st.expander('Fresh TfL journey suggestions after reported disruption'):
                st.caption('Requested at '+alternatives['checked_at']+'. Suggestions may still use an affected line; they are not guaranteed disruption-free.')
                for journey in alternatives.get('journeys', []):
                    st.write(journey['startDateTime'], '→', journey['arrivalDateTime'])
                    for leg in journey.get('legs', []): st.write(leg.get('instruction', {}).get('summary', ''))
    st.subheader('Alert history')
    history = storage.events()
    if history: st.dataframe(history, use_container_width=True)
    else: st.caption('No scheduled alert events recorded.')
monitor_panel()

if base:
    with st.expander('Saved bus connections and monitoring limits'):
        st.dataframe(base['discovery']['candidates'], use_container_width=True)
        if base['discovery']['failures']: st.warning('Discovery incomplete: '+', '.join(base['discovery']['failures']))
        st.write('Bus connections are geographic candidates, not confirmed services at the travel time. Night-only candidates remain visible but are excluded from the wider daytime watch list unless a saved journey uses them.')
        st.write('Warnings use line-wide reports. Automatic segment matching is not implemented. Reported warnings trigger fresh TfL journey suggestions; the saved baseline stays intact.')
