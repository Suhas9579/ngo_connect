# Resource Allocation and Volunteer Matching Platform for a Single NGO

This is a complete, fully functional, production-ready web application designed for a single NGO to manage volunteers, events, resources, attendance, donations, reports, and smart volunteer allocation.

It serves as an excellent **Final Year Engineering Project** demonstrating full-stack engineering, databases, security, and algorithmic recommendation systems.

---

## 🌟 Key Features

1. **Role-Based Portals**:
   - **Admin (NGO Manager)**: Dashboard counters, volunteer CRUD with search/filters, event scheduling and closing, resource stock registry, allocation tickets, donation ledger, QR code attendance generation, manual check-sheet overrides, and dynamic PDF/CSV reports.
   - **Volunteer**: Profile settings (skills, availability), event catalog, application submission & cancellation, check-in page with camera QR reader + simulated mock scan, and earned certificate history.

2. **Smart Volunteer Matchmaking System**:
   - Recommends suitable volunteers for any event based on:
     - **Skill overlap**: Correlates event categories with volunteer skills (e.g. *Medical Camp* -> *medicine*, *first aid*).
     - **General Availability**: Matches event dates (weekdays/weekends) with volunteer availability.
     - **Experience**: Weighs points based on cumulative attendance history.
     - **Schedule Conflict Checking**: Marks availability status as "Busy" if the volunteer is already assigned to another event on the same day.

3. **Resource Allocation and Stock Tracking**:
   - Automates inventory counts with the calculation:
     $$\text{Remaining Quantity} = \text{Available} - \text{Allocated} - \text{Used}$$
   - Permits allocation of inventory items to upcoming events, and logs consumption quantities.

4. **Attendance Management (QR & Manual)**:
   - In-memory QR code generator representing secure event check-in URLs.
   - Direct camera QR scanner integrations using standard webcams or mobile browsers.
   - Mock check-in simulator to demonstrate check-in without physical camera access.
   - Manual admin check-sheets.

5. **Automated PDF Certificate Generation**:
   - Uses `ReportLab` to programmatically build landscape Certificates of Appreciation with borders, issuance dates, serial numbers, and authorized signature canvases.

6. **Consolidated Reports Module**:
   - Exports 6 reports in **PDF** (rendered tables) and **CSV** formats:
     1. Volunteer Participation
     2. Event Schedules
     3. Donation Logs
     4. Attendance Ledger
     5. Resource Inventory
     6. Monthly consolidated NGO Activity summary

7. **Notification Center**:
   - Real-time-like updates for status approvals, certificate issues, check-ins, and newly scheduled events.

---

## 🛠️ Technology Stack

- **Backend**: Python, Flask, Flask-SQLAlchemy (SQLite database), Flask-Login (session management), Flask-WTF (forms security), Werkzeug (password hashing)
- **Frontend**: HTML5, CSS3, Bootstrap 5, JavaScript, Chart.js, HTML5-QRCode scanner
- **Libraries**: ReportLab (PDFs), qrcode (QR codes), Pillow, Cryptography, email-validator

---

## 🚀 Setup & Execution

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application**:
   ```bash
   python app.py
   ```

   *When `app.py` runs, it will:*
   - Automatically create the SQLite database (`ngo.db`).
   - Automatically build all database tables.
   - Automatically initialize assets folders (`uploads/`, `reports/`, `certificates/`).
   - Automatically insert the default Administrator account and seed sample records (10 volunteers, 5 events, 10 resources, 20 donations, past attendance history, and pre-generated PDF certificates).

3. **Default Admin Login**:
   - **Email**: `admin@ngo.com`
   - **Password**: `admin123`

4. **Default Volunteer Logins**:
   - **Emails**: `vol1@ngo.com` through `vol10@ngo.com`
   - **Password**: `volpass123`

---

## 📂 Project Architecture

```text
ngo_platform/
│
├── app.py              # Main route handlers, matching engine, and pdf exports
├── models.py           # SQLAlchemy database schemas and relationships
├── forms.py            # Flask-WTF validation rules for all modules
├── config.py           # File paths and app configurations
├── requirements.txt    # Python dependencies
├── README.md           # Documentation
├── ngo.db              # SQLite Database (Auto-generated)
│
├── static/
│   ├── css/
│   │   └── styles.css  # Tailored Light/Dark mode stylesheets
│   └── js/
│       └── main.js    # Chart.js loaders and scanner wrappers
│
├── templates/          # Jinja2 Layout Templates
│   ├── base.html       # Sidebar shell with notifications
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html  # Dynamic widgets and charts
│   ├── volunteers.html # Directories and profiles
│   ├── events.html
│   ├── event_details.html
│   ├── resources.html  # Stock registers
│   ├── donations.html  # Contribution logs
│   ├── attendance.html # QR readers and simulators
│   ├── reports.html    # Data export modules
│   └── certificates.html
│
├── uploads/            # Temporary attachments (Auto-created)
├── reports/            # Export cache (Auto-created)
└── certificates/       # PDF Certificate storage (Auto-created)
```
