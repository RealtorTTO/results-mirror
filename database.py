"""Results Mirror™ — Database layer for agent profiles and session tracking."""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.environ.get("DATABASE_PATH", "/opt/render/project/src/data/mirror.db")

def get_db():
    """Get a database connection, creating tables if needed."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    
    # Create tables
    db.executescript("""
        CREATE TABLE IF NOT EXISTS approved_emails (
            email TEXT PRIMARY KEY,
            agent_name TEXT,
            added_at TEXT DEFAULT (datetime('now')),
            active INTEGER DEFAULT 1
        );
        
        CREATE TABLE IF NOT EXISTS agents (
            email TEXT PRIMARY KEY,
            first_name TEXT NOT NULL,
            coaching_style TEXT DEFAULT 'straight',
            total_sessions INTEGER DEFAULT 0,
            first_session_at TEXT,
            last_session_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_email TEXT NOT NULL,
            door TEXT NOT NULL,
            coaching_style TEXT,
            client_profile TEXT,
            summary TEXT,
            patterns_identified TEXT,
            strengths_noted TEXT,
            areas_for_growth TEXT,
            messages_json TEXT,
            started_at TEXT DEFAULT (datetime('now')),
            ended_at TEXT,
            FOREIGN KEY (agent_email) REFERENCES agents(email)
        );
        
        CREATE TABLE IF NOT EXISTS progress_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_email TEXT NOT NULL,
            note_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_email) REFERENCES agents(email)
        );
    """)
    db.commit()
    return db


# ===== APPROVED EMAILS =====

def is_email_approved(email):
    db = get_db()
    row = db.execute("SELECT * FROM approved_emails WHERE LOWER(email) = LOWER(?) AND active = 1", (email,)).fetchone()
    db.close()
    return row is not None


def add_approved_email(email, agent_name=""):
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO approved_emails (email, agent_name, active) VALUES (LOWER(?), ?, 1)",
        (email, agent_name)
    )
    db.commit()
    db.close()


def add_approved_emails_bulk(email_list):
    """Add multiple emails at once. email_list is a list of (email, name) tuples."""
    db = get_db()
    db.executemany(
        "INSERT OR REPLACE INTO approved_emails (email, agent_name, active) VALUES (LOWER(?), ?, 1)",
        email_list
    )
    db.commit()
    db.close()


def list_approved_emails():
    db = get_db()
    rows = db.execute("SELECT email, agent_name, added_at, active FROM approved_emails ORDER BY agent_name").fetchall()
    db.close()
    return [dict(r) for r in rows]


def remove_approved_email(email):
    db = get_db()
    db.execute("UPDATE approved_emails SET active = 0 WHERE LOWER(email) = LOWER(?)", (email,))
    db.commit()
    db.close()


# ===== AGENT PROFILES =====

def get_or_create_agent(email, first_name):
    db = get_db()
    agent = db.execute("SELECT * FROM agents WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
    if not agent:
        db.execute(
            "INSERT INTO agents (email, first_name, first_session_at) VALUES (LOWER(?), ?, datetime('now'))",
            (email, first_name)
        )
        db.commit()
        agent = db.execute("SELECT * FROM agents WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
    else:
        # Update first name if changed
        if first_name and first_name != agent["first_name"]:
            db.execute("UPDATE agents SET first_name = ? WHERE LOWER(email) = LOWER(?)", (first_name, email))
            db.commit()
    db.close()
    return dict(agent) if agent else None


def get_agent(email):
    db = get_db()
    agent = db.execute("SELECT * FROM agents WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
    db.close()
    return dict(agent) if agent else None


# ===== SESSIONS =====

def create_session(agent_email, door, coaching_style="straight", client_profile=None):
    db = get_db()
    cur = db.execute(
        "INSERT INTO sessions (agent_email, door, coaching_style, client_profile) VALUES (LOWER(?), ?, ?, ?)",
        (agent_email, door, coaching_style, json.dumps(client_profile) if client_profile else None)
    )
    session_id = cur.lastrowid
    
    # Update agent stats
    db.execute(
        "UPDATE agents SET total_sessions = total_sessions + 1, last_session_at = datetime('now') WHERE LOWER(email) = LOWER(?)",
        (agent_email,)
    )
    db.commit()
    db.close()
    return session_id


def update_session(session_id, summary=None, patterns=None, strengths=None, growth_areas=None, messages=None):
    db = get_db()
    updates = []
    params = []
    
    if summary:
        updates.append("summary = ?")
        params.append(summary)
    if patterns:
        updates.append("patterns_identified = ?")
        params.append(patterns)
    if strengths:
        updates.append("strengths_noted = ?")
        params.append(strengths)
    if growth_areas:
        updates.append("areas_for_growth = ?")
        params.append(growth_areas)
    if messages:
        updates.append("messages_json = ?")
        params.append(json.dumps(messages))
    
    updates.append("ended_at = datetime('now')")
    params.append(session_id)
    
    if updates:
        db.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?", params)
        db.commit()
    db.close()


def get_agent_sessions(agent_email, limit=10):
    db = get_db()
    rows = db.execute(
        "SELECT id, door, coaching_style, summary, patterns_identified, strengths_noted, areas_for_growth, started_at FROM sessions WHERE LOWER(agent_email) = LOWER(?) ORDER BY started_at DESC LIMIT ?",
        (agent_email, limit)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_agent_session_count(agent_email):
    db = get_db()
    row = db.execute("SELECT COUNT(*) as cnt FROM sessions WHERE LOWER(agent_email) = LOWER(?)", (agent_email,)).fetchone()
    db.close()
    return row["cnt"] if row else 0


# ===== PROGRESS NOTES =====

def add_progress_note(agent_email, note_type, content):
    """note_type: 'pattern', 'breakthrough', 'regression', 'excuse', 'strength'"""
    db = get_db()
    db.execute(
        "INSERT INTO progress_notes (agent_email, note_type, content) VALUES (LOWER(?), ?, ?)",
        (agent_email, note_type, content)
    )
    db.commit()
    db.close()


def get_progress_notes(agent_email, limit=20):
    db = get_db()
    rows = db.execute(
        "SELECT note_type, content, created_at FROM progress_notes WHERE LOWER(agent_email) = LOWER(?) ORDER BY created_at DESC LIMIT ?",
        (agent_email, limit)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_agent_progress_summary(agent_email):
    """Build a text summary of agent's history for the AI to reference."""
    agent = get_agent(agent_email)
    if not agent:
        return ""
    
    sessions = get_agent_sessions(agent_email, limit=5)
    notes = get_progress_notes(agent_email, limit=10)
    
    summary_parts = []
    summary_parts.append(f"Agent: {agent['first_name']}")
    summary_parts.append(f"Total sessions: {agent['total_sessions']}")
    
    if agent.get('first_session_at'):
        summary_parts.append(f"First session: {agent['first_session_at']}")
    if agent.get('last_session_at'):
        summary_parts.append(f"Last session: {agent['last_session_at']}")
    
    if sessions:
        summary_parts.append("\nRecent sessions:")
        for s in sessions[:5]:
            line = f"- {s['started_at']}: Door '{s['door']}'"
            if s.get('summary'):
                line += f" — {s['summary']}"
            if s.get('patterns_identified'):
                line += f" | Patterns: {s['patterns_identified']}"
            if s.get('strengths_noted'):
                line += f" | Strengths: {s['strengths_noted']}"
            if s.get('areas_for_growth'):
                line += f" | Growth areas: {s['areas_for_growth']}"
            summary_parts.append(line)
    
    if notes:
        summary_parts.append("\nProgress notes:")
        for n in notes[:10]:
            summary_parts.append(f"- [{n['note_type'].upper()}] {n['created_at']}: {n['content']}")
    
    return "\n".join(summary_parts)
