"""Sets a new password for an existing local account (passwords are hashed, so
they can't be recovered, only replaced).

Usage:  python scripts/reset_password.py            # local accounts (users.db)
        python scripts/reset_password.py --demo     # public-demo accounts (demo_users.db)
"""
import os
import re
import sys
import sqlite3
import getpass

from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    db = os.path.join(ROOT, "demo_users.db" if "--demo" in sys.argv else "users.db")
    if not os.path.exists(db):
        sys.exit(f"No account database found at {db}")

    with sqlite3.connect(db) as conn:
        users = [r[0] for r in conn.execute("SELECT username FROM users ORDER BY id")]
        if not users:
            sys.exit("There are no accounts yet. Register one in the app.")
        print("Accounts:", ", ".join(users))

        username = input("Username to reset: ").strip()
        row = conn.execute("SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        if not row:
            sys.exit(f"No account named '{username}'.")

        # Same rules as registration: 8+ characters with letters and numbers
        while True:
            password = getpass.getpass("New password (hidden while typing): ")
            if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
                print("Use at least 8 characters, with both letters and numbers.")
                continue
            if getpass.getpass("Type it again: ") != password:
                print("They didn't match, try again.")
                continue
            break

        conn.execute("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(password), row[0]))
        conn.commit()
    print(f"Password updated for '{username}'. You can log in now.")


if __name__ == "__main__":
    main()
