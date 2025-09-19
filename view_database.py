#!/usr/bin/env python3
"""
View contents of the deadlines.db SQLite database
"""

import sqlite3

def view_database(db_path='deadlines.db'):
    """Display all tables and their contents from the database."""

    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print("No tables found in the database.")
            return

        print(f"Database: {db_path}")
        print("=" * 80)

        # Display each table
        for table in tables:
            table_name = table[0]
            print(f"\nTable: {table_name}")
            print("-" * 60)

            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            print("\nColumns:")
            col_names = []
            for col in columns:
                col_names.append(col[1])
                print(f"  - {col[1]} ({col[2]})")

            # Get table data
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()

            print(f"\nData ({len(rows)} rows):")
            if len(rows) > 0:
                # Print header
                header = " | ".join([f"{name:15}" for name in col_names])
                print(f"\n{header}")
                print("-" * len(header))

                # Print rows
                for row in rows:
                    row_str = " | ".join([f"{str(val)[:15]:15}" for val in row])
                    print(row_str)
            else:
                print("  (empty table)")

        # Also show some sample queries
        print("\n" + "=" * 80)
        print("Sample Queries:")
        print("-" * 60)

        # Try to get some sample data if there's a deadlines table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%deadline%';")
        deadline_tables = cursor.fetchall()

        if deadline_tables:
            for table in deadline_tables:
                table_name = table[0]
                print(f"\nFirst 5 rows from {table_name}:")
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                rows = cursor.fetchall()
                for row in rows:
                    print(f"  {row}")

        conn.close()
        print("\nDatabase viewing complete!")

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    view_database()