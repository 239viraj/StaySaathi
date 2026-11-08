
import os
import sqlite3
import shutil
from datetime import datetime

DB_PATH = os.path.join("instance", "pg_finder.db")

if not os.path.exists(DB_PATH):
    raise FileNotFoundError(f"Database not found: {DB_PATH}")

# Create a fresh backup before modifying the database.
backup_path = (
    DB_PATH + "." + datetime.now().strftime("%Y%m%d_%H%M%S") + ".bak"
)
shutil.copy2(DB_PATH, backup_path)
print(f"Backup created: {backup_path}")

conn = sqlite3.connect(DB_PATH)

try:
    # Foreign keys must be disabled before starting the transaction
    # when rebuilding a referenced SQLite table.
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN IMMEDIATE")

    # Verify the expected schema.
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info('user')")
    }

    expected_columns = {
        "id",
        "name",
        "email",
        "phone",
        "password",
        "role",
        "verification_status",
    }

    if columns != expected_columns:
        raise RuntimeError(
            f"Unexpected user-table columns: {sorted(columns)}"
        )

    # Check that the original global unique constraints exist.
    unique_indexes = conn.execute(
        "PRAGMA index_list('user')"
    ).fetchall()

    unique_column_sets = []

    for index in unique_indexes:
        if index[2]:
            index_name = index[1]
            index_columns = tuple(
                row[2]
                for row in conn.execute(
                    f'PRAGMA index_info("{index_name}")'
                )
            )
            unique_column_sets.append(index_columns)

    if ("email",) not in unique_column_sets:
        raise RuntimeError("Global email uniqueness was not found.")

    if ("phone",) not in unique_column_sets:
        raise RuntimeError("Global phone uniqueness was not found.")

    # Check duplicates within each role.
    duplicate_emails = conn.execute("""
        SELECT lower(email), role, COUNT(*)
        FROM user
        GROUP BY lower(email), role
        HAVING COUNT(*) > 1
    """).fetchall()

    duplicate_phones = conn.execute("""
        SELECT phone, role, COUNT(*)
        FROM user
        GROUP BY phone, role
        HAVING COUNT(*) > 1
    """).fetchall()

    if duplicate_emails or duplicate_phones:
        raise RuntimeError(
            "Duplicate emails or phone numbers within a role exist."
        )

    # Preserve all current user records and IDs.
    conn.execute("""
        CREATE TABLE user_new (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(120) NOT NULL,
            phone VARCHAR(15) NOT NULL,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL,
            verification_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            CONSTRAINT unique_email_per_role UNIQUE (email, role),
            CONSTRAINT unique_phone_per_role UNIQUE (phone, role)
        )
    """)

    conn.execute("""
        INSERT INTO user_new (
            id, name, email, phone, password, role, verification_status
        )
        SELECT
            id, name, email, phone, password, role, verification_status
        FROM user
    """)

    conn.execute("DROP TABLE user")
    conn.execute("ALTER TABLE user_new RENAME TO user")

    # Check all foreign-key relationships before committing.
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()

    if violations:
        raise RuntimeError(
            f"Foreign-key violations detected: {violations}"
        )

    conn.commit()
    print("Migration completed successfully.")

except Exception as exc:
    conn.rollback()
    print(f"Migration failed; changes rolled back: {exc}")
    raise

finally:
    conn.close()

print("User IDs and related records have been preserved.")
print(f"Backup available at: {backup_path}")

