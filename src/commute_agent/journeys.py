"""CLI address-to-address preview using the same settings as the dashboard."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from commute_agent.storage import load_profile
from commute_agent.commute import get_plan, travel_date

def main():
    p = load_profile()
    now = datetime.now(ZoneInfo(p['timezone']))
    print(json.dumps(get_plan(p, travel_date(p, now)), indent=2))

if __name__ == '__main__': main()
