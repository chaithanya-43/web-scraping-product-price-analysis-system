import sqlite3
from pathlib import Path
from flask import session


DATABASE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "users.db"


def get_connection():
    """
    Create and return a SQLite database connection.
    """

    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


def current_user_id():
    """Return the signed-in user only while the account session is current."""
    user_id = session.get("user_id")
    session_version = session.get("session_version")
    if user_id is None or session_version is None:
        session.clear()
        return None
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT session_version FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        connection.close()
    if row is None or row["session_version"] != session_version:
        session.clear()
        return None
    return user_id


def init_database():
    """
    Create the users and analysis history tables.
    """

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            session_version INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source_url TEXT NOT NULL,
            pages_scraped INTEGER NOT NULL,
            products_found INTEGER NOT NULL,
            minimum_price REAL,
            maximum_price REAL,
            average_price REAL,
            median_price REAL,
            source_name TEXT,
            products_json TEXT,
            analyzed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)

    columns = {
        row["name"]
        for row in cursor.execute("PRAGMA table_info(analysis_history)").fetchall()
    }
    if "currency" not in columns:
        cursor.execute("ALTER TABLE analysis_history ADD COLUMN currency TEXT")
    if "source_name" not in columns:
        cursor.execute("ALTER TABLE analysis_history ADD COLUMN source_name TEXT")
    if "products_json" not in columns:
        cursor.execute("ALTER TABLE analysis_history ADD COLUMN products_json TEXT")

    user_columns = {
        row["name"] for row in cursor.execute("PRAGMA table_info(users)").fetchall()
    }
    if "session_version" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_requests (
            email_key TEXT PRIMARY KEY,
            ip_key TEXT NOT NULL,
            user_id INTEGER,
            otp_hash TEXT,
            expires_at INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            requested_at INTEGER NOT NULL,
            verified_at INTEGER,
            reset_token_hash TEXT,
            token_expires_at INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_ip_limits (
            ip_key TEXT PRIMARY KEY,
            window_started INTEGER NOT NULL,
            request_count INTEGER NOT NULL
        )
    """)

    connection.commit()
    connection.close()
