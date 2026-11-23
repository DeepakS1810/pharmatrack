# PharmaTrack DW: Medicine Demand, Pharmacy and Hospital Access Intelligence Warehouse

> **Educational Project Notice:**  
> PharmaTrack DW is an academic capstone application demonstrating **Data Warehousing and Data Mining (DWDM)** principles alongside public health location intelligence. It is **not** a medical diagnosis tool, not a guarantee of medicine stock or hospital bed capacity, not a payment or prescription ordering platform, not an ambulance-dispatch service, and not an organ-donor matching exchange.

---

## 1. Quick Windows Setup & Local Execution

### Prerequisites
- Windows 10 / 11
- Python 3.10+ (tested on Python 3.14)
- Modern web browser (Chrome, Edge, Firefox)

### Option A: One-Click Windows Launcher (Recommended)
Double-click `START_PHARMATRACK.bat` in the project directory:
```
C:\Users\jayes\OneDrive\Documents\dwdn capstone\Sales_OLAP_Application\START_PHARMATRACK.bat
```
The script verifies Python, checks dependencies, initializes the SQLite Data Warehouse (`pharmatrack_dw.sqlite`) if missing, automatically runs the initial ETL extraction from `pharma_sales.csv`, opens your browser to `http://127.0.0.1:5000`, and starts the local web server.

### Option B: Manual Command-Line Setup (PowerShell / Command Prompt)

1. **Navigate to the Project Directory:**
   ```powershell
   cd "C:\Users\jayes\OneDrive\Documents\dwdn capstone\Sales_OLAP_Application"
   ```

2. **Install Required Packages:**
   ```powershell
   pip install -r requirements.txt
   ```
   *(Required dependencies include Flask, pandas, Werkzeug, and requests.)*

3. **Initialize the Data Warehouse (Star & Snowflake Schemas):**
   ```powershell
   python migrate_db.py
   ```
   Creates all tables, foreign keys, and indexes in `pharmatrack_dw.sqlite`, seeds the essential medicines formulary catalog, loads verified pharmacies and hospitals, and creates authorized role-based user accounts.

4. **Execute the ETL Pipeline from `pharma_sales.csv`:**
   ```powershell
   python etl.py --run
   ```
   Executes the Extract, Transform, and Load pipeline, audits data quality (uniqueness, missing values, financial consistency, negative expiry flagging), and populates `fact_sales_expiry` and `fact_weather_observation`. The ETL pipeline can also be triggered directly from the web interface at `/etl`.

5. **Start the Local-First Web Server:**
   ```powershell
   python app.py
   ```
   Open your browser to: **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

### OpenStreetMap Nearby Hospital and Pharmacy Search

The Hospital Finder and Pharmacy Finder resolve a submitted place name with OpenStreetMap Nominatim, then search nearby mapped pharmacies or hospitals with the Overpass API. Device GPS can be used directly. Results are sorted by calculated straight-line distance, displayed as map pins, and include OpenStreetMap place links and driving directions. No API key or paid map service is required.

The endpoints and default radius can be changed in `.env`:

```dotenv
OSM_NOMINATIM_URL=https://nominatim.openstreetmap.org/search
OSM_OVERPASS_URL=https://overpass-api.de/api/interpreter
OSM_SEARCH_RADIUS_METERS=10000
```

Searches are only sent after a user submits a location. The app caches successful place-name lookups during its current run and limits Nominatim requests to one per second, identifies itself with an application User-Agent, and displays OpenStreetMap attribution. The public Nominatim and Overpass services have usage limits and may be busy; for larger deployments, use a compatible provider or a self-hosted service. See the [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/) and [Overpass API overview](https://wiki.openstreetmap.org/wiki/Overpass_API).

OpenStreetMap coverage is community-maintained and may be missing or outdated. A mapped hospital does not confirm current capacity or emergency intake, and a pharmacy listing does not confirm licensing, medicine stock, opening status, or delivery availability. The local PharmaTrack sample directory is displayed separately from the OSM search results.

---

## 2. File Placements & Structure

| File / Folder | Location | Purpose |
| :--- | :--- | :--- |
| **`pharma_sales.csv`** | Root of `Sales_OLAP_Application\` | Historical educational dataset (2,000 orders, Jan 2025 – May 2026). Source file for the ETL pipeline. |
| **`pharmatrack_dw.sqlite`** | Root of `Sales_OLAP_Application\` | The local SQLite Data Warehouse containing both Star and Snowflake schema tables, fact tables, dimensions, operational tables, and recovery codes. |
| **`totp_auth.py`** | Root of `Sales_OLAP_Application\` | Pure-Python RFC 6238 TOTP authenticator engine, base32 secret generation, provisioning URI generator, and single-use emergency recovery code hashing. |
| **`migrate_db.py`** | Root of `Sales_OLAP_Application\` | Database initialization, schema migration, and CLI role assignment script (`--assign-role`). |
| **`etl.py`** | Root of `Sales_OLAP_Application\` | Standalone developer CLI tool for Extract-Transform-Load execution, schema validation, and data quality logging. |
| **`import_catalog.py`** | Root of `Sales_OLAP_Application\` | Developer CLI tool for importing external medicine formulary CSV/JSON files into `dim_product`. |
| **`app.py`** | Root of `Sales_OLAP_Application\` | Core Flask application controller handling routes, two-step authentication, role verification, rate limiting, and developer CLI commands (`assign-role`). |
| **`test_app.py`** | Root of `Sales_OLAP_Application\` | Existing automated checks; some authentication cases still describe the earlier password-login flow and need updating for email OTP. |
| **`requirements.txt`** | Root of `Sales_OLAP_Application\` | Python package dependencies (`Flask`, `pandas`, `Werkzeug`). |
| **`.env.example`** | Root of `Sales_OLAP_Application\` | Configuration template for the Flask app, Brevo email OTP, and data-source settings. |
| **`START_PHARMATRACK.bat`** | Root directory | Windows batch file to launch the local web server and open the browser. |
| **`templates/`** | `templates/` subdirectory | Jinja2 HTML templates for all application modules, separate login and registration views, 2FA prompt (`login_2fa.html`), recovery code prompt (`login_recovery.html`), security settings (`security_settings.html`), and role-specific dashboards. |
| **`static/`** | `static/` subdirectory | Custom CSS (`css/style.css`), 3D polyhedral OLAP Cube renderer (`js/olap_cube.js`), client-side QR generator (`js/qrcode.min.js`), and bilingual client script (`js/app.js`). |

---

## 3. Strict Application Navigation Order

The navigation bar strictly follows the required sequence:
1. **🔍 Medicine Search** (`/medicines`)
2. **🏥 Pharmacy Finder** (`/pharmacies`)
3. **🚑 Hospital Finder** (`/hospitals`)
4. **🚨 Emergency Help** (`/emergency`) *(Emergency 108/112 accessible without logging in)*
5. **📈 Demand & Weather Analysis** (`/analytics`)
6. **📐 DWDM Warehouse & Schema** (`/schema`)
7. **⚙️ ETL Pipeline & Data Quality** (`/etl`) *(strictly positioned before OLAP Cube)*
8. **🧊 OLAP Cube** (`/olap`)
9. **🫀 Organ Donation Awareness** (`/organ-donation`)

*For authenticated Pharmacy Owners and Hospital Staff, dedicated management tabs (`Owner Management` or `Staff Management`) appear at the right end of the navigation bar.*

---

## 4. Email OTP Sign-In, Role-Based Access Control & Registration

When the application opens, users are immediately directed to the **Sign In** screen (`/login`). Feature and analytics modules cannot be accessed prior to authentication.

### Authentication Flow — Registered Email + Brevo OTP

1. **Choose role and enter email (`/login`)** — The person selects Public Citizen, Pharmacy Owner, or Hospital Staff and enters the email address registered on their account. Sign-in looks up email and role together; a password or username cannot bypass verification.
2. **Email a one-time code** — PharmaTrack generates a cryptographically secure six-digit code and submits it to the account's registered email using Brevo Transactional Email. Only a hash is stored in `otp_attempts`.
3. **Verify to access** — The code expires after five minutes, allows five attempts, and can be resent after the cooldown. Access is granted only after correct verification. If the account has separately enrolled authenticator TOTP, that check follows email verification.
4. **Fail-closed behavior** — Missing Brevo credentials or a failed send blocks sign-in and email-verified registration. There is no password-only fallback, owner-phone routing, or WhatsApp fallback.
5. **New account registration** — Public Citizen sign-up requires a valid, accessible email. After submitting registration, the app emails a code; the account is not signed in until that code is verified. Successful verification completes registration and signs the user in.

> **Delivery status:** A successful Brevo API response means **Submitted**, not confirmed delivered. The user interface never claims delivery unless Brevo reports it. Check the registered inbox's Spam/Junk and Promotions folders and Brevo's transactional email logs if no message arrives.

### Two-Step Verification Flow (TOTP via Authenticator App — optional)
Accounts that have enrolled TOTP (Google Authenticator / Microsoft Authenticator) first complete the registered-email OTP flow and then verify the time-sensitive authenticator code at `/login/2fa`. No role or session access is granted before those checks complete.
3. **Emergency Recovery Codes (`/login/recovery`):**
   - If the user misplaces their phone or cannot open their authenticator app, they can redeem one of their 8 single-use emergency recovery codes (e.g. `A1B2-C3D4`).
   - Recovery codes are stored in the database **only as cryptographic hashes** (`user_recovery_codes`).
   - When a recovery code is redeemed, it is marked `is_used = 1` with a timestamp and permanently invalidated. It cannot be used again.

### Account Security Settings (`/settings/security`)
Authenticated users can manage their two-step verification status at any time:
- **Enrollment Flow:**
  - Displays a clean QR code generated client-side using zero-dependency JavaScript (`static/js/qrcode.min.js`), completely offline.
  - Displays a human-readable setup key grouped in 4-character blocks (e.g. `ABCD EFGH 1234 ...`) with a one-click **Copy Key** button.
  - **Verification Gate:** 2FA is **not enabled** until the user types the 6-digit code from their app to confirm successful pairing.
  - Upon confirmation, the application automatically generates **8 fresh single-use emergency recovery codes**, stores their hashes, and displays them with **Copy All Codes** and **Download (.txt)** buttons.
- **Regenerate Recovery Codes:**
  - Users can generate a fresh batch of 8 recovery codes at any time by verifying their account password and current 6-digit authenticator code. Any previous unused codes are invalidated.
- **Disable Two-Step Verification:**
  - Requires entering the account password and either the current 6-digit authenticator code or an unused recovery code. Disabling 2FA clears secrets and removes recovery codes.

### Dedicated Separate Views: Sign In vs. Create Account
- **Sign In View (`/login`):** Streamlined login form requiring role selection and the account's registered email. The user enters the code emailed by Brevo on the next screen. No registration fields clutter the sign-in screen.
- **Create Account View (`/register`):** Separate registration screen opened after the user clicks **"Create Account"**. It requires an accessible email, sends an OTP, and completes sign-in only after verification.
- **Public Citizen Registration Enforcement:**
  - Public signup is restricted to **Public Citizen** (`role = 'public'`) accounts only.
  - Public registration does **not** allow users to grant themselves Pharmacy Owner or Hospital Staff roles.
  - Any forged or programmatic attempt to register a privileged role via `/register` is strictly rejected with an explicit error message.
- **Institutional Roles Provisioning:**
  - **Pharmacy Owner** and **Hospital Staff** accounts represent verified institutional actors and must be assigned only through trusted setup (`migrate_db.py`) or the documented developer CLI:
    ```powershell
    python app.py assign-role <username> <role> [--pharmacy-id <id>] [--hospital-id <id>]
    ```

### Rate Limiting & Brute-Force Protection
To protect against sign-in abuse and brute-force attacks:
- Email-code requests are rate-limited under `auth_rate_limits`; repeated requests are temporarily locked. Code requests also have a 60-second resend cooldown.
- Failed 6-digit authenticator code attempts are tracked under `totp:<user_id>`. 5 consecutive failures lock 2FA verification for 15 minutes, prompting the user to wait or use an emergency recovery code.
- Failed recovery code redemptions are tracked under `rec:<user_id>`. 5 consecutive failures lock recovery verification for 15 minutes.
- Successful verification immediately resets attempt counters.

### Role Selection & Access Permissions
Users select their authorization role prior to signing in:
- **Public Citizen:** Open public access to medicine search with autocomplete, verified nearby pharmacy & hospital locator with GPS geodesic routing, demand & weather analytics, DWDM Star/Snowflake schema visualizer, ETL quality auditing, 3D OLAP cube, and NOTTO organ donation resources.
- **Pharmacy Owner:** Authorized access to manage only assigned pharmacy/franchise locations, update dispensary hours and phone, and submit stock reports with 48-hour staleness tracking. Cannot access Hospital Staff workspaces or other owners' pharmacies.
- **Hospital Staff:** Authorized access to manage only their assigned hospital profile, contact details, operating hours, and clinical emergency capacity indicators. Cannot access pharmacy inventory tools or other hospitals.

### Role Authorization Verification
- Selecting a role **does not** automatically authenticate the user, prefill credentials, or bypass the login gate.
- During authentication, the backend queries the database and verifies that the account's registered role matches the role selected in the dropdown.
- The sign-in form uses the account's registered email and sends the code only if that account matches the selected role. The UI uses a generic error for unrecognized email/role combinations.
- **Removal of Admin Portal:** The user-facing Project Administrator role, admin portal, and bypass buttons have been removed from the application. Necessary database maintenance is handled exclusively through developer CLI tools (`python migrate_db.py`, `python etl.py`).

### OTP Routes
- All legacy One-Time Password routes for Twilio, Meta WhatsApp webhooks (`/verify-otp`, `/otp/send-whatsapp`, `/otp/resend`, `/otp/cancel`, `/api/webhooks/twilio`, `/api/webhooks/meta-whatsapp`, `/api/webhooks/sms-dlr`) have been removed and return HTTP 404.
- Brevo email OTP routes (`/login/otp`, `/login/otp/verify`, `/login/otp/resend`, `/api/otp/status`) require a valid pending-OTP session. There is no WhatsApp OTP route.

### Brevo Setup — Transactional Email OTP

#### Prerequisites
1. **Create a Brevo account** at [https://app.brevo.com](https://app.brevo.com)
2. **Generate an API key:** Profile → SMTP & API → API Keys → Create New Key.
3. **Verify a sender email:** add and verify an email under Brevo's Senders & IP settings. Brevo will reject unverified senders.
4. **Use the registered user's real email:** seeded `example.com` addresses are placeholders and cannot receive codes. Update each account's email in the local `app_users` table before testing that account. For example, from the project folder, replace the sample username and address here:
   ```powershell
   py -c "import sqlite3; c=sqlite3.connect('pharmatrack_dw.sqlite'); c.execute('UPDATE app_users SET email = ? WHERE username = ?', ('you@example.org', 'citizen_chennai')); c.commit(); c.close()"
   ```

See Brevo's [transactional email API guide](https://developers.brevo.com/docs/send-a-transactional-email).

#### Windows Environment Setup
```powershell
# 1. Copy the template
copy .env.example .env

# 2. Edit with Notepad (or VS Code)
notepad .env
```

Fill in these values in `.env`:
```
BREVO_API_KEY=<your-private-Brevo-API-key>
BREVO_EMAIL_SENDER=<your-verified-sender-email>
BREVO_EMAIL_SENDER_NAME=PharmaTrack DW
```

> **Never commit `.env` to source control.** The file is in `.gitignore`.

#### OTP Security Parameters
| Parameter | Value |
|-----------|-------|
| OTP length | 6 digits (cryptographically secure) |
| OTP expiry | 5 minutes |
| Max verification attempts | 5 (then locked) |
| Resend cooldown | 60 seconds |
| Storage | SHA-256 hash only — plain OTP never stored |
| Email masking | Only a masked version of the registered email is shown on the OTP page |

#### Testing OTP Delivery
1. Set `BREVO_API_KEY` and a verified `BREVO_EMAIL_SENDER` in `.env`, then restart the app.
2. Enter the email stored on the selected account and request a code.
3. Check Brevo's transactional email logs. A submitted message may still be delayed, filtered, or rejected by the recipient mailbox.
4. Check Inbox, Spam/Junk, and Promotions. Confirm the account's stored address is correct and accessible.

### Cryptographic Security & Session Handling
- Passwords are securely hashed using `werkzeug.security` with PBKDF2-SHA256 (or scrypt where supported).
- Plain-text passwords and credentials are never stored in the database or exposed in client logs.
- Sessions are cryptographically signed with Flask's secret key, and session tokens store only authenticated user identity and verified role scopes.

### Seeded Demonstration Accounts
The local capstone database is configured so the registered project email can open the Public Citizen, Pharmacy Owner, and Hospital Staff demonstration profiles. Choose the role and use that registered email; sign-in resolves the profile by both email and role. The owner and hospital profiles retain their seeded pharmacy/hospital assignments.

Fresh database initialization still seeds placeholder `example.com` addresses. Before using OTP sign-in on a fresh copy, replace the email on each required demonstration profile with an accessible address. Public sign-up remains limited to Public Citizen; institutional roles must be provisioned and assigned to their pharmacy or hospital. This shared-email setup is for the local capstone walkthrough only.

| Role | Username (for local database email update) | Assigned Facility Scope |
| :--- | :--- | :--- |
| **Public Citizen** | `citizen_chennai` | Open Public Access |
| **Public Citizen (Alt)** | `citizen_delhi` | Open Public Access |
| **Pharmacy Owner** | `ayapakkam_apollo` | Apollo Pharmacy (Ayapakkam Main Road & Mogappair) |
| **Pharmacy Owner (Alt)** | `ambattur_medplus` | MedPlus Ambattur OT |
| **Hospital Staff** | `stedeford_staff` | Sir Ivan Stedeford Hospital, Ambattur |
| **Hospital Staff (Alt)** | `gh_ambattur_staff` | Government Hospital, Ambattur |

---

## 5. Pharmacy Owner Workspace & 48-Hour Staleness Rule

Authenticated Pharmacy Owners access a dedicated management workspace (`/owner/dashboard`):
- **Multi-Franchise Switcher:** Switch between assigned locations via a dropdown menu.
- **Location Profile Management:** Edit dispensary phone number, operating hours, and online store URL with explicit **Save** and **Cancel** actions.
- **Formulation Stock Submission:** Report stock with formulation/active ingredient, quantity, listed retail price, and batch verification notes with explicit **Save** and **Cancel** actions.
- **Pharmacy-Reported Label:** Submissions are tagged as **pharmacy-reported** with the verified owner's name and an audit timestamp.
- **48-Hour Staleness Rule:** Any stock update older than **48 hours** is automatically flagged in both the Owner Dashboard and the public Pharmacy Finder:
  - `✓ Active (<48h)`: Fresh, verified availability.
  - `⚠️ Stale (>48h - Re-verification Required)`: Reported more than 48 hours ago; requires dispensary re-verification.
- **Server-Side Ownership Enforcement:** Server-side verification confirms that owners can modify only locations assigned to their user ID in `user_pharmacy_assignments`.

---

## 6. DWDM Warehouse Architecture: Connected Star vs. Snowflake Schemas

The **DWDM Warehouse & Schema** module (`/schema`) provides an interactive architectural visualizer with a live toggle between Star Schema and Snowflake Schema views:

### Star Schema Architecture
- Central Fact Table: `fact_sales_expiry` positioned in the center with dimension tables connected around it (`dim_product`, `dim_date`, `dim_region`).
- Grain: 1 transactional order observation.
- Measures: Quantity sold, unit price, total sales volume.

### Snowflake Schema Architecture (Normalized 3NF)
- Normalization trees branching outward:
  - Product Hierarchy: `dim_product` $\rightarrow$ `dim_category` and `dim_dosage_form`.
  - Geographic Hierarchy: `dim_region` $\rightarrow$ `dim_city` $\rightarrow$ `dim_district` $\rightarrow$ `dim_state`.
  - Facilities Hierarchy: `dim_pharmacy` $\rightarrow$ `dim_city`, and `dim_hospital` $\rightarrow$ `dim_hospital_type` + `dim_city`.

### Dynamic Edge-Anchored SVG Relationship Connectors
- Visible SVG bezier curves connect Foreign Keys (FK) to referenced Primary Keys (PK).
- **Outer Edge Anchoring:** Paths strictly anchor to outer card boundaries (exiting the outer border of the source and landing on the outer border of the target) so lines travel through whitespace gutters and **never overlap or cross table card text**.
- Visible directional arrowheads (`url(#arrow-star)` / `url(#arrow-snowflake)`), clear `🔑 PK` / `🔗 FK` labels, and `1 : N` cardinality badges.
- Dynamically resizes to match container dimensions on scroll, tab switch, or window resize.

---

## 7. True 3D WebGL Multidimensional OLAP Hypercube

The **OLAP Cube** (`/olap`) features an authentic, GPU-accelerated 3D spatial rendering engine built with **Three.js (r128)** and **OrbitControls** (`static/js/three.min.js`, `static/js/OrbitControls.js`, `static/js/olap_cube.js`) bundled locally with zero external CDN dependencies:
- **True 3D WebGL Perspective & Lighting:** Renders real 3D box voxels with perspective projection, depth testing, specular sheen, and directional lighting.
- **Accessible Therapeutic Category Colors & Matching Legend:**
  - **Antibiotics:** `#0d9488` (Teal)
  - **Analgesics & Antipyretics:** `#2563eb` (Blue)
  - **Antidiabetic:** `#7c3aed` (Purple)
  - **Hormone Preparations:** `#ea580c` (Amber)
- **3D Labeled Coordinate Axes:** Color-coded 3D axes with directional arrowheads and billboarded text sprites:
  - **X-Axis (Teal `#0d9488`):** Medicine Name / Therapeutic Category
  - **Y-Axis (Deep Blue `#2563eb`):** Calendar Period (Year, Quarter, Month)
  - **Z-Axis (Purple `#7c3aed`):** Geographic Region / Distributor Chain
  - **Active Measure Badge:** Displays currently selected metric (`Units Sold`, `Total Sales Volume`, `Expired Transactions Count`, `Average Unit Price`).
- **Outer Wireframe Bounding Cage:** Renders a 12-edge bounding box framing the 3D data hypercube rotating in 360°.
- **Interactive Multi-Input Navigation:**
  - 360° mouse drag orbit and touch swipe gestures.
  - Mouse wheel zoom and dedicated zoom buttons (`🔍+ In`, `🔍- Out`).
  - Step rotation toolbar (`⟲ Left`, `⟳ Right`, `⬆ Up`, `⬇ Down`, `↺ Reset View`).
  - **▶ Auto-Rotate Toggle:** Continuous smooth 60fps rotation.
  - Accessible keyboard shortcuts: Arrow keys (orbit), `+`/`-` (zoom), `R` (reset view), `Space` (auto-rotate).
- **Raycasting Hover & Click Inspection:**
  - Hovering over any 3D voxel highlights it with a glowing golden amber emissive effect (`#f59e0b`) and scale emphasis.
  - Floating tooltip displays Medicine, Category, Period, Region, and formatted Measure value.
  - Clicking a cell pins its multidimensional coordinates to the Inspector Card.
- **Empty State & Accessible 2D Alternative:**
  - Clean empty state alert when filter criteria match zero warehouse records.
  - Synchronized WCAG AA accessible 2D Cross-Tabulation Pivot Table with row totals, column totals, and clickable cell inspection.
- **5 Core OLAP Operations Demonstrated:**
  1. **Roll-up:** Aggregate from month to quarter, year, or therapeutic category.
  2. **Drill-down:** Decompose annual summaries into quarterly and monthly detail.
  3. **Slice:** Extract a 2D cross-section by fixing one dimension (e.g. `Region = 'Tamil Nadu'`).
  4. **Dice:** Apply conditional filters across multiple dimensions simultaneously.
  5. **Pivot / Rotate:** Dynamically swap row and column dimensions.

---

## 8. Web-Triggered & CLI ETL Ingestion Pipeline

The **ETL Pipeline & Data Quality** module (`/etl`) is strictly positioned **before** the OLAP Cube in the navigation bar (Nav Item 7 vs Item 8) and performs real warehouse ingestion:
- **Web-Triggered Ingestion:** Users can trigger the complete ETL pipeline by clicking **⚡ Run ETL Ingestion Pipeline** (or `POST /etl/run`), which executes `execute_etl()` from `etl.py`.
- **Live Stage Telemetry:** Displays step-by-step status for Extract, Transform, and Load stages with real-time timer and reload notification.
- **Data Quality Profiling & Scorecards:**
  - Total Records Extracted: 2,000
  - Clean Valid Records: 1,909
  - Quarantined Expired Records: 91 (`Expiry_Days_Left <= 0` or `Expired_Stock == 'Yes'`)
  - Null / Missing Attributes: 0
- **Quarantined Inventory & Quality Anomaly Table:** Real transaction records flagged during transformation with explicit reasons (e.g. `Shelf-life expired (<= 0 days)`) and safety isolation actions taken (`expired_stock_flag='Yes'`).
- **Idempotent Load Transactions:** Atomic database transactions using `INSERT OR REPLACE INTO fact_sales_expiry`, preventing duplicate rows upon pipeline re-execution.
- **Audit Logging:** Every execution is audited in `etl_audit_log` with timestamp, stage, status, row counts, and quality notes.
- **Standalone CLI Execution:** Developers can run `python etl.py --run` or `python etl.py --status` directly from PowerShell.

---

## 9. Emergency Help (108 / 112) Direct Access

Emergency medical assistance is prioritized throughout the application:
- **Top Emergency Banner:** Direct Tap-to-Call buttons for **108** (Tamil Nadu Ambulance) and **112** (All India ERSS).
- **Emergency Screen (`/emergency`):** Accessible **without logging in**. Provides one-tap calling, nearest emergency department directory, and ambulance protocol guidance.
- **Hero Callout on Login Screen:** Emergency assistance callout on the login screen ensures no user facing an emergency is delayed by an authentication gate.

---

## 10. Developer CLI Commands Reference

All administrative operations are executed using command-line developer scripts:

### 1. Execute Full ETL Pipeline
```powershell
python etl.py --run
```
Extracts `pharma_sales.csv`, audits data quality, flags negative expiry transactions, and populates `fact_sales_expiry`.

### 2. View Warehouse & ETL Telemetry
```powershell
python etl.py --status
```
Displays live record counts for facts, dimensions, and the last refresh timestamp.

### 3. Rebuild / Migrate Database Schema
```powershell
python migrate_db.py
```
Initializes Star and Snowflake schema tables, establishes referential constraints, populates seed records, creates recovery tables, and initializes rate limits.

### 5. Institutional Role Assignment CLI
```powershell
# Assign a user to Pharmacy Owner with an assigned pharmacy key:
python app.py assign-role priya_owner pharmacy_owner --pharmacy-id 1

# Assign a user to Hospital Staff with an assigned hospital key:
python app.py assign-role rajan_hospital hospital_staff --hospital-id 2

# Or use migrate_db.py:
python migrate_db.py --assign-role priya_owner pharmacy_owner --pharmacy-id 1
```
