"""Store commuter profiles and separate each commuter's saved state."""

import json
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(os.getenv("COMMUTE_PROJECT_ROOT", Path.cwd())).resolve()
PROFILE = ROOT / "config" / "commuters.local.json"
DB = ROOT / "data" / "commute.db"


def validate_commuter_id(commuter_id):
    """Keep IDs predictable and safe to use in storage keys."""
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", commuter_id):
        raise ValueError(
            "Commuter IDs must contain lowercase letters, numbers, "
            "underscores or hyphens."
        )


def load_profiles():
    """Return every saved commuter without changing their settings."""
    with PROFILE.open(encoding="utf-8") as file:
        profiles = json.load(file)["commuters"]

    seen = set()

    for profile in profiles:
        commuter_id = profile["id"]
        validate_commuter_id(commuter_id)

        if commuter_id in seen:
            raise ValueError(f"Duplicate commuter ID: {commuter_id}")

        seen.add(commuter_id)

    return profiles


def load_profile(commuter_id="tim"):
    """Find one commuter. Existing calls still default to Tim."""
    validate_commuter_id(commuter_id)

    for profile in load_profiles():
        if profile["id"] == commuter_id:
            return profile

    raise ValueError(f"Commuter not found: {commuter_id}")


def save_profile(profile):
    """Add or update one commuter while preserving everyone else."""
    commuter_id = profile["id"]
    validate_commuter_id(commuter_id)

    with PROFILE.open(encoding="utf-8") as file:
        document = json.load(file)

    profiles = document["commuters"]

    for index, existing in enumerate(profiles):
        if existing["id"] == commuter_id:
            profiles[index] = profile
            break
    else:
        profiles.append(profile)

    # Write a complete temporary file before replacing the original.
    descriptor, temporary_name = tempfile.mkstemp(
        dir=PROFILE.parent,
        prefix=".commuters-",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(document, file, indent=2)

        temporary_path.replace(PROFILE)
    finally:
        temporary_path.unlink(missing_ok=True)


def record_key(key, commuter_id):
    """Preserve Tim's existing keys; separate other commuters' records."""
    validate_commuter_id(commuter_id)

    if key.startswith("commuter:"):
        raise ValueError("Pass the commuter ID separately from the record key.")

    if commuter_id == "tim":
        return key

    return f"commuter:{commuter_id}:{key}"


@contextmanager
def connect():
    """Open a transaction and always close its database connection."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB, timeout=30)

    try:
        # Serialise schema setup if two processes start together.
        connection.execute("BEGIN IMMEDIATE")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                key TEXT PRIMARY KEY,
                body TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                at TEXT,
                body TEXT,
                commuter_id TEXT NOT NULL DEFAULT 'tim'
            )
            """
        )

        # Upgrade the original event table, preserving Tim's history.
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(events)")
        }

        if "commuter_id" not in columns:
            connection.execute(
                "ALTER TABLE events ADD COLUMN "
                "commuter_id TEXT NOT NULL DEFAULT 'tim'"
            )

        yield connection
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def read(key, default=None, *, commuter_id="tim"):
    """Read one commuter's saved record."""
    stored_key = record_key(key, commuter_id)

    with connect() as connection:
        row = connection.execute(
            "SELECT body FROM records WHERE key = ?",
            (stored_key,),
        ).fetchone()

    return json.loads(row[0]) if row else default


def write(key, value, *, commuter_id="tim"):
    """Save one commuter's record."""
    stored_key = record_key(key, commuter_id)

    with connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO records (key, body) VALUES (?, ?)",
            (stored_key, json.dumps(value)),
        )


def event(at, value, *, commuter_id="tim"):
    """Append an event belonging to one commuter."""
    validate_commuter_id(commuter_id)

    with connect() as connection:
        connection.execute(
            "INSERT INTO events (at, body, commuter_id) VALUES (?, ?, ?)",
            (at, json.dumps(value), commuter_id),
        )


def events(commuter_id="tim", limit=30):
    """Read one person's history, or everyone's when ID is None."""
    if commuter_id is not None:
        validate_commuter_id(commuter_id)

    with connect() as connection:
        if commuter_id is None:
            rows = connection.execute(
                """
                SELECT at, body, commuter_id
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT at, body, commuter_id
                FROM events
                WHERE commuter_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (commuter_id, limit),
            ).fetchall()

    return [
        {
            **json.loads(body),
            "at": at,
            "commuter_id": owner,
        }
        for at, body, owner in rows
    ]