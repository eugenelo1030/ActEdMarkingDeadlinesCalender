# deadlines_to_ics.py
"""
Script to convert a TSV deadlines file to multiple .ics calendar files for each module group.
Now supports both static file generation and database import for subscription calendars.

Usage:
    python deadlines_to_ics.py <input_tsv_path>                    # Generate static ICS files
    python deadlines_to_ics.py <input_tsv_path> --to-database      # Import to database for subscriptions
    python deadlines_to_ics.py --start-server                      # Start subscription server
"""
import sys
import csv
import os
from datetime import datetime
from ics import Calendar, Event


def parse_date(date_str):
    # Handles dates in format DD/MM/YYYY
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except Exception:
        return None


def generate_static_files(input_path):
    """Generate static ICS files (original functionality)."""
    # Mapping of module code to output file name
    module_files = {
        'CM1': 'CM1 Assignment Deadlines September 2026.ics',
        'CM2': 'CM2 Assignment Deadlines September 2026.ics',
        'CS1': 'CS1 Assignment Deadlines September 2026.ics',
        'CS2': 'CS2 Assignment Deadlines September 2026.ics',
        'CB': 'CB Assignment Deadlines September 2026.ics',
        'CP1': 'CP1 Assignment Deadlines September 2026.ics',
        'CP2': 'CP2 Assignment Deadlines September 2026.ics',
        'CP3': 'CP3 Assignment Deadlines September 2026.ics',
        'SP': 'SP Assignment Deadlines September 2026.ics',
        'SA': 'SA Assignment Deadlines September 2026.ics',
    }

    # Create a calendar for each module
    calendars = {key: Calendar() for key in module_files}

    with open(input_path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 4:
                continue
            module, code, reccomend_date_str, deadline_date_str = row[:4]
            start = parse_date(deadline_date_str)
            if not start:
                continue
            # Find the module group (e.g., CM1, CM2, etc.)
            for mod_key in module_files:
                if module.strip().upper().startswith(mod_key):
                    event = Event()
                    event.name = f"{module} {code} deadline"
                    event.begin = start
                    event.end = start
                    calendars[mod_key].events.add(event)
                    break

    # Write each calendar to its respective file
    for mod_key, cal in calendars.items():
        if cal.events:
            with open(module_files[mod_key], "w", encoding="utf-8") as f:
                f.write(cal.serialize())
            print(f"ICS file written to {module_files[mod_key]}")


def import_to_database(input_path, db_path="deadlines.db"):
    """Import TSV data to database for subscription calendars."""
    try:
        from calendar_server import DeadlineDatabase

        db = DeadlineDatabase(db_path)
        db.import_from_tsv(input_path)
        print(f"Successfully imported {input_path} to database {db_path}")
        print("You can now start the calendar server with: python calendar_server.py")

    except ImportError:
        print("Error: calendar_server.py not found. Make sure it's in the same directory.")
        sys.exit(1)


def start_server():
    """Start the calendar subscription server."""
    try:
        from calendar_server import main as server_main
        server_main()
    except ImportError:
        print("Error: calendar_server.py not found. Make sure it's in the same directory.")
        sys.exit(1)


def main():
    """Main function with enhanced command line options."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if "--start-server" in sys.argv:
        start_server()
        return

    input_path = sys.argv[1]

    if not os.path.exists(input_path):
        print(f"Error: File {input_path} not found")
        sys.exit(1)

    if "--to-database" in sys.argv:
        # Import to database for subscription calendars
        import_to_database(input_path)
    else:
        # Generate static ICS files (original functionality)
        generate_static_files(input_path)


if __name__ == "__main__":
    main()
