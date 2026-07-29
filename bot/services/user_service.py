import sqlite3
import psycopg2
import os
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

DB_PATH = "data/bot_state.db"
DATABASE_URL = os.environ.get("DATABASE_URL")
PLACEHOLDER = "%s" if DATABASE_URL else "?"

if DATABASE_URL:
    logger.info("DATABASE_URL is SET — will use Supabase PostgreSQL for user storage.")
else:
    logger.warning("DATABASE_URL is NOT SET — falling back to local SQLite (data will be lost on redeploy!).")

def get_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    else:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        return sqlite3.connect(DB_PATH)

def _format_row(row: Optional[tuple]) -> Optional[tuple]:
    """Format row to ensure datetime objects are formatted as string for UI compatibility."""
    if not row:
        return row
    return tuple(
        val.strftime("%Y-%m-%d %H:%M:%S") if isinstance(val, datetime) else val
        for val in row
    )

def init_db():
    """Initialize the database (PostgreSQL or SQLite) and create tables."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if DATABASE_URL:
            logger.info("Connecting to Supabase PostgreSQL database...")
            # PostgreSQL: user_id must be BIGINT to handle large Telegram IDs
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    subscribed SMALLINT DEFAULT 0,
                    banned SMALLINT DEFAULT 0,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            logger.info("Connecting to local SQLite database (DATABASE_URL not set)...")
            # SQLite
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
            # Migration: Add banned column if it doesn't exist for SQLite
            try:
                cur.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
                
        conn.commit()
        logger.info("Bot state database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize bot_state DB: {e}")
    finally:
        conn.close()

def register_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> None:
    """Save or update user in database."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            INSERT INTO users (user_id, username, first_name, last_name, last_seen)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                last_seen = CURRENT_TIMESTAMP
        """
        cur.execute(query.replace("?", PLACEHOLDER), (user_id, username, first_name, last_name))
        conn.commit()
        db_type = "PostgreSQL" if DATABASE_URL else "SQLite"
        logger.info(f"User saved to {db_type}: id={user_id}, name={first_name} {last_name}, username=@{username}")
    except Exception as e:
        logger.error(f"Failed to register user {user_id}: {e}", exc_info=True)
    finally:
        conn.close()

def set_subscription_status(user_id: int, subscribed: bool) -> None:
    """Update user's subscription status."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            UPDATE users 
            SET subscribed = ? 
            WHERE user_id = ?
        """
        cur.execute(query.replace("?", PLACEHOLDER), (1 if subscribed else 0, user_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to update subscription status for {user_id}: {e}")
    finally:
        conn.close()

def get_subscribed_users() -> List[Tuple[int, str, str, str, str]]:
    """Retrieve all users marked as subscribed."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, username, first_name, last_name, last_seen 
            FROM users 
            WHERE subscribed = 1 AND banned = 0
            ORDER BY last_seen DESC
        """)
        return [_format_row(row) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Failed to fetch subscribed users: {e}")
        return []
    finally:
        conn.close()

def ban_user(user_id: int) -> None:
    """Ban a user by ID."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "UPDATE users SET banned = 1 WHERE user_id = ?"
        cur.execute(query.replace("?", PLACEHOLDER), (user_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to ban user {user_id}: {e}")
    finally:
        conn.close()

def unban_user(user_id: int) -> None:
    """Unban a user by ID."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "UPDATE users SET banned = 0 WHERE user_id = ?"
        cur.execute(query.replace("?", PLACEHOLDER), (user_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to unban user {user_id}: {e}")
    finally:
        conn.close()

def is_user_banned(user_id: int) -> bool:
    """Check if user is banned."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "SELECT banned FROM users WHERE user_id = ?"
        cur.execute(query.replace("?", PLACEHOLDER), (user_id,))
        row = cur.fetchone()
        return bool(row[0]) if row else False
    except Exception as e:
        logger.error(f"Failed to check ban status for {user_id}: {e}")
        return False
    finally:
        conn.close()

def get_all_users() -> List[Tuple[int, str, str, str, int, int, str]]:
    """Retrieve all users including banned ones."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, username, first_name, last_name, subscribed, banned, last_seen 
            FROM users 
            ORDER BY last_seen DESC
        """)
        return [_format_row(row) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Failed to fetch all users: {e}")
        return []
    finally:
        conn.close()

def search_user(query: str) -> Optional[Tuple[int, str, str, str, int, int, str]]:
    """Search for a user by ID or Username (case-insensitive)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Try ID search first
        try:
            user_id = int(query)
            q = """
                SELECT user_id, username, first_name, last_name, subscribed, banned, last_seen 
                FROM users WHERE user_id = ?
            """
            cur.execute(q.replace("?", PLACEHOLDER), (user_id,))
            res = cur.fetchone()
            if res:
                return _format_row(res)
        except ValueError:
            pass

        # Try Username search (removing @ prefix if present)
        clean_query = query.lstrip('@').lower()
        q = """
            SELECT user_id, username, first_name, last_name, subscribed, banned, last_seen 
            FROM users WHERE LOWER(username) = ?
        """
        cur.execute(q.replace("?", PLACEHOLDER), (clean_query,))
        res = cur.fetchone()
        return _format_row(res)
    except Exception as e:
        logger.error(f"Failed to search user: {e}")
        return None
    finally:
        conn.close()

# Initialize DB on import
init_db()
