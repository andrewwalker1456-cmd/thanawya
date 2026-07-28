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
        
        # Migration: Add banned column if it doesn't exist
        try:
            cur.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            # Column already exists
            pass
            
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
            WHERE subscribed = 1 AND banned = 0
            ORDER BY last_seen DESC
        """)
        return cur.fetchall()
    except Exception as e:
        logger.error(f"Failed to fetch subscribed users: {e}")
        return []
    finally:
        conn.close()

def ban_user(user_id: int) -> None:
    """Ban a user by ID."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to ban user {user_id}: {e}")
    finally:
        conn.close()

def unban_user(user_id: int) -> None:
    """Unban a user by ID."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to unban user {user_id}: {e}")
    finally:
        conn.close()

def is_user_banned(user_id: int) -> bool:
    """Check if user is banned."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return bool(row[0]) if row else False
    except Exception as e:
        logger.error(f"Failed to check ban status for {user_id}: {e}")
        return False
    finally:
        conn.close()

def get_all_users() -> List[Tuple[int, str, str, str, int, int, str]]:
    """Retrieve all users including banned ones."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, username, first_name, last_name, subscribed, banned, last_seen 
            FROM users 
            ORDER BY last_seen DESC
        """)
        return cur.fetchall()
    except Exception as e:
        logger.error(f"Failed to fetch all users: {e}")
        return []
    finally:
        conn.close()

def search_user(query: str) -> Optional[Tuple[int, str, str, str, int, int, str]]:
    """Search for a user by ID or Username (case-insensitive)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        # Try ID search first
        try:
            user_id = int(query)
            cur.execute("""
                SELECT user_id, username, first_name, last_name, subscribed, banned, last_seen 
                FROM users WHERE user_id = ?
            """, (user_id,))
            res = cur.fetchone()
            if res:
                return res
        except ValueError:
            pass

        # Try Username search (removing @ prefix if present)
        clean_query = query.lstrip('@').lower()
        cur.execute("""
            SELECT user_id, username, first_name, last_name, subscribed, banned, last_seen 
            FROM users WHERE LOWER(username) = ?
        """, (clean_query,))
        return cur.fetchone()
    except Exception as e:
        logger.error(f"Failed to search user: {e}")
        return None
    finally:
        conn.close()

# Initialize DB on import
init_db()
