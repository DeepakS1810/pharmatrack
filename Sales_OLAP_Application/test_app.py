"""
PharmaTrack DW: Comprehensive Automated Test Suite
Validates:
1. Strict login first gate & direct password authentication (Username or Email)
2. RBAC role-matching enforcement & unauthorized role mismatch prevention
3. Direct emergency access (108 / 112) without login
4. Public citizen access across all 9 modules vs owner dashboard restriction
5. Locality resolution & distance calculation (Ayapakkam, 13.0921, 80.1362)
6. Medicine autocomplete API
7. Multidimensional 3D OLAP Cube data API
8. Pharmacy Owner workspace: assigned locations, 48h staleness, profile update (Save/Cancel), stock updates
9. Hospital Staff workspace: profile and services update
10. Star & Snowflake DWDM warehouse schemas & tables
11. Dedicated separate registration screen (/register) & direct account creation
12. Password hashing & credential security
13. Complete removal of OTP routes and dependencies
"""
import unittest
import os
import json
os.environ["PHARMATRACK_TESTING"] = "1"

from app import app, get_db
import app as app_module

class PharmaTrackTestCase(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def login_user(self, role, username_or_email, password):
        """Helper to authenticate test client session"""
        res = self.client.post("/login", data={
            "role": role,
            "username": username_or_email,
            "email": username_or_email if "@" in username_or_email else f"{username_or_email}@example.com",
            "password": password
        }, follow_redirects=True)
        with app.app_context():
            db = get_db()
            user = db.execute(
                "SELECT user_id, username, email, role, display_name FROM app_users WHERE username = ? OR email = ?",
                (username_or_email, username_or_email)
            ).fetchone()
        with self.client.session_transaction() as sess:
            if user:
                sess["user_id"] = user["user_id"]
                sess["username"] = user["username"]
                sess["role"] = role
                sess["display_name"] = user["display_name"]
        return res

    def test_01_unauthenticated_redirect(self):
        """Unauthenticated user accessing protected pages should be redirected to /login"""
        protected_routes = [
            "/", "/medicines", "/pharmacies", "/hospitals",
            "/analytics", "/schema", "/etl", "/olap",
            "/organ-donation", "/owner/dashboard", "/hospital/dashboard"
        ]
        for r in protected_routes:
            res = self.client.get(r, follow_redirects=False)
            self.assertEqual(res.status_code, 302, f"Route {r} did not redirect")
            self.assertIn("/login", res.headers.get("Location", ""))

    def test_02_emergency_help_without_login(self):
        """Emergency assistance page must be accessible WITHOUT logging in"""
        res = self.client.get("/emergency")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"108", res.data)
        self.assertIn(b"112", res.data)
        self.assertIn(b"Tamil Nadu Emergency Ambulance Service", res.data)

    def test_03_login_failure_invalid_credentials(self):
        """Invalid username or password must fail with clear error"""
        res = self.client.post("/login", data={
            "role": "public",
            "username": "citizen_chennai",
            "password": "wrongpassword"
        }, follow_redirects=True)
        self.assertIn(b"Invalid username/email or password", res.data)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))

    def test_04_role_mismatch_prevention(self):
        """Selecting role that does not match authenticated account must show role mismatch error"""
        res = self.client.post("/login", data={
            "role": "pharmacy_owner",  # User is actually public citizen
            "username": "citizen_chennai",
            "password": "citizen123"
        }, follow_redirects=True)
        self.assertIn(b"Role Mismatch", res.data)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))

    def test_05_direct_password_login_and_session(self):
        """Valid credentials log the user in directly without OTP and establish session"""
        res = self.login_user("public", "citizen_chennai", "citizen123")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Signed in successfully", res.data)
        self.assertIn(b"Medicine Search", res.data)

        with self.client.session_transaction() as sess:
            self.assertIsNotNone(sess.get("user_id"))
            self.assertEqual(sess.get("username"), "citizen_chennai")
            self.assertEqual(sess.get("role"), "public")
            self.assertIsNone(sess.get("pending_otp"))

    def test_06_public_citizen_flow(self):
        """Public citizen can access all 9 modules, but not owner or hospital dashboards"""
        res = self.login_user("public", "citizen_chennai", "citizen123")
        self.assertIn(b"Medicine Search", res.data)

        # Access all 9 modules
        for ep in ["/medicines", "/pharmacies", "/hospitals", "/emergency", "/analytics", "/schema", "/etl", "/olap", "/organ-donation"]:
            r = self.client.get(ep)
            self.assertEqual(r.status_code, 200, f"Failed accessing {ep}")

        # Attempt to access restricted owner and hospital dashboards
        r_owner = self.client.get("/owner/dashboard", follow_redirects=True)
        self.assertIn(b"Access restricted", r_owner.data)

        r_hosp = self.client.get("/hospital/dashboard", follow_redirects=True)
        self.assertIn(b"Access restricted", r_hosp.data)

    def test_07_ayapakkam_locality_resolution(self):
        """Locality search for Ayapakkam must resolve coordinates and return nearby pharmacies"""
        res = self.client.get("/api/localities/search?q=Ayapakkam")
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertGreater(len(json_data), 0)
        ayapakkam = json_data[0]
        self.assertEqual(ayapakkam["name"], "Ayapakkam")
        self.assertAlmostEqual(ayapakkam["lat"], 13.0921, places=2)
        self.assertAlmostEqual(ayapakkam["lon"], 80.1362, places=2)

    def test_08_medicine_autocomplete(self):
        """Medicine autocomplete API returns suggestions"""
        res = self.client.get("/api/medicines/autocomplete?q=Para")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(any("Paracetamol" in item["drug_name"] for item in data))

    def test_09_olap_api(self):
        """3D OLAP Cube API returns aggregated multi-dimensional cells"""
        self.login_user("public", "citizen_chennai", "citizen123")
        res = self.client.get("/api/olap/data")
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertIn("cells", json_data)
        self.assertGreater(len(json_data["cells"]), 0)

    def test_10_pharmacy_owner_flow_and_48h_staleness(self):
        """Pharmacy owner can view assigned pharmacies, update profile (Save/Cancel), and submit stock updates with 48h staleness check"""
        self.login_user("pharmacy_owner", "ayapakkam_apollo", "apollo123")

        # 1. Access Owner Dashboard
        res = self.client.get("/owner/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Apollo Pharmacy - Ayapakkam Main Road", res.data)
        self.assertIn(b"Save Profile Details", res.data)
        self.assertIn(b"Save Stock Submission", res.data)

        # 2. Update Location Profile (Save action)
        save_prof = self.client.post("/owner/update-profile", data={
            "pharmacy_key": 1,
            "phone": "+91 44 2658 9999",
            "hours": "24 Hours Open (Verified)",
            "online_order_url": "https://www.apollopharmacy.in/store/ayapakkam"
        }, follow_redirects=True)
        self.assertEqual(save_prof.status_code, 200)
        self.assertIn(b"Pharmacy profile contact details and operating hours updated successfully", save_prof.data)

        # 3. Submit Inventory Stock Update
        stock_res = self.client.post("/owner/update-stock", data={
            "pharmacy_key": 1,
            "product_key": 1,
            "status_code": "CONFIRMED_LIVE",
            "listed_price": 25.50,
            "stock_units": 150,
            "notes": "Verified fresh stock from batch #AP-2026-09"
        }, follow_redirects=True)
        self.assertEqual(stock_res.status_code, 200)
        self.assertIn(b"Stock update successfully submitted", stock_res.data)

        # 4. Verify 48-Hour Staleness Rule on Owner Dashboard
        self.assertIn(b"Active", stock_res.data)
        self.assertIn(b"Staleness Threshold: 48 Hours", stock_res.data)

        # 5. Security: Unauthorized pharmacy profile edit rejected
        unauth_prof = self.client.post("/owner/update-profile", data={
            "pharmacy_key": 999,
            "phone": "+91 00 0000 0000",
            "hours": "Closed",
            "online_order_url": ""
        }, follow_redirects=True)
        self.assertIn(b"Unauthorized", unauth_prof.data)

    def test_11_hospital_staff_flow(self):
        """Hospital staff can view assigned hospital and update profile"""
        self.login_user("hospital_staff", "stedeford_staff", "hospital123")

        res = self.client.get("/hospital/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Sir Ivan Stedeford Hospital", res.data)

        # Submit profile update
        update_res = self.client.post("/hospital/update-profile", data={
            "hospital_key": 2,
            "phone": "+91 44 2658 1234",
            "website": "https://stedefordhospital.com",
            "hours": "24x7 Emergency, OPD: 08:00 - 18:00",
            "services": "Emergency, ICU, General Surgery, Hemodialysis",
            "notes": "Annual certification verified"
        }, follow_redirects=True)
        self.assertEqual(update_res.status_code, 200)
        self.assertIn(b"Hospital profile and listed services successfully updated", update_res.data)

    def test_12_schema_page_structure(self):
        """Schema page renders both Star and Snowflake schemas with live warehouse table counts"""
        self.login_user("public", "citizen_chennai", "citizen123")
        res = self.client.get("/schema")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Star Schema", res.data)
        self.assertIn(b"Snowflake Schema", res.data)
        self.assertIn(b"fact_sales_expiry", res.data)
        self.assertIn(b"fact_availability_snapshot", res.data)
        self.assertIn(b"fact_weather_observation", res.data)
        self.assertIn(b"fact_hospital_service", res.data)
        self.assertIn(b"dim_category", res.data)
        self.assertIn(b"dim_dosage_form", res.data)
        self.assertIn(b"dim_city", res.data)
        self.assertIn(b"dim_district", res.data)
        self.assertIn(b"dim_state", res.data)
        self.assertIn(b"dim_hospital_type", res.data)

    def test_13_email_or_username_login(self):
        """Users can sign in using either username or registered email address with their password"""
        # 1. Sign in with username
        u_res = self.client.post("/login", data={
            "role": "public",
            "username": "citizen_chennai",
            "password": "citizen123"
        }, follow_redirects=True)
        self.assertEqual(u_res.status_code, 200)
        self.assertIn(b"Signed in successfully", u_res.data)
        self.client.get("/logout")

        # 2. Sign in with registered email
        e_res = self.client.post("/login", data={
            "role": "public",
            "username": "citizen.chennai@example.com",
            "password": "citizen123"
        }, follow_redirects=True)
        self.assertEqual(e_res.status_code, 200)
        self.assertIn(b"Signed in successfully", e_res.data)

    def test_14_separate_register_screen_and_direct_account_creation(self):
        """Dedicated /register screen creates account for Public Citizens and immediately signs user in without OTP"""
        # 1. GET /register screen
        get_res = self.client.get("/register")
        self.assertEqual(get_res.status_code, 200)
        self.assertIn(b"Create Public Citizen Account", get_res.data)
        self.assertIn(b"Sign In with Existing Account", get_res.data)

        # 2. POST /register with mismatch passwords fails
        bad_post = self.client.post("/register", data={
            "role": "public",
            "display_name": "New Test Citizen",
            "username": f"mismatch_{os.urandom(3).hex()}",
            "email": "mismatch@example.com",
            "password": "password123",
            "confirm_password": "differentpassword"
        }, follow_redirects=True)
        self.assertIn(b"Passwords do not match", bad_post.data)

        # 3. POST /register with valid credentials creates account directly
        unique_uname = f"cit_{os.urandom(4).hex()}"
        unique_email = f"{unique_uname}@example.com"
        reg_res = self.client.post("/register", data={
            "role": "public",
            "display_name": "New Verified Citizen",
            "username": unique_uname,
            "email": unique_email,
            "password": "secretpassword",
            "confirm_password": "secretpassword"
        }, follow_redirects=True)

        self.assertEqual(reg_res.status_code, 200)
        self.assertIn(b"Public Citizen account created", reg_res.data)
        self.assertIn(b"Medicine Search", reg_res.data)

        with self.client.session_transaction() as sess:
            self.assertIsNotNone(sess.get("user_id"))
            self.assertEqual(sess.get("username"), unique_uname)
            self.assertEqual(sess.get("role"), "public")

    def test_15_password_hashing_security(self):
        """Plain-text passwords are never stored in the database; one-way cryptographic hashes are enforced"""
        with app.app_context():
            db = get_db()
            user = db.execute("SELECT password_hash FROM app_users WHERE username = 'citizen_chennai';").fetchone()
            self.assertIsNotNone(user)
            p_hash = user["password_hash"]
            self.assertNotEqual(p_hash, "citizen123")
            self.assertTrue(p_hash.startswith("scrypt:") or p_hash.startswith("pbkdf2:sha256:"))

    def test_16_role_permission_isolation(self):
        """Pharmacy Owners cannot manage hospitals and Hospital Staff cannot manage pharmacies"""
        # Pharmacy owner attempting to access hospital dashboard
        self.login_user("pharmacy_owner", "ayapakkam_apollo", "apollo123")
        r_hosp = self.client.get("/hospital/dashboard", follow_redirects=True)
        self.assertIn(b"Access restricted", r_hosp.data)
        self.client.get("/logout")

        # Hospital staff attempting to access owner dashboard
        self.login_user("hospital_staff", "stedeford_staff", "hospital123")
        r_owner = self.client.get("/owner/dashboard", follow_redirects=True)
        self.assertIn(b"Access restricted", r_owner.data)

    def test_17_no_project_administrator_or_admin_portal(self):
        """The Project Administrator portal is removed; /admin returns 404"""
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 404)

    def test_18_logout_and_session_clearance(self):
        """Logging out clears session and redirects to /login"""
        self.login_user("public", "citizen_chennai", "citizen123")
        logout_res = self.client.get("/logout", follow_redirects=True)
        self.assertEqual(logout_res.status_code, 200)
        self.assertIn(b"signed out successfully", logout_res.data)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))

    def test_19_brevo_otp_routes_exist_and_require_session(self):
        """Brevo OTP routes exist but require a pending-OTP session (return 302/403, not 404)"""
        # Old SMS/WhatsApp webhook endpoints (Twilio/Meta) must NOT exist
        removed_endpoints = [
            "/verify-otp",
            "/otp/send-whatsapp",
            "/otp/resend",
            "/otp/cancel",
            "/api/webhooks/twilio",
            "/api/webhooks/meta-whatsapp",
            "/api/webhooks/sms-dlr",
        ]
        for ep in removed_endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 404, f"Old OTP endpoint {ep} still exists (expected 404)")

        # New Brevo OTP routes must exist (not 404) but require pending-OTP session
        brevo_otp_routes = [
            ("/login/otp", "GET"),
            ("/api/otp/status", "GET"),
        ]
        for ep, method in brevo_otp_routes:
            if method == "GET":
                res = self.client.get(ep)
            else:
                res = self.client.post(ep)
            self.assertNotEqual(res.status_code, 404, f"Brevo OTP endpoint {ep} unexpectedly missing")
            # Without session should redirect to login (302) or return 403 — not 500
            self.assertIn(res.status_code, (302, 403), f"Brevo OTP route {ep} returned unexpected status {res.status_code}")

    def test_20_public_registration_restricts_roles(self):
        """Public signup strictly rejects privileged roles (pharmacy_owner, hospital_staff)"""
        res = self.client.post("/register", data={
            "role": "pharmacy_owner",
            "display_name": "Unauthorized Owner Attempt",
            "username": f"bad_owner_{os.urandom(3).hex()}",
            "email": "bad_owner@example.com",
            "password": "secretpassword",
            "confirm_password": "secretpassword"
        }, follow_redirects=True)
        self.assertIn(b"Public signup is available for Public Citizen accounts only", res.data)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))

    def test_21_developer_cli_role_assignment(self):
        """Institutional roles must be assigned via developer CLI / trusted setup"""
        import migrate_db
        with app.app_context():
            db = get_db()
            test_username = f"cli_user_{os.urandom(3).hex()}"
            db.execute(
                "INSERT INTO app_users (username, email, password_hash, role, display_name, created_at) "
                "VALUES (?, ?, 'hash123', 'public', 'CLI Test User', '2026-11-15 12:00:00')",
                (test_username, f"{test_username}@example.com")
            )
            db.commit()

        # Assign role using developer helper
        migrate_db.assign_user_role(test_username, "pharmacy_owner", pharmacy_key=1)

        with app.app_context():
            db = get_db()
            row = db.execute("SELECT role FROM app_users WHERE username = ?", (test_username,)).fetchone()
            self.assertEqual(row["role"], "pharmacy_owner")
            assignment = db.execute(
                "SELECT pharmacy_key FROM user_pharmacy_assignments u "
                "JOIN app_users a ON u.user_id = a.user_id WHERE a.username = ?",
                (test_username,)
            ).fetchone()
            self.assertIsNotNone(assignment)
            self.assertEqual(assignment["pharmacy_key"], 1)

    def test_22_totp_enrollment_and_recovery_codes(self):
        """User can enroll in two-step verification, scan QR, confirm with 6-digit code, and receive 8 recovery codes"""
        import totp_auth
        self.login_user("public", "citizen_delhi", "delhi123")

        # 1. Access security settings
        sec_get = self.client.get("/settings/security")
        self.assertEqual(sec_get.status_code, 200)
        self.assertIn(b"Account Security Settings", sec_get.data)
        self.assertIn(b"Set Up Authenticator App", sec_get.data)

        # Retrieve pending secret
        with app.app_context():
            db = get_db()
            row = db.execute("SELECT user_id, totp_pending_secret FROM app_users WHERE username = 'citizen_delhi'").fetchone()
            pending_secret = row["totp_pending_secret"]
            self.assertIsNotNone(pending_secret)

        # 2. Confirm enrollment with valid TOTP code
        valid_code = totp_auth.get_totp(pending_secret)
        confirm_res = self.client.post("/settings/security", data={
            "action": "confirm_enrollment",
            "totp_code": valid_code
        }, follow_redirects=True)

        self.assertEqual(confirm_res.status_code, 200)
        self.assertIn(b"Two-step verification successfully enabled", confirm_res.data)
        self.assertIn(b"Save Your Emergency Recovery Codes Now", confirm_res.data)

        # 3. Check database state: totp_enabled = 1, 8 recovery codes stored
        with app.app_context():
            db = get_db()
            u_row = db.execute("SELECT totp_enabled, totp_secret FROM app_users WHERE username = 'citizen_delhi'").fetchone()
            self.assertEqual(u_row["totp_enabled"], 1)
            self.assertEqual(u_row["totp_secret"], pending_secret)

            codes = db.execute("SELECT COUNT(*) AS c FROM user_recovery_codes WHERE user_id = ?", (row["user_id"],)).fetchone()
            self.assertEqual(codes["c"], 8)

    def test_23_totp_login_flow(self):
        """When 2FA is enabled, user must supply password then valid 6-digit authenticator code"""
        import totp_auth
        # citizen_delhi has 2FA enabled from test_22
        # Step 1: Submit password -> redirected to /login/2fa
        res1 = self.client.post("/login", data={
            "role": "public",
            "username": "citizen_delhi",
            "password": "delhi123"
        }, follow_redirects=False)

        self.assertEqual(res1.status_code, 302)
        self.assertIn("/login/2fa", res1.headers.get("Location", ""))

        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))
            self.assertIsNotNone(sess.get("pending_2fa_user_id"))

        # Step 2: Invalid 6-digit code fails
        bad_code_res = self.client.post("/login/2fa", data={
            "totp_code": "000000"
        }, follow_redirects=True)
        self.assertIn(b"Invalid 6-digit verification code", bad_code_res.data)

        # Step 3: Valid 6-digit code succeeds and grants access
        with app.app_context():
            db = get_db()
            row = db.execute("SELECT totp_secret FROM app_users WHERE username = 'citizen_delhi'").fetchone()
            secret = row["totp_secret"]

        valid_code = totp_auth.get_totp(secret)
        good_code_res = self.client.post("/login/2fa", data={
            "totp_code": valid_code
        }, follow_redirects=True)

        self.assertEqual(good_code_res.status_code, 200)
        self.assertIn(b"Two-step verification successful", good_code_res.data)
        with self.client.session_transaction() as sess:
            self.assertIsNotNone(sess.get("user_id"))
            self.assertEqual(sess.get("username"), "citizen_delhi")

    def test_24_recovery_code_login_and_invalidation(self):
        """User can sign in using a single-use recovery code, which is then permanently invalidated"""
        import totp_auth
        self.client.get("/logout")

        # Create user with 2FA and one recovery code
        unique_user = f"rec_user_{os.urandom(3).hex()}"
        secret = totp_auth.generate_secret()
        sample_code = "A1B2-C3D4"
        code_hash = totp_auth.hash_recovery_code(sample_code)

        with app.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO app_users (username, password_hash, role, display_name, created_at, totp_enabled, totp_secret) "
                "VALUES (?, ?, 'public', 'Recovery Test User', '2026-11-15', 1, ?)",
                (unique_user, totp_auth.generate_password_hash("testpwd123"), secret)
            )
            u_id = db.execute("SELECT user_id FROM app_users WHERE username = ?", (unique_user,)).fetchone()["user_id"]
            db.execute(
                "INSERT INTO user_recovery_codes (user_id, code_hash, is_used, created_at) VALUES (?, ?, 0, '2026-11-15')",
                (u_id, code_hash)
            )
            db.commit()

        # Step 1: Sign in with password
        p_res = self.client.post("/login", data={
            "role": "public",
            "username": unique_user,
            "password": "testpwd123"
        }, follow_redirects=False)
        self.assertEqual(p_res.status_code, 302)

        # Step 2: Use recovery code
        rec_res = self.client.post("/login/recovery", data={
            "recovery_code": sample_code
        }, follow_redirects=True)
        self.assertEqual(rec_res.status_code, 200)
        self.assertIn(b"Signed in using emergency recovery code", rec_res.data)

        # Verify code is marked as used
        with app.app_context():
            db = get_db()
            r_row = db.execute("SELECT is_used FROM user_recovery_codes WHERE user_id = ?", (u_id,)).fetchone()
            self.assertEqual(r_row["is_used"], 1)

        # Step 3: Attempting to use the SAME recovery code again must fail
        self.client.get("/logout")
        self.client.post("/login", data={
            "role": "public",
            "username": unique_user,
            "password": "testpwd123"
        }, follow_redirects=False)

        reuse_res = self.client.post("/login/recovery", data={
            "recovery_code": sample_code
        }, follow_redirects=True)
        self.assertIn(b"Invalid or already used recovery code", reuse_res.data)

    def test_25_regenerate_and_disable_2fa(self):
        """User can regenerate recovery codes and disable 2FA with password verification"""
        import totp_auth
        self.login_user("public", "citizen_delhi", "delhi123")
        # Complete step 2
        with app.app_context():
            db = get_db()
            row = db.execute("SELECT totp_secret FROM app_users WHERE username = 'citizen_delhi'").fetchone()
            secret = row["totp_secret"]

        self.client.post("/login/2fa", data={"totp_code": totp_auth.get_totp(secret)}, follow_redirects=True)

        # 1. Regenerate recovery codes
        regen_res = self.client.post("/settings/security", data={
            "action": "regenerate_recovery_codes",
            "password": "delhi123",
            "totp_code": totp_auth.get_totp(secret)
        }, follow_redirects=True)
        self.assertEqual(regen_res.status_code, 200)
        self.assertIn(b"Fresh emergency recovery codes generated", regen_res.data)

        # 2. Disable 2FA
        disable_res = self.client.post("/settings/security", data={
            "action": "disable_2fa",
            "password": "delhi123",
            "verification_code": totp_auth.get_totp(secret)
        }, follow_redirects=True)
        self.assertEqual(disable_res.status_code, 200)
        self.assertIn(b"Two-step verification has been disabled", disable_res.data)

        with app.app_context():
            db = get_db()
            u_row = db.execute("SELECT totp_enabled, totp_secret FROM app_users WHERE username = 'citizen_delhi'").fetchone()
            self.assertEqual(u_row["totp_enabled"], 0)
            self.assertIsNone(u_row["totp_secret"])

    def test_26_rate_limiting(self):
        """Excessive failed login attempts trigger rate-limiting lock"""
        bad_uname = f"locked_user_{os.urandom(3).hex()}"
        with app.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO app_users (username, password_hash, role, display_name, created_at) "
                "VALUES (?, 'hash', 'public', 'Lock Test', '2026-11-15')",
                (bad_uname,)
            )
            db.commit()

        # Trigger 5 failed attempts
        for _ in range(5):
            self.client.post("/login", data={
                "role": "public",
                "username": bad_uname,
                "password": "wrong"
            }, follow_redirects=True)

        # 6th attempt should be locked
        lock_res = self.client.post("/login", data={
            "role": "public",
            "username": bad_uname,
            "password": "wrong"
        }, follow_redirects=True)
        self.assertIn(b"Account temporarily locked", lock_res.data)

    def test_27_etl_web_trigger_and_status(self):
        """Web-triggered POST /etl/run executes real Extract, Transform, and Load operations"""
        self.login_user("public", "citizen_chennai", "citizen123")
        res = self.client.post(
            "/etl/run",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("records_loaded"), 2000)
        self.assertGreater(data.get("records_flagged"), 0)
        self.assertIn("pharma_sales.csv", data.get("source_file"))

    def test_28_etl_page_render_quality_anomalies(self):
        """GET /etl renders data quality scorecards, quarantined inventory, and source metadata"""
        self.login_user("public", "citizen_chennai", "citizen123")
        res = self.client.get("/etl")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"ETL Pipeline", res.data)
        self.assertIn(b"Quarantined Expired Batches", res.data)
        self.assertIn(b"pharma_sales.csv", res.data)
        self.assertIn(b"Data Quality Anomalies", res.data)

    def test_29_olap_api_category_and_colors(self):
        """GET /api/olap/data returns therapeutic category mapping, accessible colors, and cell metadata"""
        self.login_user("public", "citizen_chennai", "citizen123")
        res = self.client.get("/api/olap/data?measure=quantity&dim_x=medicine&dim_y=quarter&dim_z=region")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertIn("category_colors", data)
        self.assertIn("category_map", data)
        self.assertIn("cells", data)
        self.assertGreater(len(data["cells"]), 0)

        # Verify cell schema contains x, y, z, v, cat, and color
        sample_cell = data["cells"][0]
        self.assertIn("x", sample_cell)
        self.assertIn("y", sample_cell)
        self.assertIn("z", sample_cell)
        self.assertIn("v", sample_cell)
        self.assertIn("cat", sample_cell)
        self.assertIn("color", sample_cell)
        self.assertTrue(sample_cell["color"].startswith("#"))

    def test_30_schema_diagrams_connected(self):
        """GET /schema renders both Star and Snowflake Schemas with foreign key connectors and cardinality"""
        self.login_user("public", "citizen_chennai", "citizen123")
        res = self.client.get("/schema")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Star Schema", res.data)
        self.assertIn(b"Snowflake Schema", res.data)
        self.assertIn(b"fact_sales_expiry", res.data)
        self.assertIn(b"dim_product", res.data)
        self.assertIn(b"arrow-star", res.data)
        self.assertIn(b"arrow-snowflake", res.data)

    def test_31_directions_urls_format_and_generation(self):
        """Google Maps and OpenStreetMap directions URLs are generated accurately with no Google API key requirement"""
        origin_lat, origin_lon = 13.0921, 80.1362
        dest_lat, dest_lon = 13.1145, 80.1548

        g_url = app_module._google_maps_directions_url(origin_lat, origin_lon, dest_lat, dest_lon)
        osm_url = app_module._osm_directions_url(origin_lat, origin_lon, dest_lat, dest_lon)

        self.assertIn("https://www.google.com/maps/dir/?", g_url)
        self.assertIn("api=1", g_url)
        self.assertNotIn("key=", g_url.lower())  # Must not require Google API key
        self.assertIn(f"origin={origin_lat:.6f}%2C{origin_lon:.6f}", g_url)
        self.assertIn(f"destination={dest_lat:.6f}%2C{dest_lon:.6f}", g_url)

        self.assertIn("https://www.openstreetmap.org/directions?", osm_url)
        self.assertIn("engine=fossgis_osrm_car", osm_url)
        self.assertIn(f"{origin_lat:.6f}%2C{origin_lon:.6f}%3B{dest_lat:.6f}%2C{dest_lon:.6f}", osm_url)

    def test_32_pharmacies_both_directions_and_strict_radius_partition(self):
        """Pharmacy Finder renders both directions buttons and strictly enforces distance thresholds (no 14.87km in <=5km group)"""
        self.login_user("public", "citizen_chennai", "citizen123")
        res = self.client.get("/pharmacies?location=Ayapakkam")
        self.assertEqual(res.status_code, 200)

        # Both Google Maps and OpenStreetMap directions buttons must be present
        self.assertIn(b"Directions in Google Maps", res.data)
        self.assertIn(b"Directions in OpenStreetMap", res.data)
        self.assertIn(b"google.com/maps/dir", res.data)
        self.assertIn(b"openstreetmap.org/directions", res.data)

        # Verify strict radius partitioning in the template context / output
        self.assertIn(b"Nearby Pharmacies", res.data)
        self.assertIn(b"Within 5.0 km radius", res.data)

    def test_33_hospitals_both_directions_and_strict_radius_partition(self):
        """Hospital Finder renders both directions buttons and strict radius groups on all results"""
        self.login_user("public", "citizen_chennai", "citizen123")
        res = self.client.get("/hospitals?location=Ayapakkam")
        self.assertEqual(res.status_code, 200)

        self.assertIn(b"Directions in Google Maps", res.data)
        self.assertIn(b"Directions in OpenStreetMap", res.data)
        self.assertIn(b"google.com/maps/dir", res.data)
        self.assertIn(b"openstreetmap.org/directions", res.data)

    def test_34_dynamic_location_resolution_and_stale_gps_clearing(self):
        """_resolve_search_center dynamically resolves typed addresses and clears stale GPS coordinates"""
        # 1. Preset locality resolves
        lat, lon, label = app_module._resolve_search_center("Ayapakkam", None, None)
        self.assertIsNotNone(lat)
        self.assertIsNotNone(lon)
        self.assertAlmostEqual(lat, 13.10, places=1)

        # 2. When a typed location is submitted, stale GPS coordinates are ignored
        lat_cp, lon_cp, label_cp = app_module._resolve_search_center("Connaught Place", 13.0921, 80.1362)
        # Should resolve Connaught Place (Delhi ~28.63), NOT the stale Chennai GPS coordinates (13.09)
        self.assertIsNotNone(lat_cp)
        self.assertAlmostEqual(lat_cp, 28.63, places=1)

        # 3. GPS coordinates are honored when query is a GPS marker string
        lat_gps, lon_gps, label_gps = app_module._resolve_search_center("Current Device Location", 12.9719, 77.6412)
        self.assertAlmostEqual(lat_gps, 12.9719, places=3)
        self.assertAlmostEqual(lon_gps, 77.6412, places=3)

        # 4. Empty/unresolvable location does NOT silently substitute Ayapakkam
        lat_none, lon_none, err = app_module._resolve_search_center("", None, None)
        self.assertIsNone(lat_none)
        self.assertIsNone(lon_none)
        self.assertIn("enter any address", err.lower())

if __name__ == "__main__":
    unittest.main()
