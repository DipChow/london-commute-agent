"""Run independently: python -m commute_agent.worker."""
import argparse
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from commute_agent import storage
from commute_agent.commute import check

def tick():
    now = datetime.now(ZoneInfo('Europe/London'))
    try:
        result = check(storage.load_profile(), now)
        storage.write('worker', {'at':now.isoformat(), 'state':result['state'], 'check_from':result.get('check_from')})
    except Exception as error:
        # Do not store requests exception strings, which can contain API keys.
        message = str(error) if isinstance(error, (ValueError, FileNotFoundError)) else type(error).__name__
        storage.write('worker', {'at':now.isoformat(), 'state':'error', 'error':message})
        print(f'{now:%H:%M} Unable to check: {message}', flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    while True:
        tick()
        if args.once: return
        time.sleep(120)

if __name__ == '__main__': main()
