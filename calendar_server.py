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
from ics.grammar.parse import ContentLine
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
        elif path == '/api/deadlines':
            self.serve_deadlines(query_params)
        elif path == '/favicon.ico':
            # Return empty favicon to avoid 404 errors
            self.send_response(204)  # No Content
            self.end_headers()
        else:
            self.send_error(404, "Calendar not found")

    def serve_index(self):
        """Serve a simple index page with available calendars."""
        groups = self.db.get_module_groups()

        # Get last update time - try Railway deploy time first, fallback to database last modified time
        last_update = None
        if 'RAILWAY_DEPLOYMENT_ID' in os.environ:
            # Railway provides deployment timestamp
            last_update = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
        else:
            # Fallback to database file modification time
            try:
                db_mtime = os.path.getmtime(self.db.db_path)
                last_update = datetime.fromtimestamp(db_mtime).strftime('%Y-%m-%d %H:%M:%S')
            except:
                last_update = "Unknown"

        html = '''<!DOCTYPE html>
<html>
<head>
    <title>Assignment Deadlines Calendar Subscription</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .last-update {
            background: #e8f4f8;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
            font-size: 0.9em;
            color: #666;
        }
        .calendar-link {
            margin: 10px 0;
            padding: 10px;
            background: #f5f5f5;
            border-radius: 5px;
            position: relative;
        }
        .calendar-link a { text-decoration: none; font-weight: bold; }
        .subscribe-btn {
            display: inline-block;
            background: #28a745;
            color: white;
            padding: 8px 16px;
            border-radius: 5px;
            text-decoration: none;
            font-weight: bold;
            margin-bottom: 10px;
            transition: background 0.3s;
        }
        .subscribe-btn:hover {
            background: #218838;
            color: white;
            text-decoration: none;
        }
        .calendar-link .url-container {
            display: flex;
            align-items: center;
            margin-top: 5px;
            background: white;
            padding: 8px;
            border-radius: 4px;
            border: 1px solid #ddd;
        }
        .calendar-link .url {
            font-family: monospace;
            color: #666;
            font-size: 0.9em;            
            margin-right: 10px;
            word-break: break-all;
        }
        .copy-btn {
            background: #0066cc;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
            white-space: nowrap;
            transition: background 0.3s;
        }
        .copy-btn:hover {
            background: #0052a3;
        }
        .copy-btn.copied {
            background: #28a745;
        }
        .instructions {
            background: #e8f4f8;
            padding: 0;
            border-radius: 5px;
            margin: 20px 0;
        }
        .instructions-header {
            padding: 20px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: space-between;
            user-select: none;
            background: #d4edda;
            border-radius: 5px;
        }
        .instructions-header:hover {
            background: #c3e6cb;
        }
        .instructions-content {
            padding: 20px;
            display: none;
        }
        .instructions.expanded .instructions-content {
            display: block;
        }
        .instructions.expanded .instructions-header {
            border-radius: 5px 5px 0 0;
        }
        .chevron {
            transition: transform 0.3s;
            font-size: 1.2em;
        }
        .instructions.expanded .chevron {
            transform: rotate(90deg);
        }
        .info-icon {
            display: inline-block;
            width: 20px;
            height: 20px;
            background: #0066cc;
            color: white;
            border-radius: 50%;
            text-align: center;
            line-height: 20px;
            cursor: pointer;
            font-size: 12px;
            margin-left: 10px;
            transition: background 0.3s;
        }
        .info-icon:hover {
            background: #0052a3;
        }
        /* Modal Styles */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            overflow: auto;
            background-color: rgba(0,0,0,0.4);
        }
        .modal-content {
            background-color: #fefefe;
            margin: 5% auto;
            padding: 0;
            border: 1px solid #888;
            width: 80%;
            max-width: 700px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .modal-header {
            padding: 20px;
            background: #0066cc;
            color: white;
            border-radius: 8px 8px 0 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-body {
            padding: 20px;
            max-height: 60vh;
            overflow-y: auto;
        }
        .close {
            color: white;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            line-height: 20px;
        }
        .close:hover,
        .close:focus {
            opacity: 0.8;
            text-decoration: none;
        }
        .deadline-item {
            padding: 10px;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .deadline-item:last-child {
            border-bottom: none;
        }
        .deadline-module {
            font-weight: bold;
            color: #0066cc;
        }
        .deadline-date {
            background: #f0f0f0;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.9em;
        }
        .deadline-recommend {
            color: #666;
            font-size: 0.85em;
            margin-top: 4px;
        }
    </style>
    <script>
        function toggleInstructions() {
            const instructions = document.getElementById('instructions-panel');
            instructions.classList.toggle('expanded');
        }

        function showDeadlines(moduleGroup) {
            const modal = document.getElementById('deadlineModal');
            const modalTitle = document.getElementById('modalTitle');
            const modalBody = document.getElementById('modalBody');

            modalTitle.textContent = moduleGroup + ' Assignment Deadlines';
            modalBody.textContent = 'Loading...';
            modal.style.display = 'block';

            // Fetch deadlines from the server
            fetch('/api/deadlines?group=' + moduleGroup)
                .then(response => response.json())
                .then(data => {
                    // Clear modal body safely
                    modalBody.innerHTML = '';

                    if (data.deadlines && data.deadlines.length > 0) {
                        data.deadlines.forEach(deadline => {
                            const deadlineDate = new Date(deadline.deadline_date);
                            const formattedDate = deadlineDate.toLocaleDateString('en-GB', {
                                day: '2-digit',
                                month: 'short',
                                year: 'numeric'
                            });

                            // Create deadline item container
                            const deadlineItem = document.createElement('div');
                            deadlineItem.className = 'deadline-item';

                            // Create left container
                            const leftContainer = document.createElement('div');

                            // Create module info element safely
                            const moduleDiv = document.createElement('div');
                            moduleDiv.className = 'deadline-module';
                            moduleDiv.textContent = deadline.module_code + ' ' + deadline.assignment_code;
                            leftContainer.appendChild(moduleDiv);

                            // Add recommended date if exists
                            if (deadline.recommend_date) {
                                const recommendDate = new Date(deadline.recommend_date);
                                const formattedRecommend = recommendDate.toLocaleDateString('en-GB', {
                                    day: '2-digit',
                                    month: 'short',
                                    year: 'numeric'
                                });

                                const recommendDiv = document.createElement('div');
                                recommendDiv.className = 'deadline-recommend';
                                recommendDiv.textContent = 'Recommended: ' + formattedRecommend;
                                leftContainer.appendChild(recommendDiv);
                            }

                            // Create date element
                            const dateDiv = document.createElement('div');
                            dateDiv.className = 'deadline-date';
                            dateDiv.textContent = formattedDate;

                            // Append all elements
                            deadlineItem.appendChild(leftContainer);
                            deadlineItem.appendChild(dateDiv);
                            modalBody.appendChild(deadlineItem);
                        });
                    } else {
                        const noDeadlinesP = document.createElement('p');
                        noDeadlinesP.textContent = 'No deadlines found for this module group.';
                        modalBody.appendChild(noDeadlinesP);
                    }
                })
                .catch(error => {
                    const errorP = document.createElement('p');
                    errorP.textContent = 'Error loading deadlines. Please try again.';
                    modalBody.innerHTML = '';
                    modalBody.appendChild(errorP);
                    console.error('Error:', error);
                });
        }

        function closeModal() {
            document.getElementById('deadlineModal').style.display = 'none';
        }

        // Close modal when clicking outside of it
        window.onclick = function(event) {
            const modal = document.getElementById('deadlineModal');
            if (event.target == modal) {
                modal.style.display = 'none';
            }
        }

        function copyToClipboard(text, button) {
            // Create a temporary textarea element
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);

            // Select and copy the text
            textarea.select();
            textarea.setSelectionRange(0, 99999); // For mobile devices

            try {
                document.execCommand('copy');
                // Show success feedback
                const originalText = button.innerHTML;
                button.innerHTML = '✓ Copied!';
                button.classList.add('copied');

                // Reset button after 2 seconds
                setTimeout(() => {
                    button.innerHTML = originalText;
                    button.classList.remove('copied');
                }, 2000);
            } catch (err) {
                // Fallback for older browsers
                alert('Press Ctrl+C (or Cmd+C on Mac) to copy');
            }

            // Remove the temporary element
            document.body.removeChild(textarea);
        }
    </script>
</head>
<body>
    <h1>Assignment Deadlines Calendar Subscription</h1>

    <div class="last-update">
        <strong>📅 Last Updated:</strong> ''' + (last_update if last_update else 'Unknown') + '''
    </div>

    <!-- Modal for deadlines -->
    <div id="deadlineModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="modalTitle">Deadlines</h2>
                <span class="close" onclick="closeModal()">&times;</span>
            </div>
            <div class="modal-body" id="modalBody">
                <!-- Deadlines will be loaded here -->
            </div>
        </div>
    </div>

    <div class="instructions expanded" id="instructions-panel">
        <div class="instructions-header" onclick="toggleInstructions()">
            <h2 style="margin: 0;">📅 Calendar Import Instructions</h2>
            <span class="chevron">▶</span>
        </div>
        <div class="instructions-content">

        <div style="background: #d4edda; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
            <strong>✅ Quick Subscribe:</strong> Click the green "Subscribe to Calendar" button below to automatically
            subscribe with your default calendar app. This uses the <code>webcal://</code> protocol for automatic updates.
        </div>

        <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
            <strong>⚠️ Important:</strong> For automatic updates, use "Subscribe" or "Add from URL" (not "Import").
            Importing creates a one-time copy that won't update when deadlines change.
        </div>

        <h3>Microsoft Outlook</h3>
        <details style="margin-bottom: 15px;">
            <summary style="cursor: pointer; font-weight: bold; padding: 10px; background: #f0f0f0; border-radius: 5px;">
                📧 Click to expand Outlook instructions
            </summary>
            <div style="padding: 15px; border-left: 3px solid #0078d4;">
                <h4>Desktop App (Windows/Mac):</h4>
                <ol>
                    <li>Copy the calendar URL below</li>
                    <li>In Outlook, go to File → Account Settings → Account Settings</li>
                    <li>Click the "Internet Calendars" tab</li>
                    <li>Click "New" and paste the URL</li>
                    <li>Give it a name and click OK</li>
                    <li>The calendar will appear in your calendar list</li>
                </ol>

                <h4>Outlook Web (Browser):</h4>
                <ol>
                    <li>Copy the calendar URL below</li>
                    <li>Go to outlook.com and sign in</li>
                    <li>Click the Calendar icon</li>
                    <li>Click "Add calendar" in the left sidebar</li>
                    <li>Choose "Subscribe from web"</li>
                    <li>Paste the URL and give it a name</li>
                    <li>Click "Import"</li>
                </ol>

                <h4>Outlook Mobile App:</h4>
                <ol>
                    <li>First add the calendar using desktop/web method above</li>
                    <li>Open Outlook mobile app</li>
                    <li>Tap the calendar icon at bottom</li>
                    <li>Tap the menu (☰) and check the subscribed calendar</li>
                </ol>
            </div>
        </details>

        <h3>Google Calendar</h3>
        <details style="margin-bottom: 15px;">
            <summary style="cursor: pointer; font-weight: bold; padding: 10px; background: #f0f0f0; border-radius: 5px;">
                🗓️ Click to expand Google Calendar instructions
            </summary>
            <div style="padding: 15px; border-left: 3px solid #4285f4;">
                <h4>Desktop Browser:</h4>
                <ol>
                    <li>Copy the calendar URL below</li>
                    <li>Open Google Calendar (calendar.google.com)</li>
                    <li>On the left, next to "Other calendars" click the + button</li>
                    <li>Select "From URL"</li>
                    <li>Paste the calendar URL</li>
                    <li>Click "Add calendar"</li>
                    <li>The calendar will appear in your list</li>
                </ol>

                <h4>Google Calendar Mobile App:</h4>
                <ol>
                    <li>First add the calendar using the browser method above</li>
                    <li>Open Google Calendar app</li>
                    <li>Tap the menu (☰) icon</li>
                    <li>Scroll down to find your subscribed calendar</li>
                    <li>Make sure it's checked to display events</li>
                </ol>

                <p><strong>Note:</strong> Google Calendar doesn't support direct URL subscription on mobile.
                You must add it via web browser first.</p>
            </div>
        </details>

        <h3>Apple Calendar</h3>
        <details style="margin-bottom: 15px;">
            <summary style="cursor: pointer; font-weight: bold; padding: 10px; background: #f0f0f0; border-radius: 5px;">
                🍎 Click to expand Apple Calendar instructions
            </summary>
            <div style="padding: 15px; border-left: 3px solid #007aff;">
                <h4>Mac Desktop:</h4>
                <ol>
                    <li>Copy the calendar URL below</li>
                    <li>Open Calendar app</li>
                    <li>From the menu bar, choose File → New Calendar Subscription</li>
                    <li>Paste the URL and click Subscribe</li>
                    <li>Choose settings (color, alerts, update frequency)</li>
                    <li>Click OK</li>
                </ol>

                <h4>iPhone/iPad:</h4>
                <ol>
                    <li>Copy the calendar URL below</li>
                    <li>Go to Settings → Calendar → Accounts</li>
                    <li>Tap "Add Account"</li>
                    <li>Select "Other"</li>
                    <li>Tap "Add Subscribed Calendar"</li>
                    <li>Paste the URL in the Server field</li>
                    <li>Tap "Next" and then "Save"</li>
                </ol>

                <h4>Alternative iPhone/iPad Method:</h4>
                <ol>
                    <li>Click on a calendar link below using Safari</li>
                    <li>A popup will ask if you want to subscribe</li>
                    <li>Tap "Subscribe"</li>
                    <li>Adjust settings if needed and tap "Done"</li>
                </ol>
            </div>
        </details>

        <h3>Android Calendars</h3>
        <details style="margin-bottom: 15px;">
            <summary style="cursor: pointer; font-weight: bold; padding: 10px; background: #f0f0f0; border-radius: 5px;">
                🤖 Click to expand Android instructions
            </summary>
            <div style="padding: 15px; border-left: 3px solid #3ddc84;">
                <h4>Samsung Calendar:</h4>
                <ol>
                    <li>Copy the calendar URL below</li>
                    <li>Open Samsung Calendar app</li>
                    <li>Tap the menu (☰) icon</li>
                    <li>Tap Settings → Manage calendars</li>
                    <li>Tap "Add account" → "Other"</li>
                    <li>Select "Subscribe to calendar"</li>
                    <li>Paste the URL and follow prompts</li>
                </ol>

                <h4>Other Android Apps (via Google Calendar):</h4>
                <ol>
                    <li>First add to Google Calendar using browser (see Google Calendar section)</li>
                    <li>The calendar will sync to your Android device automatically</li>
                    <li>Open your calendar app and ensure the subscribed calendar is visible</li>
                </ol>

                <h4>Using ICSx⁵ App (Universal Android Solution):</h4>
                <ol>
                    <li>Install ICSx⁵ from Google Play Store (free)</li>
                    <li>Copy the calendar URL below</li>
                    <li>Open ICSx⁵ and tap the + button</li>
                    <li>Paste the URL</li>
                    <li>Configure sync settings</li>
                    <li>The calendar will appear in your default calendar app</li>
                </ol>
            </div>
        </details>

        <h3>Quick Tips</h3>
        <div style="background: #e8f4f8; padding: 15px; border-radius: 5px; margin-top: 20px;">
            <ul style="margin: 0;">
                <li><strong>Subscribe vs Import:</strong> Always choose "Subscribe" or "From URL" for automatic updates</li>
                <li><strong>Update Frequency:</strong> Most apps check for updates every few hours to daily</li>
                <li><strong>Colors:</strong> You can usually customize calendar colors in your app settings</li>
                <li><strong>Notifications:</strong> Set up alerts for deadlines in your calendar app preferences</li>
                <li><strong>Troubleshooting:</strong> If events don't appear, check that the calendar is enabled/visible in your app</li>
            </ul>
        </div>
        </div>
    </div>

    <h2>Available Calendars:</h2>
'''

        # Add individual module group calendars
        for group in groups:
            group_name = {
                'CM1': 'CM1 Assignment Deadlines April 2026',
                'CM2': 'CM2 Assignment Deadlines April 2026',
                'CS1': 'CS1 Assignment Deadlines April 2026',
                'CS2': 'CS2 Assignment Deadlines April 2026',
                'CB': 'CB Assignment Deadlines April 2026',
                'CP1': 'CP1 Assignment Deadlines April 2026',
                'CP2': 'CP2 Assignment Deadlines April 2026',
                'CP3': 'CP3 Assignment Deadlines April 2026',
                'SP': 'SP Assignment Deadlines April 2026',
                'SA': 'SA Assignment Deadlines April 2026'
            }.get(group, f"{group} Assignment Deadlines April 2026")

            # Use environment variable for URL or detect from request
            if 'RAILWAY_STATIC_URL' in os.environ:
                base_host = os.environ['RAILWAY_STATIC_URL']
                https_base_url = f"webcal://{base_host}"
            else:
                host_header = self.headers.get('Host', 'localhost:8080')
                base_host = host_header
                https_base_url = f"webcal://{host_header}" if host_header != 'localhost:8080' else f"webcal://{host_header}"

            # Create both webcal and https URLs
            https_url = f"{https_base_url}/calendar/{group.lower()}.ics"
            webcal_url = f"webcal://{base_host}/calendar/{group.lower()}.ics"

            html += f'''
    <div class="calendar-link">
        <div style="font-weight: bold; margin-bottom: 10px;">
            {group_name}
            <span class="info-icon" onclick="showDeadlines('{group}')" title="View deadlines">ℹ</span>
        </div>
        <a href="{webcal_url}" class="subscribe-btn">🔄 Subscribe to Calendar</a>
        <div class="url-container">
            <span class="url">{https_url}</span>
            <button class="copy-btn" onclick="copyToClipboard('{https_url}', this)">📋 Copy URL</button>
        </div>
    </div>'''

        # Add combined calendar
        all_https_url = f"{https_base_url}/calendar/all.ics"
        all_webcal_url = f"webcal://{base_host}/calendar/all.ics"
        html += f'''
    <div class="calendar-link">
        <div style="font-weight: bold; margin-bottom: 10px;">
            ALL - All Assignment Deadlines
            <span class="info-icon" onclick="showDeadlines('ALL')" title="View all deadlines">ℹ</span>
        </div>
        <a href="{all_webcal_url}" class="subscribe-btn">🔄 Subscribe to Calendar</a>
        <div class="url-container">
            <span class="url">{all_https_url}</span>
            <button class="copy-btn" onclick="copyToClipboard('{all_https_url}', this)">📋 Copy URL</button>
        </div>
    </div>'''

        html += '''
    <hr style="margin-top: 30px;">
    <h3>Alternative: Manual Download</h3>
    <p>You can also download static ICS files by right-clicking the links above and selecting "Save Link As".</p>
    <p style="color: #666;">Note: Downloaded files won't update automatically. You'll need to re-download when deadlines change.</p>
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
            calendar_name = "All Assignment Deadlines April 2026"
        else:
            module_group = filename.replace('.ics', '').upper()
            calendar_name = f"{module_group} Marking Deadlines April 2026"

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

    def serve_deadlines(self, query_params):
        """Serve deadlines for a specific module group as JSON."""
        module_group = query_params.get('group', [None])[0]

        if module_group == 'ALL':
            module_group = None

        deadlines = self.db.get_deadlines_by_group(module_group)

        # Format deadlines for JSON response
        formatted_deadlines = []
        for module_code, assignment_code, title, deadline_date, recommend_date in deadlines:
            formatted_deadlines.append({
                'module_code': module_code,
                'assignment_code': assignment_code,
                'title': title,
                'deadline_date': deadline_date,
                'recommend_date': recommend_date
            })

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        response = {'deadlines': formatted_deadlines}
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def generate_calendar(self, module_group, calendar_name):
        """Generate ICS calendar for the specified module group."""
        calendar = Calendar()
        calendar.creator = f"{calendar_name}"

        # Set calendar name properties for better display in calendar apps
        calendar.extra.append(ContentLine('X-WR-CALNAME', value=calendar_name))
        calendar.extra.append(ContentLine('X-WR-CALDESC', value=f'ActEd {calendar_name}'))
        calendar.extra.append(ContentLine('NAME', value=calendar_name))

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
    parser.add_argument('--port', type=int, default=int(os.environ.get('CALENDAR_PORT', 8080)), help='Server port (default: 8080)')
    parser.add_argument('--host', default=os.environ.get('CALENDAR_HOST',
                        '0.0.0.0'), help='Server host (default: localhost)')
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