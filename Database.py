import sqlite3
import hashlib
import os

DB_NAME = "game_accounts.db"


def _connect():
    return sqlite3.connect(DB_NAME, timeout=10)


def _execute(sql, params=()):
    """Run one SQL statement. Returns (rows, rowcount)."""
    conn = _connect()
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        conn.commit()
        return rows, cur.rowcount
    finally:
        conn.close()


def create_database():
    conn = _connect()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL
        )
    """)

    # status is 'pending' or 'accepted'
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friend_requests (
            from_user TEXT NOT NULL,
            to_user TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            PRIMARY KEY (from_user, to_user)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player1 TEXT NOT NULL,
            player2 TEXT NOT NULL,
            played_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000
    ).hex()


def create_account(username, password):
    username = username.strip()

    if len(username) < 3:
        return False, "Username must contain at least 3 characters."

    if len(password) < 6:
        return False, "Password must contain at least 6 characters."

    salt = os.urandom(16).hex()
    password_hash = hash_password(password, salt)

    try:
        _execute(
            "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
            (username, password_hash, salt)
        )
        return True, "Account created successfully!"

    except sqlite3.IntegrityError:
        return False, "This username already exists."


def login_account(username, password):
    rows, _ = _execute(
        "SELECT password_hash, salt FROM users WHERE username = ?",
        (username.strip(),)
    )

    if not rows:
        return False

    saved_hash, salt = rows[0]
    return hash_password(password, salt) == saved_hash


# ---------------------------------------------------------------- friends

def user_exists(username):
    rows, _ = _execute(
        "SELECT 1 FROM users WHERE username = ?", (username,)
    )
    return bool(rows)


def are_friends(a, b):
    rows, _ = _execute(
        """SELECT 1 FROM friend_requests
           WHERE status = 'accepted'
             AND ((from_user = ? AND to_user = ?)
               OR (from_user = ? AND to_user = ?))""",
        (a, b, b, a)
    )
    return bool(rows)


def send_friend_request(sender, receiver):
    receiver = receiver.strip()

    if not receiver:
        return False, "Type a username first."
    if receiver == sender:
        return False, "You cannot add yourself."
    if not user_exists(receiver):
        return False, "User not found."
    if are_friends(sender, receiver):
        return False, "You are already friends."

    # If they already sent us a request, just accept it.
    rows, _ = _execute(
        "SELECT status FROM friend_requests WHERE from_user = ? AND to_user = ?",
        (receiver, sender)
    )
    if rows and rows[0][0] == "pending":
        _execute(
            """UPDATE friend_requests SET status = 'accepted'
               WHERE from_user = ? AND to_user = ?""",
            (receiver, sender)
        )
        return True, f"You and {receiver} are now friends!"

    rows, _ = _execute(
        "SELECT status FROM friend_requests WHERE from_user = ? AND to_user = ?",
        (sender, receiver)
    )
    if rows and rows[0][0] == "pending":
        return False, "Request already sent."

    _execute(
        """INSERT OR REPLACE INTO friend_requests (from_user, to_user, status)
           VALUES (?, ?, 'pending')""",
        (sender, receiver)
    )
    return True, f"Friend request sent to {receiver}."


def accept_friend_request(user, from_user):
    _, count = _execute(
        """UPDATE friend_requests SET status = 'accepted'
           WHERE from_user = ? AND to_user = ? AND status = 'pending'""",
        (from_user, user)
    )
    if count:
        return True, f"You and {from_user} are now friends!"
    return False, "Request not found."


def reject_friend_request(user, from_user):
    _, count = _execute(
        """DELETE FROM friend_requests
           WHERE from_user = ? AND to_user = ? AND status = 'pending'""",
        (from_user, user)
    )
    if count:
        return True, "Request rejected."
    return False, "Request not found."


def get_friends(user):
    rows, _ = _execute(
        """SELECT to_user FROM friend_requests
           WHERE from_user = ? AND status = 'accepted'
           UNION
           SELECT from_user FROM friend_requests
           WHERE to_user = ? AND status = 'accepted'""",
        (user, user)
    )
    return sorted(r[0] for r in rows)


def get_pending_requests(user):
    rows, _ = _execute(
        """SELECT from_user FROM friend_requests
           WHERE to_user = ? AND status = 'pending'""",
        (user,)
    )
    return sorted(r[0] for r in rows)


# ---------------------------------------------------------------- matches

def record_match(player1, player2):
    _execute(
        "INSERT INTO matches (player1, player2) VALUES (?, ?)",
        (player1, player2)
    )


def get_suggestions(user, limit=6):
    """
    Suggested friends: people you recently played against first,
    then other registered players. Friends and pending requests are skipped.
    """
    excluded = set(get_friends(user))
    excluded.add(user)

    rows, _ = _execute(
        """SELECT from_user, to_user FROM friend_requests
           WHERE status = 'pending' AND (from_user = ? OR to_user = ?)""",
        (user, user)
    )
    for a, b in rows:
        excluded.add(a)
        excluded.add(b)

    suggestions = []

    rows, _ = _execute(
        """SELECT opp FROM (
               SELECT CASE WHEN player1 = ? THEN player2 ELSE player1 END AS opp,
                      MAX(id) AS last_id
               FROM matches
               WHERE player1 = ? OR player2 = ?
               GROUP BY opp
           ) ORDER BY last_id DESC""",
        (user, user, user)
    )
    for (name,) in rows:
        if name not in excluded and name not in suggestions:
            suggestions.append(name)

    if len(suggestions) < limit:
        rows, _ = _execute("SELECT username FROM users ORDER BY RANDOM()")
        for (name,) in rows:
            if name not in excluded and name not in suggestions:
                suggestions.append(name)
            if len(suggestions) >= limit:
                break

    return suggestions[:limit]


create_database()