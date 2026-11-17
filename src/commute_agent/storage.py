"""Local private profiles and SQLite snapshots shared by worker and display."""
import json
import os
from pathlib import Path
import sqlite3

ROOT = Path(os.getenv('COMMUTE_PROJECT_ROOT', Path.cwd())).resolve()
PROFILE = ROOT / 'config/commuters.local.json'
DB = ROOT / 'data/commute.db'

def load_profile():
    with PROFILE.open(encoding='utf-8') as f:
        return next(p for p in json.load(f)['commuters'] if p['id'] == 'tim')

def save_profile(profile):
    with PROFILE.open(encoding='utf-8') as f: document = json.load(f)
    document['commuters'] = [profile if p['id'] == 'tim' else p for p in document['commuters']]
    temp = PROFILE.with_suffix('.tmp')
    temp.write_text(json.dumps(document, indent=2), encoding='utf-8')
    os.chmod(temp, 0o600)
    temp.replace(PROFILE)

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB, timeout=30)
    connection.execute('CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, body TEXT)')
    connection.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at TEXT, body TEXT)')
    return connection

def read(key, default=None):
    with connect() as c:
        row = c.execute('SELECT body FROM records WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default

def write(key, value):
    with connect() as c:
        c.execute('INSERT OR REPLACE INTO records VALUES (?,?)', (key, json.dumps(value)))

def event(at, value):
    with connect() as c: c.execute('INSERT INTO events(at,body) VALUES (?,?)', (at, json.dumps(value)))

def events():
    with connect() as c:
        return [{'at': r[0], **json.loads(r[1])} for r in c.execute('SELECT at,body FROM events ORDER BY id DESC LIMIT 30')]
