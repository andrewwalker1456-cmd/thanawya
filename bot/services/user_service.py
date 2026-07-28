import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

DB_PATH = "data/bot_state.db"

def init_db():
    """Initialize the bot state database and create the users table."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                subscribed INTEGER DEFAULT 0,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to initialize bot_state DB: {e}")
    finally:
        conn.close()

def register_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> None:
    """Save or update user in database."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, last_seen)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_seen = CURRENT_TIMESTAMP
        """, (user_id, username, first_name, last_name))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to register user {user_id}: {e}")
    finally:
        conn.close()

def set_subscription_status(user_id: int, subscribed: bool) -> None:
    """Update user's subscription status."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE users 
            SET subscribed = ? 
            WHERE user_id = ?
        """, (1 if subscribed else 0, user_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to update subscription status for {user_id}: {e}")
    finally:
        conn.close()

def get_subscribed_users() -> List[Tuple[int, str, str, str, str]]:
    """Retrieve all users marked as subscribed."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, username, first_name, last_name, last_seen 
            FROM users 
            WHERE subscribed = 1
            ORDER BY last_seen DESC
        """)
        return cur.fetchall()
    except Exception as e:
        logger.error(f"Failed to fetch subscribed users: {e}")
        return []
    finally:
        conn.close()

# Initialize DB on import
init_db()
