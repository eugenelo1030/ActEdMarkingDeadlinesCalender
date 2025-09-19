#!/usr/bin/env python3
"""
Simple HTTP server to serve dynamic ICS calendar subscriptions.
Serves calendars that auto-update when deadline data changes.
"""

import os
import sys
import json
import sqlite3
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from ics import Calendar, Event
import threading
import time

class DeadlineDatabase:
    """Simple SQLite database for storing deadlines."""

    def __init__(self, db_path="deadlines.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize the SQLite database with deadlines table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_code TEXT NOT NULL,
                module_group TEXT NOT NULL,
                assignment_code TEXT NOT NULL,
                title TEXT,
                recommend_date TEXT,
                deadline_date TEXT NOT NULL,
                academic_year TEXT DEFAULT '2026',
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(module_code, assignment_code, academic_year)
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_module_group_deadline
            ON deadlines(module_group, deadline_date)
        ''')

        conn.commit()
        conn.close()

    def import_from_tsv(self, tsv_path):
        """Import deadlines from TSV file."""
        import csv

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Clear existing data
        cursor.execute("DELETE FROM deadlines")

        module_groups = {
            'CM1': 'CM1', 'CM2': 'CM2', 'CS1': 'CS1', 'CS2': 'CS2',
            'CB': 'CB', 'CP1': 'CP1', 'CP2': 'CP2', 'CP3': 'CP3',
            'SP': 'SP', 'SA': 'SA'
        }

        with open(tsv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\t')
            for row in reader:
                if len(row) < 4:
                    continue

                module, code, recommend_date_str, deadline_date_str = row[:4]

                # Find module group
                module_group = None
                for group_key in module_groups:
                    if module.strip().upper().startswith(group_key):
                        module_group = group_key
                        break

                if not module_group:
                    continue

                # Parse dates
                try:
                    deadline_date = datetime.strptime(deadline_date_str.strip(), "%d/%m/%Y").date()
                    recommend_date = None
                    if recommend_date_str.strip():
                        recommend_date = datetime.strptime(recommend_date_str.strip(), "%d/%m/%Y").date()
                except:
                    continue

                cursor.execute('''
                    INSERT OR REPLACE INTO deadlines
                    (module_code, module_group, assignment_code, title, recommend_date, deadline_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    module.strip(),
                    module_group,
                    code.strip(),
                    f"{module.strip()} {code.strip()}",
                    recommend_date.isoformat() if recommend_date else None,
                    deadline_date.isoformat()
                ))

        conn.commit()
        conn.close()
        print(f"Imported deadlines from {tsv_path}")

    def get_deadlines_by_group(self, module_group=None):
        """Get deadlines filtered by module group."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if module_group:
            cursor.execute('''
                SELECT module_code, assignment_code, title, deadline_date, recommend_date
                FROM deadlines
                WHERE module_group = ? AND is_active = 1
                ORDER BY deadline_date, module_code
            ''', (module_group.upper(),))
        else:
            cursor.execute('''
                SELECT module_code, assignment_code, title, deadline_date, recommend_date
                FROM deadlines
                WHERE is_active = 1
                ORDER BY module_group, deadline_date, module_code
            ''')

        deadlines = cursor.fetchall()
        conn.close()
        return deadlines

    def get_module_groups(self):
        """Get all available module groups."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT DISTINCT module_group
            FROM deadlines
            WHERE is_active = 1
            ORDER BY module_group
        ''')

        groups = [row[0] for row in cursor.fetchall()]
        conn.close()
        return groups


class CalendarHandler(BaseHTTPRequestHandler):
    """HTTP request handler for calendar subscription endpoints."""

    def __init__(self, *args, db_instance=None, **kwargs):
        self.db = db_instance
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET requests for calendar subscriptions."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query_params = parse_qs(parsed_path.query)

        if path == '/':
            self.serve_index()
        elif path.startswith('/calendar/'):
            self.serve_calendar(path, query_params)
        elif path == '/api/groups':
            self.serve_groups()
        else:
            self.send_error(404, "Calendar not found")

    def serve_index(self):
        """Serve a simple index page with available calendars."""
        groups = self.db.get_module_groups()

        html = '''<!DOCTYPE html>
<html>
<head>
    <title>Assignment Deadlines Calendar Subscription</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .calendar-link { margin: 10px 0; padding: 10px; background: #f5f5f5; border-radius: 5px; }
        .calendar-link a { text-decoration: none; color: #0066cc; font-weight: bold; }
        .calendar-link .url { font-family: monospace; color: #666; font-size: 0.9em; }
        .instructions { background: #e8f4f8; padding: 20px; border-radius: 5px; margin: 20px 0; }
    </style>
</head>
<body>
    <h1>Assignment Deadlines Calendar Subscription</h1>

    <div class="instructions">
        <h3>Two Options Available:</h3>

        <h4>🔄 Auto-Updating Subscription (Recommended)</h4>
        <ol>
            <li>Copy the subscription URL below</li>
            <li>In your calendar app, choose "Add Calendar" → "From URL" (not "Import")</li>
            <li>Paste the URL</li>
            <li>Calendar automatically updates when deadlines change</li>
        </ol>

        <h4>📥 One-Time Download</h4>
        <ol>
            <li>Right-click any calendar link below → "Save Link As"</li>
            <li>Import the downloaded .ics file into your calendar app</li>
            <li>⚠️ No automatic updates - you'll need to re-import if deadlines change</li>
        </ol>
    </div>

    <h2>Available Calendars:</h2>
'''

        # Add individual module group calendars
        for group in groups:
            group_name = {
                'CM1': 'CM1 Assignment Deadlines September 2026',
                'CM2': 'CM2 Assignment Deadlines September 2026',
                'CS1': 'CS1 Assignment Deadlines September 2026',
                'CS2': 'CS2 Assignment Deadlines September 2026',
                'CB': 'CB Assignment Deadlines September 2026',
                'CP1': 'CP1 Assignment Deadlines September 2026',
                'CP2': 'CP2 Assignment Deadlines September 2026',
                'CP3': 'CP3 Assignment Deadlines September 2026',
                'SP': 'SP Assignment Deadlines September 2026',
                'SA': 'SA Assignment Deadlines September 2026'
            }.get(group, f"{group} Assignment Deadlines September 2026")

            # Use environment variable for URL or detect from request
            if 'RAILWAY_STATIC_URL' in os.environ:
                base_url = f"https://{os.environ['RAILWAY_STATIC_URL']}"
            else:
                host_header = self.headers.get('Host', 'localhost:8080')
                base_url = f"https://{host_header}" if host_header != 'localhost:8080' else f"http://{host_header}"
            calendar_url = f"{base_url}/calendar/{group.lower()}.ics"

            html += f'''
    <div class="calendar-link">
        <a href="{calendar_url}">{group_name}</a><br>
        <span class="url">https://{calendar_url}</span>
    </div>'''

        # Add combined calendar
        all_calendar_url = f"{base_url}/calendar/all.ics"
        html += f'''
    <div class="calendar-link">
        <a href="{all_calendar_url}">ALL - All Assignment Deadlines</a><br>
        <span class="url">{all_calendar_url}</span>
    </div>'''

        html += '''
    <h2>Manual Download:</h2>
    <p>You can also download static ICS files by clicking the links above.</p>

    <h2>Update Data:</h2>
    <p>To update deadline data, use: <code>python calendar_server.py --import your_file.tsv</code></p>
</body>
</html>'''

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_calendar(self, path, query_params):
        """Serve ICS calendar file."""
        # Extract module group from path
        filename = path.split('/')[-1]
        if filename == 'all.ics':
            module_group = None
            calendar_name = "All Assignment Deadlines September 2026"
        else:
            module_group = filename.replace('.ics', '').upper()
            calendar_name = f"{module_group} Assignment Deadlines September 2026"

        # Generate calendar
        calendar = self.generate_calendar(module_group, calendar_name)

        # Serve as ICS file
        self.send_response(200)
        self.send_header('Content-Type', 'text/calendar; charset=utf-8')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        # Important headers for calendar subscription
        self.send_header('Cache-Control', 'no-cache, must-revalidate')
        self.send_header('Expires', 'Thu, 01 Jan 1970 00:00:00 GMT')
        self.end_headers()

        self.wfile.write(calendar.serialize().encode('utf-8'))

    def serve_groups(self):
        """Serve available module groups as JSON."""
        groups = self.db.get_module_groups()

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        response = {'groups': groups}
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def generate_calendar(self, module_group, calendar_name):
        """Generate ICS calendar for the specified module group."""
        calendar = Calendar()
        calendar.creator = f"Assignment Deadlines Calendar - {calendar_name}"

        # Get deadlines from database
        deadlines = self.db.get_deadlines_by_group(module_group)

        for module_code, assignment_code, title, deadline_date_str, recommend_date_str in deadlines:
            # Parse deadline date
            deadline_date = datetime.strptime(deadline_date_str, "%Y-%m-%d").date()

            # Create calendar event
            event = Event()
            event.name = f"{module_code} {assignment_code} deadline"
            event.begin = deadline_date
            event.end = deadline_date
            event.description = f"Assignment deadline for {module_code} {assignment_code}"

            # Add location/category
            event.categories = [module_group] if module_group else ["Assignment"]

            # Add unique ID for the event (important for updates)
            event.uid = f"{module_code}-{assignment_code}-{deadline_date_str}@deadlines-calendar"

            calendar.events.add(event)

        return calendar

    def log_message(self, format, *args):
        """Override to customize logging."""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {format % args}")


def create_handler_with_db(db_instance):
    """Create handler class with database instance."""
    def handler(*args, **kwargs):
        return CalendarHandler(*args, db_instance=db_instance, **kwargs)
    return handler


def main():
    """Main server function."""
    import argparse

    parser = argparse.ArgumentParser(description='Assignment Deadlines Calendar Server')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8080)), help='Server port (default: 8080)')
    parser.add_argument('--host', default=os.environ.get('HOST', 'localhost'), help='Server host (default: localhost)')
    parser.add_argument('--import', dest='import_file', help='Import deadlines from TSV file')
    parser.add_argument('--db', default='deadlines.db', help='Database file path (default: deadlines.db)')

    args = parser.parse_args()

    # Initialize database
    db = DeadlineDatabase(args.db)

    # Import data if specified
    if args.import_file:
        if os.path.exists(args.import_file):
            db.import_from_tsv(args.import_file)
            print(f"Data imported from {args.import_file}")
        else:
            print(f"Error: File {args.import_file} not found")
            return

    # Create and start server
    handler_class = create_handler_with_db(db)
    server = HTTPServer((args.host, args.port), handler_class)

    print(f"Starting calendar server on http://{args.host}:{args.port}")
    print(f"Calendar subscriptions available at:")
    print(f"  - http://{args.host}:{args.port}/calendar/cm1.ics")
    print(f"  - http://{args.host}:{args.port}/calendar/cm2.ics")
    print(f"  - http://{args.host}:{args.port}/calendar/all.ics")
    print(f"  - etc...")
    print(f"\nVisit http://{args.host}:{args.port} for the full list")
    print(f"Press Ctrl+C to stop the server")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()


if __name__ == '__main__':
    main()