# deadlines_to_ics.py
"""
Script to convert a TSV deadlines file to multiple .ics calendar files for each module group.
Now supports both static file generation and database import for subscription calendars.

Usage:
    python deadlines_to_ics.py <input_tsv_path> --year 2026 --month September    # Generate static ICS files
    python deadlines_to_ics.py <input_tsv_path> --to-database                    # Import to database for subscriptions
    python deadlines_to_ics.py --start-server                                    # Start subscription server

Parameters:
    --year YYYY     Four-digit year (e.g., 2026)
    --month NAME    Full month name (e.g., September, October, November)
"""
import sys
import csv
import os
import argparse
from datetime import datetime
from ics import Calendar, Event
from ics.grammar.parse import ContentLine


def parse_date(date_str):
    # Handles dates in format DD/MM/YYYY
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except Exception:
        return None


def generate_static_files(input_path, year=2026, month='September'):
    """Generate static ICS files with configurable year and month."""
    # Mapping of module code to output file name
    module_files = {
        'CM1': f'CM1 Assignment Deadlines {month} {year}.ics',
        'CM2': f'CM2 Assignment Deadlines {month} {year}.ics',
        'CS1': f'CS1 Assignment Deadlines {month} {year}.ics',
        'CS2': f'CS2 Assignment Deadlines {month} {year}.ics',
        'CB': f'CB Assignment Deadlines {month} {year}.ics',
        'CP1': f'CP1 Assignment Deadlines {month} {year}.ics',
        'CP2': f'CP2 Assignment Deadlines {month} {year}.ics',
        'CP3': f'CP3 Assignment Deadlines {month} {year}.ics',
        'SP': f'SP Assignment Deadlines {month} {year}.ics',
        'SA': f'SA Assignment Deadlines {month} {year}.ics',
    }

    # Mapping of module code to calendar display names
    module_names = {
        'CM1': 'CM1 Assignment Deadlines',
        'CM2': 'CM2 Assignment Deadlines',
        'CS1': 'CS1 Assignment Deadlines',
        'CS2': 'CS2 Assignment Deadlines',
        'CB': 'CB Assignment Deadlines',
        'CP1': 'CP1 Assignment Deadlines',
        'CP2': 'CP2 Assignment Deadlines',
        'CP3': 'CP3 Assignment Deadlines',
        'SP': 'SP Assignment Deadlines',
        'SA': 'SA Assignment Deadlines',
    }

    # Create a calendar for each module with proper name
    calendars = {}
    for key in module_files:
        cal = Calendar()
        # Set calendar name and display name properties using ContentLine
        cal.extra.append(ContentLine('X-WR-CALNAME', value=module_names[key]))
        cal.extra.append(ContentLine('X-WR-CALDESC', value=f'ActEd {module_names[key]} - {month} {year}'))
        cal.extra.append(ContentLine('NAME', value=module_names[key]))
        calendars[key] = cal

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
        # Pass empty args to server_main to use its defaults
        sys.argv = ['calendar_server.py']  # Reset argv to avoid passing --start-server
        server_main()
    except ImportError:
        print("Error: calendar_server.py not found. Make sure it's in the same directory.")
        sys.exit(1)


def main():
    """Main function with enhanced command line options."""
    parser = argparse.ArgumentParser(description='Convert TSV deadlines to ICS calendar files')
    parser.add_argument('input_path', nargs='?', help='Path to input TSV file')
    parser.add_argument('--year', type=int, help='Four-digit year (e.g., 2026)')
    parser.add_argument('--month', type=str, help='Full month name (e.g., September)')
    parser.add_argument('--to-database', action='store_true', help='Import to database for subscriptions')
    parser.add_argument('--start-server', action='store_true', help='Start subscription server')

    args = parser.parse_args()

    # Handle server start first (doesn't need input file)
    if args.start_server:
        start_server()
        return

    # Check for input path
    if not args.input_path:
        print(__doc__)
        sys.exit(1)

    if not os.path.exists(args.input_path):
        print(f"Error: File {args.input_path} not found")
        sys.exit(1)

    # Validate month name if provided
    valid_months = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    if args.to_database:
        # Import to database for subscription calendars
        import_to_database(args.input_path)
        # After importing to database, optionally start server
        if args.start_server:
            print("\nStarting calendar server...")
            start_server()
    else:
        # Generate static ICS files
        year = args.year if args.year else 2026
        month = args.month if args.month else 'September'

        # Validate year
        if year < 1900 or year > 3000:
            print(f"Error: Year must be between 1900 and 3000")
            sys.exit(1)

        # Validate month
        if month not in valid_months:
            print(f"Error: Month must be one of: {', '.join(valid_months)}")
            sys.exit(1)

        generate_static_files(args.input_path, year=year, month=month)


if __name__ == "__main__":
    main()
