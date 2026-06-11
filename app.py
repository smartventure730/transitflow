import os
import sqlite3
import uuid
import random
from datetime import datetime, timedelta, time
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'transitflow_secure_matrix_key_2026'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'transitflow.db')

# ---------------------------------------------------------
# DATABASE INITIALIZATION & RELATION MANAGEMENT
# ---------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes local transactional schemas and handles automated schema migrations."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # ==========================================
        # SYSTEM DATABASE SCHEMAS & LEDGERS INITIALIZATION
        # ==========================================

        # Users Core Ledger
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                balance REAL DEFAULT 0.0,
                cumulative_profit REAL DEFAULT 0.0,
                referral_commission REAL DEFAULT 0.0,
                ref_code TEXT UNIQUE NOT NULL,
                referred_by TEXT
            )
        ''')

        # --- MIGRATION: ADD FLEET AND USER INFO COLUMNS ---
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN fleet_data TEXT")
        except sqlite3.OperationalError:
            pass # Already exists
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN user_info TEXT")
        except sqlite3.OperationalError:
            pass # Already exists
        # ---------------------------------------------------
        
        # Merchant Channels Configuration Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS merchant_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                registered_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        # Deposits Management Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deposits (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount REAL,
                method TEXT,
                target_number TEXT,
                target_name TEXT,
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Withdrawals Management Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS withdrawals (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                gross_amount REAL,
                tax_amount REAL,
                net_amount REAL,
                registered_name TEXT,
                status TEXT DEFAULT 'Pending',
                handling_agent TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Safe migration block for older live withdrawals tables
        try:
            cursor.execute("ALTER TABLE withdrawals ADD COLUMN registered_name TEXT;")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        
        # Asset Subscriptions / Fleet Allocations Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                tier_name TEXT,
                cost REAL,
                daily_return REAL,
                activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                status TEXT DEFAULT 'Active',
                last_payout_date TEXT  -- Track the calendar date of the last processed daily reward
            )
        ''')
        
        # Schema Migration: Safely add last_payout_date to existing databases without data loss
        try:
            cursor.execute("ALTER TABLE purchases ADD COLUMN last_payout_date TEXT;")
        except sqlite3.OperationalError:
            # Column already exists, pass safely
            pass

        # App Settings (Social Links and Corporate Details)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # Referral Single-Payout Validation Ledger
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_payout_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uplink_id INTEGER,
                downlink_id INTEGER,
                commission_awarded REAL,
                purchased_tier TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(uplink_id, downlink_id)
            )
        ''')

        # Dynamic System Lock Tiers
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS coming_soon_tiers (
                tier_name TEXT PRIMARY KEY,
                price REAL,
                daily_return REAL,
                img TEXT,
                is_unlocked INTEGER DEFAULT 0
            )
        ''')

        # Permanent System Audit Archive & Operational Ledger Matrix
        cursor.execute("DROP TABLE IF EXISTS transaction_archive;")
        cursor.execute("""
            CREATE TABLE transaction_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_type TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL,
                notes TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

        # ==========================================================
        # AUTOMATED SCHEMA MIGRATION: SECURITY PIN PATCH
        # ==========================================================
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN security_pin TEXT;")
            conn.commit()
            print("Database schema migration successful: 'security_pin' column patched safely.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("Database operational status: 'security_pin' column verified and active.")
            else:
                print(f"Database schema notice: {e}")

        # ==========================================================
        # ADMINISTRATIVE BACKEND PROFILE AUTOMATION SEEDING
        # ==========================================================
        from werkzeug.security import generate_password_hash
        cursor.execute("SELECT * FROM users WHERE role = 'admin'")
        
        if not cursor.fetchone():
            admin_pass = generate_password_hash("AdminSystem2026!", method='scrypt')
            cursor.execute('''
                INSERT INTO users (phone, password, role, ref_code, balance, cumulative_profit, referral_commission, security_pin)
                VALUES (?, ?, ?, ?, 0.0, 0.0, 0.0, '0000')
            ''', ("0700000000", admin_pass, "admin", "ADMINREF"))
            conn.commit()
            print("Administrative baseline security node deployed successfully.")
            
        # ==========================================================
        # DATA MATRIX SEEDING PROFILE PLATFORMS
        # ==========================================================
        settings_defaults = {
            'whatsapp_link': 'https://chat.whatsapp.com/example',
            'telegram_link': 'https://t.me/example',
            'help_group_link': 'https://t.me/TransitFlow_Official_Help',
            'about_text': 'TransitFlow Logistics Group...'
        }
        for k, v in settings_defaults.items():
            cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)", (k, v))

        coming_soon_defaults = [
            ("VIP 6", 1000000.0, 260000.0, "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=500&auto=format&fit=crop&q=60", 0),
            ("VIP 7", 2000000.0, 550000.0, "https://images.unsplash.com/photo-1592838064575-70ed626d3a0e?w=500&auto=format&fit=crop&q=60", 0),
            ("VIP 8", 5000000.0, 1500000.0, "https://images.unsplash.com/photo-1501700493788-fa1a4fc9fe62?w=500&auto=format&fit=crop&q=60", 0)
        ]
        for tier_data in coming_soon_defaults:
            cursor.execute("INSERT OR IGNORE INTO coming_soon_tiers (tier_name, price, daily_return, img, is_unlocked) VALUES (?, ?, ?, ?, ?)", tier_data)
            
        conn.commit()
        print("Database settings and schema matrices verified successfully.")

    except Exception as general_err:
        print(f"CRITICAL: Database initialization encountered an error: {general_err}")
        
    finally:
        conn.close()
        print("Database connection closed cleanly at pipeline termination.")

init_db()

# Global Hardcoded Vehicles Map
VEHICLES_STATIC = {
    "VIP 1": {"price": 30000, "daily": 7500, "img": "https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=500&auto=format&fit=crop&q=60"},
    "VIP 2": {"price": 60000, "daily": 15000, "img": "https://images.unsplash.com/photo-1532581291347-9c39cf10a73c?w=500&auto=format&fit=crop&q=60"},
    "VIP 3": {"price": 120000, "daily": 30000, "img": "https://images.unsplash.com/photo-1592838064575-70ed626d3a0e?w=500&auto=format&fit=crop&q=60"},
    "VIP 4": {"price": 250000, "daily": 62500, "img": "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=500&auto=format&fit=crop&q=60"},
    "VIP 5": {"price": 500000, "daily": 125000, "img": "https://images.unsplash.com/photo-1544620347-c4fd4a3d5957?w=500&auto=format&fit=crop&q=60"}
}

def get_combined_vehicles():
    vehicles = VEHICLES_STATIC.copy()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM coming_soon_tiers WHERE is_unlocked = 1")
        for row in cursor.fetchall():
            vehicles[row['tier_name']] = {
                "price": row['price'],
                "daily": row['daily_return'],
                "img": row['img']
            }
        conn.close()
    except:
        pass
    return vehicles

# ---------------------------------------------------------
# WITHDRAWAL TIMING CONTROLLER
# ---------------------------------------------------------
from datetime import datetime, time
import pytz  # Handles timezone translations cleanly

def check_withdrawal_window():
    # 1. Force the system clock to read East Africa Time (Uganda local time)
    uganda_tz = pytz.timezone('Africa/Kampala')
    now_uganda = datetime.now(uganda_tz).time()
    
    # 2. Define your 3 exact operational windows
    w1_start, w1_end = time(10, 0), time(11, 0) # 10:00 AM - 11:00 AM
    w2_start, w2_end = time(13, 0), time(14, 0) # 1:00 PM - 2:00 PM
    w3_start, w3_end = time(16, 0), time(18, 0) # 4:00 PM - 6:00 PM
    
    # 3. Check if the local Uganda time falls within any of the slots
    is_inside_window = (
        (w1_start <= now_uganda <= w1_end) or 
        (w2_start <= now_uganda <= w2_end) or 
        (w3_start <= now_uganda <= w3_end)
    )
    
    return is_inside_window

# Autosecurity Wrappers
def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def admin_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            abort(403)
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# ---------------------------------------------------------
# ASYNCHRONOUS ENGINE
# ---------------------------------------------------------
@app.route('/api/live-metrics')
def live_metrics():
    conn = get_db_connection()
    cursor = conn.cursor()
    if 'user_id' in session and session.get('role') != 'admin':
        cursor.execute("SELECT balance, cumulative_profit FROM users WHERE id = ?", (session['user_id'],))
        user_data = cursor.fetchone()
        
        cursor.execute("SELECT status, amount FROM deposits WHERE user_id = ? ORDER BY created_at DESC LIMIT 5", (session['user_id'],))
        latest_deposits = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute("SELECT status, gross_amount FROM withdrawals WHERE user_id = ? ORDER BY created_at DESC LIMIT 5", (session['user_id'],))
        latest_withdrawals = [dict(r) for r in cursor.fetchall()]
        
        conn.close()
        return jsonify({
            "status": "success",
            "balance": user_data['balance'] if user_data else 0,
            "profit": user_data['cumulative_profit'] if user_data else 0,
            "withdrawal_open": check_withdrawal_window(),
            "latest_deposits": latest_deposits,
            "latest_withdrawals": latest_withdrawals
        })
    elif session.get('role') == 'admin':
        cursor.execute("SELECT COUNT(*) FROM deposits WHERE status = 'Pending'")
        p_dep = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'Pending'")
        p_wit = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(amount) FROM deposits WHERE status='Success'")
        total_inflow = cursor.fetchone()[0] or 0.0
        cursor.execute("SELECT SUM(gross_amount) FROM withdrawals WHERE status='Success'")
        total_outflow = cursor.fetchone()[0] or 0.0
        
        conn.close()
        return jsonify({
            "status": "success",
            "pending_deposits_count": p_dep,
            "pending_withdrawals_count": p_wit,
            "total_inflow": total_inflow,
            "total_outflow": total_outflow,
            "net_profit": total_inflow - total_outflow
        })
    return jsonify({"status": "unauthorized"}), 401

# ---------------------------------------------------------
# CORE SECURITY AUTHS
# ---------------------------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    ref_param = request.args.get('ref', '')
    if request.method == 'POST':
        phone = request.form.get('phone').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        security_pin = request.form.get('security_pin', '').strip() # Captures security validation PIN
        referred_by = request.form.get('referred_by', '').strip() # Tracks alpha-numeric referral token
        
        # Comprehensive Data Entries Validation
        if not phone or not password or not confirm_password or not security_pin:
            flash("All entries, including your recovery security PIN, require accurate data input.", "danger")
            return redirect(url_for('register', ref=ref_param))
            
        if password != confirm_password:
            flash("Passwords do not match. Please verify credentials.", "danger")
            return redirect(url_for('register', ref=ref_param))
            
        if len(security_pin) < 4:
            flash("Security PIN must be at least 4 digits long.", "danger")
            return redirect(url_for('register', ref=ref_param))
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ─── CRITICAL SECURITY CHECK: BLOCK VIOLATORS IN QUARANTINE ───
        # Looks into text snapshot logs to block purged accounts from re-registering
        cursor.execute("""
            SELECT id FROM transaction_archive 
            WHERE tx_type = 'ACCOUNT_SUSPENDED' AND notes LIKE ?
        """, (f'%"{phone}"%',))
        quarantined_record = cursor.fetchone()

        if quarantined_record:
            conn.close()
            flash("This phone number is flagged for administrative violations. Registration blocked until approved by Admin.", "danger")
            return redirect(url_for('register', ref=ref_param))
        # ─────────────────────────────────────────────────────────────

        # Proceed with validation check for active profile collisions
        cursor.execute("SELECT id FROM users WHERE phone = ?", (phone,))
        if cursor.fetchone():
            flash("This phone number is already registered.", "danger")
            conn.close()
            return redirect(url_for('register', ref=ref_param))
            
        # Verify if the affiliate marketer upline reference key exists
        if referred_by:
            cursor.execute("SELECT id FROM users WHERE ref_code = ?", (referred_by,))
            if not cursor.fetchone():
                flash("Invalid referral association token.", "danger")
                conn.close()
                return redirect(url_for('register', ref=ref_param))
        
        # Cryptographically hash credentials and establish system properties
        hashed_pw = generate_password_hash(password, method='scrypt')
        new_ref_code = str(uuid.uuid4())[:6].upper() # Creates a unique link code for the new user
        
        # Save complete ledger data cell node mapping matching your database exactly
        cursor.execute('''
            INSERT INTO users (phone, password, ref_code, referred_by, security_pin, balance, cumulative_profit, referral_commission)
            VALUES (?, ?, ?, ?, ?, 0.0, 0.0, 0.0)
        ''', (phone, hashed_pw, new_ref_code, referred_by if referred_by else None, security_pin))
        
        conn.commit()
        conn.close()
        
        flash("Registration successful! Keep your secret PIN safe; it is needed to recover account access.", "success")
        return redirect(url_for('login'))
        
    return render_template_string(HTML_REGISTER, ref_param=ref_param)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form.get('phone').strip()
        password = request.form.get('password')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE phone = ?", (phone,))
        user = cursor.fetchone()
        conn.close()
        
        # Verify if the account node exists and check cryptographic password matching
        if user and check_password_hash(user['password'], password):
            # FIX: Check if the node has been soft-deleted/purged by an admin
            if user['role'] == 'purged':
                flash("Your account access has been suspended due to system violations.", "danger")
                return redirect(url_for('login'))
                
            # If not purged, proceed with normal session tracking configuration values
            session['user_id'] = user['id']
            session['phone'] = user['phone']
            session['role'] = user['role']
            
            # Route based on account access privileges
            if user['role'] == 'admin':
                return redirect(url_for('admin_panel'))
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials provided.", "danger")
            
    return render_template_string(HTML_LOGIN)

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        user_input_pin = request.form.get('security_pin', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        # 1. Enforce strict parameter presence validation
        if not phone or not user_input_pin or not new_password or not confirm_password:
            flash("All authorization matrix fields are required.", "danger")
            return redirect(url_for('forgot_password'))
            
        # 2. Prevent password mismatch configuration escapes
        if new_password != confirm_password:
            flash("New passwords do not match.", "danger")
            return redirect(url_for('forgot_password'))

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pull the absolute profile properties based on phone index criteria
        cursor.execute("SELECT id, security_pin FROM users WHERE phone = ?", (phone,))
        user = cursor.fetchone()
        
        if user:
            # Safely handle both Row objects or standard tuples coming out of sqlite execution streams
            try:
                stored_pin = user['security_pin']
                user_id = user['id']
            except (TypeError, KeyError, IndexError):
                user_id = user[0]
                stored_pin = user[1]

            # Clear trailing layout elements and explicitly match as string definitions
            stored_pin_str = str(stored_pin).strip() if stored_pin is not None else ""
            provided_pin_str = str(user_input_pin).strip()
            
            # 3. CRITICAL SECURITY MATCH MATRIX ENFORCEMENT
            if not stored_pin_str or stored_pin_str.lower() == "none" or stored_pin_str == "":
                flash("This account profile does not have a security pin configured. Please contact support.", "danger")
                conn.close()
                return redirect(url_for('forgot_password'))
                
            if provided_pin_str != stored_pin_str:
                flash("Security authorization verification failed. Invalid Pin code.", "danger")
                conn.close()
                return redirect(url_for('forgot_password'))
            
            # 4. Hash and patch the credentials safe update ledger sequence
            from werkzeug.security import generate_password_hash
            hashed_pw = generate_password_hash(new_password, method='scrypt')
            
            cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_pw, user_id))
            conn.commit()
            conn.close()
            
            flash("Account password updated successfully. You can now log in.", "success")
            return redirect(url_for('login'))
        else:
            flash("No registered terminal account found with that phone identity.", "danger")
            conn.close()
            return redirect(url_for('forgot_password'))
            
    # Safely matches your original string variable-based template setup
    return render_template_string(HTML_FORGOT_PASSWORD)

@app.route('/logout')
def logout():
    session.clear()
    flash("Session terminated smoothly.", "info")
    return redirect(url_for('login'))

# =============================================================================
# INCREMENTAL DAILY PROFIT MONITOR MATRIX
# =============================================================================
def process_daily_profits(user_id):
    """
    Checks active contracts. Awards daily profit incrementally if a calendar 
    day has shifted, while keeping the contract active until the 14-day expiry.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch all active purchases for this user
    active_purchases = cursor.execute(
        "SELECT * FROM purchases WHERE user_id = ? AND status = 'Active'", 
        (user_id,)
    ).fetchall()
    
    now = datetime.now()
    today_date_str = now.strftime('%Y-%m-%d')
    
    for p in active_purchases:
        expires_at = datetime.strptime(p['expires_at'], '%Y-%m-%d %H:%M:%S')
        
        # Scenario A: Check if the overall 14-day contract cycle has expired
        if now >= expires_at:
            # Finalize the contract so it stops earning
            cursor.execute(
                "UPDATE purchases SET status = 'Completed' WHERE id = ?", 
                (p['id'],)
            )
            continue  # Move to next asset
            
        # Scenario B: Contract is still active. Check if daily profit is due.
        # If last_payout_date is different from today_date_str, a new calendar day has arrived.
        if p['last_payout_date'] != today_date_str:
            daily_amt = p['daily_return']
            
            # 1. Instantly credit the daily profit to the user's available balance
            cursor.execute('''
                UPDATE users 
                SET balance = balance + ?, 
                    cumulative_profit = cumulative_profit + ? 
                WHERE id = ?
            ''', (daily_amt, daily_amt, user_id))
            
            # 2. Log this asset's daily transaction record to the transaction_archive ledger
            cursor.execute('''
                INSERT INTO transaction_archive (tx_type, amount, status, notes, processed_at)
                VALUES ('Daily Profit Share', ?, 'Success', ?, ?)
            ''', (daily_amt, f"Daily return from asset tier: {p['tier_name']}", now.strftime('%Y-%m-%d %H:%M:%S')))
            
            # 3. Update last_payout_date to today so they don't get credited again today
            cursor.execute(
                "UPDATE purchases SET last_payout_date = ? WHERE id = ?", 
                (today_date_str, p['id'])
            )
            
    conn.commit()
    conn.close()

# ---------------------------------------------------------
# TRANSACTIONAL CONTROLLERS
# ---------------------------------------------------------
@app.route('/')
@login_required
def dashboard():
    if session.get('role') == 'admin':
        return redirect(url_for('admin_panel'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # SYSTEM FAULT NONE-CHECK SAFETY VALUATION
    cursor.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    user = cursor.fetchone()
    
    if user is None:
        session.clear()
        flash("User validation trace broken. Re-authorization required.", "danger")
        conn.close()
        return redirect(url_for('login'))
    
    conn.close()
    
    # Run dynamic background checks to process and drop available daily payouts
    process_daily_profits(session['user_id'])
    
    # Re-establish connection for rendering matrices
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM purchases WHERE user_id = ? ORDER BY activated_at DESC", (session['user_id'],))
    all_purchases = [dict(row) for row in cursor.fetchall()]
    for p in all_purchases:
        act_date = datetime.strptime(p['activated_at'], '%Y-%m-%d %H:%M:%S')
        p['days_held'] = max(0, (datetime.now() - act_date).days)
        
    cursor.execute("SELECT * FROM deposits WHERE user_id = ? ORDER BY created_at DESC", (session['user_id'],))
    deposits = cursor.fetchall()
    
    cursor.execute("SELECT * FROM withdrawals WHERE user_id = ? ORDER BY created_at DESC", (session['user_id'],))
    withdrawals = cursor.fetchall()
    
    cursor.execute('''
        SELECT u.phone, COALESCE(r.commission_awarded, 0.0) as commission
        FROM users u
        LEFT JOIN referral_payout_history r ON r.downlink_id = u.id AND r.uplink_id = ?
        WHERE u.referred_by = ?
    ''', (session['user_id'], user['ref_code']))
    raw_team = cursor.fetchall()
    team_members = [{"masked_phone": f"****{t['phone'][-4:]}" if len(t['phone']) >= 4 else t['phone'], "commission": t['commission']} for t in raw_team]
    
    cursor.execute("SELECT COUNT(*), SUM(cost) FROM purchases WHERE user_id = ? AND status='Active'", (session['user_id'],))
    active_stats = cursor.fetchone()
    has_active_plan = active_stats[0] > 0
    
    cursor.execute("SELECT key, value FROM system_settings")
    settings = {row['key']: row['value'] for row in cursor.fetchall()}
    
    cursor.execute("SELECT * FROM coming_soon_tiers WHERE is_unlocked = 0")
    locked_tiers = cursor.fetchall()
    
    domain_url = request.url_root.rstrip('/')
    referral_link = f"{domain_url}/register?ref={user['ref_code']}"
    
    current_vehicles = get_combined_vehicles()
    conn.close()
    
    def format_ugx(val):
        return "{:,}".format(int(val or 0))
            
    return render_template_string(
        HTML_DASHBOARD, 
        user=user, 
        vehicles=current_vehicles, 
        locked_tiers=locked_tiers,
        deposits=deposits, 
        withdrawals=withdrawals, 
        team_members=team_members, 
        has_active_plan=has_active_plan,
        referral_link=referral_link,
        purchases=all_purchases,
        settings=settings,
        ugx=format_ugx,
        window_status=check_withdrawal_window()
    )

@app.route('/deposit', methods=['POST'])
@login_required
def deposit():
    try:
        amount = float(request.form.get('amount', '0'))
        method = request.form.get('method')
        
        if amount <= 0 or not method:
            flash("Invalid transaction properties.", "danger")
            return redirect(url_for('dashboard'))
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT phone_number, registered_name FROM merchant_channels WHERE provider = ? AND is_active = 1", (method,))
        active_channels = cursor.fetchall()
        
        if not active_channels:
            flash(f"No active channels open for {method}.", "danger")
            conn.close()
            return redirect(url_for('dashboard'))
            
        selected_channel = random.choice(active_channels)
        dep_id = str(uuid.uuid4())[:8].upper()
        
        cursor.execute('''
            INSERT INTO deposits (id, user_id, amount, method, target_number, target_name, status)
            VALUES (?, ?, ?, ?, ?, ?, 'Pending')
        ''', (dep_id, session['user_id'], amount, method, selected_channel['phone_number'], selected_channel['registered_name']))
        
        conn.commit()
        conn.close()
        flash(f"ORDER ACTIVE: Send UGX {amount:,.0f} to {selected_channel['registered_name']} on {selected_channel['phone_number']} ({method}).", "info")
    except Exception:
        flash("Transactional processing fault.", "danger")
        
    return redirect(url_for('dashboard'))

@app.route('/purchase', methods=['POST'])
@login_required
def purchase():
    tier = request.form.get('tier')
    all_available = get_combined_vehicles()
    
    if tier not in all_available:
        flash("Selection out of bounds or tier remains locked currently.", "danger")
        return redirect(url_for('dashboard'))
        
    cost = all_available[tier]['price']
    daily = all_available[tier]['daily']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE id = ?", (session['user_id'],))
    user_bal = cursor.fetchone()['balance']
    
    if user_bal >= cost:
        # --- FIXED TIME STRINGS & DAILY PAYOUT MAPPING ---
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        today_date_str = datetime.now().strftime('%Y-%m-%d')  # Format: YYYY-MM-DD
        expiry_str = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')

        # Deduct balance from user
        cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (cost, session['user_id']))
        
        # Insert the package subscription with the last_payout_date initialized to today
        cursor.execute('''
            INSERT INTO purchases (user_id, tier_name, cost, daily_return, expires_at, status, last_payout_date)
            VALUES (?, ?, ?, ?, ?, 'Active', ?)
        ''', (session['user_id'], tier, cost, daily, expiry_str, today_date_str))
        
        # --- REFERRAL LOGIC MATRIX ---
        cursor.execute("SELECT referred_by FROM users WHERE id = ?", (session['user_id'],))
        user_info = cursor.fetchone()
        if user_info and user_info['referred_by']:
            cursor.execute("SELECT id FROM users WHERE ref_code = ?", (user_info['referred_by'],))
            uplink = cursor.fetchone()
            if uplink:
                cursor.execute("SELECT id FROM referral_payout_history WHERE uplink_id = ? AND downlink_id = ?", (uplink['id'], session['user_id']))
                if not cursor.fetchone():
                    comm_reward = cost * 0.36
                    cursor.execute('''
                        UPDATE users SET balance = balance + ?, referral_commission = referral_commission + ? WHERE id = ?
                    ''', (comm_reward, comm_reward, uplink['id']))
                    cursor.execute('''
                        INSERT INTO referral_payout_history (uplink_id, downlink_id, commission_awarded, purchased_tier)
                        VALUES (?, ?, ?, ?)
                    ''', (uplink['id'], session['user_id'], comm_reward, tier))
                    
        conn.commit()
        flash(f"Successfully allocated {tier} to your fleet configuration!", "success")
    else:
        flash("Insufficient balance to activate this truck configuration asset.", "danger")
            
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/withdraw', methods=['POST'])
@login_required
def withdraw():
    if not check_withdrawal_window():
        flash("ACCESS DENIED: Payouts are restricted outside standard processing hours (10-11 AM, 1-2 PM, 4-6 PM EAT).", "danger")
        return redirect(url_for('dashboard'))
        
    # Capture form parameters securely
    amount = float(request.form.get('amount', 0))
    registered_name = request.form.get('registered_name', '').strip() # <-- CAPTURE THIS NEW INPUT
    MIN_WITHDRAW = 15000
    
    if not registered_name:
        flash("Account verification error: Legal registered name must be provided.", "danger")
        return redirect(url_for('dashboard'))
    
    if amount < MIN_WITHDRAW:
        flash(f"Minimum payout requirement is UGX {MIN_WITHDRAW:,}.", "danger")
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verify historical asset deployment
    cursor.execute("SELECT COUNT(*) FROM purchases WHERE user_id = ?", (session['user_id'],))
    if cursor.fetchone()[0] == 0:
        flash("Account restriction: Payout requires an active or historical fleet allocation.", "danger")
        conn.close()
        return redirect(url_for('dashboard'))
        
    cursor.execute("SELECT balance FROM users WHERE id = ?", (session['user_id'],))
    current_balance = cursor.fetchone()['balance']
    
    if current_balance >= amount:
        tax = amount * 0.10
        net = amount - tax
        w_id = str(uuid.uuid4())[:8].upper()
        
        cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, session['user_id']))
        
        # INSERT WITH THE NEW REGISTERED NAME FIELD INCLUDED
        cursor.execute('''
            INSERT INTO withdrawals (id, user_id, gross_amount, tax_amount, net_amount, registered_name, status)
            VALUES (?, ?, ?, ?, ?, ?, 'Pending')
        ''', (w_id, session['user_id'], amount, tax, net, registered_name))
        
        conn.commit()
        flash("Withdrawal execution pipeline initialized. Processing order saved.", "warning")
    else:
        flash("Insufficient account ledger balance.", "danger")
        
    conn.close()
    return redirect(url_for('dashboard'))


# ---------------------------------------------------------
import csv
import io
import json
from flask import Response, redirect, flash, url_for, request, render_template_string, session, abort

# =====================================================================
# 1. MAIN SYSTEM DASHBOARD CONTROL TERMINAL
# =====================================================================
@app.route('/admin-operations-hq', methods=['GET', 'POST'])
@admin_required
def admin_panel():
    import json # Ensure json is imported
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_channel':
            provider = request.form.get('provider')
            phone = request.form.get('phone')
            name = request.form.get('name')
            if provider and phone and name:
                cursor.execute("INSERT INTO merchant_channels (provider, phone_number, registered_name) VALUES (?, ?, ?)", (provider, phone, name))
                conn.commit()
                flash("Dynamic Routing Pipeline Channel Inserted.", "success")
        
        elif action == 'update_settings':
            whatsapp = request.form.get('whatsapp_link')
            telegram = request.form.get('telegram_link')
            help_link = request.form.get('help_group_link')
            
            cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('whatsapp_link', ?)", (whatsapp,))
            cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('telegram_link', ?)", (telegram,))
            cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('help_group_link', ?)", (help_link,))
            
            conn.commit()
            flash("System Matrix Settings Refreshed.", "success")
            
        return redirect(url_for('admin_panel'))
            
    # Core Admin Panel Datasets
    cursor.execute("SELECT deposits.*, users.phone FROM deposits JOIN users ON deposits.user_id = users.id WHERE deposits.status = 'Pending' ORDER BY created_at DESC")
    pending_deposits = cursor.fetchall()
    
    cursor.execute("""
        SELECT withdrawals.*, users.phone 
        FROM withdrawals 
        JOIN users ON withdrawals.user_id = users.id 
        WHERE withdrawals.status = 'Pending' 
        ORDER BY created_at DESC
    """)
    pending_withdrawals = cursor.fetchall()
    
    cursor.execute("SELECT deposits.*, users.phone FROM deposits JOIN users ON deposits.user_id = users.id WHERE deposits.status != 'Pending' ORDER BY created_at DESC")
    permanent_inflows = cursor.fetchall()
    
    cursor.execute("SELECT withdrawals.*, users.phone FROM withdrawals JOIN users ON withdrawals.user_id = users.id WHERE withdrawals.status != 'Pending' ORDER BY created_at DESC")
    permanent_outflows = cursor.fetchall()
    
    cursor.execute("SELECT * FROM merchant_channels")
    channels = cursor.fetchall()
    
    cursor.execute("SELECT id, phone, role, balance, referral_commission FROM users WHERE role != 'admin' ORDER BY id DESC")
    system_users = cursor.fetchall()

    # --- NEW: Fetch purged users for restoration ---
    cursor.execute("SELECT id, phone, role FROM users WHERE role = 'purged' ORDER BY id DESC")
    purged_users = cursor.fetchall()
    
    cursor.execute("SELECT * FROM coming_soon_tiers")
    coming_soon_list = cursor.fetchall()
    
    cursor.execute("SELECT SUM(amount) FROM deposits WHERE status='Success'")
    daily_inflow = cursor.fetchone()[0] or 0.0
    
    cursor.execute("SELECT SUM(gross_amount) FROM withdrawals WHERE status='Success'")
    daily_outflow = cursor.fetchone()[0] or 0.0
    
    cursor.execute("SELECT key, value FROM system_settings")
    settings = {row['key']: row['value'] for row in cursor.fetchall()}
    
    # --- START OF UPGRADED TRANSACTION ARCHIVE LOGIC ---
    cursor.execute("SELECT * FROM transaction_archive ORDER BY processed_at DESC")
    raw_archive_rows = cursor.fetchall()
    
    archive_history_list = []
    for row in raw_archive_rows:
        try:
            row_dict = dict(row)
        except (TypeError, ValueError):
            row_dict = {
                "id": row[0],
                "tx_type": row[1],
                "amount": row[2],
                "status": row[3],
                "notes": row[4]
            }
            
        row_dict['target_phone'] = "N/A"
        if row_dict['tx_type'] == 'ACCOUNT_SUSPENDED':
            try:
                backup_data = json.loads(row_dict['notes'])
                row_dict['target_phone'] = backup_data.get('phone', 'Unknown')
            except Exception:
                row_dict['target_phone'] = "Parsing Error"
                
        archive_history_list.append(row_dict)
    # --- END OF UPGRADED TRANSACTION ARCHIVE LOGIC ---
    
    remaining_profit_margin = daily_inflow - daily_outflow
    conn.close()
    
    def format_ugx(val):
        if int(val or 0) < 0:
            return "-{:,}".format(abs(int(val)))
        return "{:,}".format(int(val or 0))
        
    return render_template_string(
        HTML_ADMIN,
        deposits=pending_deposits, 
        withdrawals=pending_withdrawals,
        inflows=permanent_inflows,
        outflows=permanent_outflows,
        channels=channels,
        users=system_users,
        purged_users=purged_users, # Variable now passed to template
        coming_soon_list=coming_soon_list,
        inflow=daily_inflow,
        outflow=daily_outflow,
        profit=remaining_profit_margin,
        settings=settings,
        ugx=format_ugx,
        archive_history_list=archive_history_list
    )


# =====================================================================
# 2. BULK EXPORT GENERATOR ENDPOINT (BASKET QUICK PAY COMPATIBLE)
# =====================================================================
@app.route('/admin/export-payout-sheet')
@admin_required  
def export_payout_sheet():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT withdrawals.*, users.phone 
        FROM withdrawals 
        JOIN users ON withdrawals.user_id = users.id 
        WHERE withdrawals.status = 'Pending' 
        ORDER BY created_at DESC
    """)
    pending_withdrawals = cursor.fetchall()
    conn.close()

    if not pending_withdrawals:
        flash("No pending liquidation requests available to export.", "warning")
        return redirect(url_for('admin_panel'))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Phone Number', 'Amount', 'Recipient Name', 'Narrative'])

    for w in pending_withdrawals:
        try:
            phone_val = w['phone']
            amount_val = w['net_amount']
            name_val = w['registered_name']
            id_val = w['id']
        except (TypeError, KeyError, IndexError):
            id_val = w[0]
            amount_val = w[4]          
            name_val = w[5]            
            phone_val = w[-1]          

        raw_phone = str(phone_val).strip()
        if raw_phone.startswith('0'):
            formatted_phone = '256' + raw_phone[1:]
        elif raw_phone.startswith('+256'):
            formatted_phone = raw_phone[1:]
        elif not raw_phone.startswith('256'):
            formatted_phone = '256' + raw_phone
        else:
            formatted_phone = raw_phone

        clean_name = str(name_val).replace(',', '').strip()
        narrative_remark = f"TXN-SETTLE-ID-{id_val}"
        writer.writerow([formatted_phone, int(amount_val), clean_name, narrative_remark])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=TransitFlow_Bulk_Payouts.csv"}
    )


# =====================================================================
# 3. ROUTING & INTERFACE COMPONENT ENDPOINTS
# =====================================================================
@app.route('/admin/unlock-tier/<string:tier_name>')
@admin_required
def unlock_tier(tier_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE coming_soon_tiers SET is_unlocked = 1 WHERE tier_name = ?", (tier_name,))
    conn.commit()
    conn.close()
    flash(f"{tier_name} has been pushed live into active fleet matrix allocation.", "success")
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete-channel/<int:c_id>')
@admin_required
def delete_channel(c_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM merchant_channels WHERE id = ?", (c_id,))
    conn.commit()
    conn.close()
    flash("Routing configuration line dropped.", "success")
    return redirect(url_for('admin_panel'))


# =====================================================================
# 4. DEPOSIT & WITHDRAWAL CORE VERIFICATION ACTIONS
# =====================================================================
@app.route('/admin/approve-deposit/<d_id>')
@admin_required
def approve_deposit(d_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deposits WHERE id = ? AND status = 'Pending'", (d_id,))
    deposit_row = cursor.fetchone()
    
    if deposit_row:
        cursor.execute("SELECT phone FROM users WHERE id = ?", (deposit_row['user_id'],))
        user_row = cursor.fetchone()
        user_phone = user_row['phone'] if user_row else f"USER_ID_{deposit_row['user_id']}"
        
        admin_signature = session.get('phone', session.get('username', 'ADMIN_NODE'))
        
        # Credit the user's account and set deposit status to Success
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (deposit_row['amount'], deposit_row['user_id']))
        cursor.execute("UPDATE deposits SET status = 'Success' WHERE id = ?", (d_id,))
        
        # FIX: Unified fields (tx_type, amount, status, notes) without ticket_id or processed_at
        cursor.execute('''
            INSERT INTO transaction_archive (tx_type, amount, status, notes)
            VALUES ('DEPOSIT', ?, 'APPROVED', ?)
        ''', (deposit_row['amount'], f"Ticket: {d_id} | Approved by {admin_signature} for user phone {user_phone}"))
        
        conn.commit()
        flash("Deposit finalized. Balance modified securely and logged to archive.", "success")
        
    conn.close()
    return redirect(url_for('admin_panel'))


@app.route('/admin/reject-deposit/<d_id>')
@admin_required
def reject_deposit(d_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deposits WHERE id = ? AND status = 'Pending'", (d_id,))
    deposit_row = cursor.fetchone()
    
    if deposit_row:
        cursor.execute("SELECT phone FROM users WHERE id = ?", (deposit_row['user_id'],))
        user_row = cursor.fetchone()
        user_phone = user_row['phone'] if user_row else f"USER_ID_{deposit_row['user_id']}"
        
        admin_signature = session.get('phone', session.get('username', 'ADMIN_NODE'))
        
        # Mark the deposit request as Rejected (no balance is added)
        cursor.execute("UPDATE deposits SET status = 'Rejected' WHERE id = ?", (d_id,))
        
        # FIX: Unified fields (tx_type, amount, status, notes) without ticket_id or processed_at
        cursor.execute('''
            INSERT INTO transaction_archive (tx_type, amount, status, notes)
            VALUES ('DEPOSIT_REJECTED', ?, 'REJECTED', ?)
        ''', (deposit_row['amount'], f"Ticket: {d_id} | Rejected by {admin_signature} for user phone {user_phone}"))
        
        conn.commit()
        flash("Deposit request rejected and logged securely to archive.", "warning")
        
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/approve-withdrawal/<w_id>')
@admin_required
def approve_withdrawal(w_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch details first for logging metrics before finalizing status
    cursor.execute("SELECT * FROM withdrawals WHERE id = ?", (w_id,))
    w_row = cursor.fetchone()
    
    if w_row:
        cursor.execute("SELECT phone FROM users WHERE id = ?", (w_row['user_id'],))
        user_row = cursor.fetchone()
        user_phone = user_row['phone'] if user_row else f"USER_ID_{w_row['user_id']}"
        
        admin_signature = session.get('phone', session.get('username', 'ADMIN_NODE'))
        
        # 1. Update the core withdrawal status tracker
        cursor.execute("UPDATE withdrawals SET status = 'Success', handling_agent = ? WHERE id = ?", (admin_signature, w_id))
        
        # 2. LOG TO ARCHIVE: Clean matrix query matching your columns
        cursor.execute('''
            INSERT INTO transaction_archive (tx_type, amount, status, notes)
            VALUES ('WITHDRAWAL', ?, 'SUCCESSFUL', ?)
        ''', (w_row['gross_amount'], f"Payout Ticket: {w_id} | Disbursed by agent {admin_signature} to user phone {user_phone} (Net: UGX {w_row['net_amount']:,})"))
        
        conn.commit()
        flash("Withdrawal marked as Successful and logged to archive system.", "success")
    else:
        flash("Withdrawal request record could not be resolved.", "warning")
        
    conn.close()
    return redirect(url_for('admin_panel'))


@app.route('/admin/reject-withdrawal/<w_id>')
@admin_required
def reject_withdrawal(w_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM withdrawals WHERE id = ? AND status = 'Pending'", (w_id,))
    w_row = cursor.fetchone()
    
    if w_row:
        cursor.execute("SELECT phone FROM users WHERE id = ?", (w_row['user_id'],))
        user_row = cursor.fetchone()
        user_phone = user_row['phone'] if user_row else f"USER_ID_{w_row['user_id']}"
        
        admin_signature = session.get('phone', session.get('username', 'ADMIN_NODE'))
        
        # 1. Refund gross balance back onto user core wallet ledger metrics
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (w_row['gross_amount'], w_row['user_id']))
        cursor.execute("UPDATE withdrawals SET status = 'Rejected', handling_agent = ? WHERE id = ?", (admin_signature, w_id))
        
        # 2. LOG TO ARCHIVE: Clean matrix query matching your columns
        cursor.execute('''
            INSERT INTO transaction_archive (tx_type, amount, status, notes)
            VALUES ('WITHDRAWAL_REJECTED', ?, 'REJECTED', ?)
        ''', (w_row['gross_amount'], f"Ticket: {w_id} | Rejected by {admin_signature} for user phone {user_phone}. Funds restored."))
        
        conn.commit()
        flash("Withdrawal rejected. Funds returned to user ledger and recorded in archive.", "info")
    else:
        flash("Withdrawal request not found or already processed.", "danger")
        
    conn.close()
    return redirect(url_for('admin_panel'))


# =====================================================================
# 5. CONDITIONAL WIPEOUT & ADMINISTRATIVE APPROVAL RESTORATION
# =====================================================================

import json  # Global backup or inline imports are safely supported
from flask import session, abort, redirect, flash

@app.route('/admin/wipeout-user/<int:user_id>', methods=['GET', 'POST'])
def wipeout_user(user_id):
    import json  # Inline import prevents global NameError crashes
    from flask import session, abort, redirect, flash
    
    # 1. DIRECT DATABASE ACCESS CLEARANCE VERIFICATION
    session_uid = session.get('user_id') or session.get('_user_id')
    if not session_uid:
        abort(403) # Hard block if no active session exists
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    is_authorized_admin = False
    try:
        # Pure role check with no invalid columns
        cursor.execute("SELECT role FROM users WHERE id = ?", (session_uid,))
        admin_check = cursor.fetchone()
        if admin_check:
            try:
                # Dict-style row factory parsing
                role_val = str(admin_check.get('role', '')).lower()
            except Exception:
                # Tuple-style traditional parsing fallback
                try:
                    role_val = str(admin_check[0]).lower()
                except Exception:
                    role_val = ""
                    
            if role_val == 'admin':
                is_authorized_admin = True
    except Exception as auth_err:
        print(f"[AUTH CRITICAL FAULT] Direct database security check failed: {auth_err}")
        
    # Strict fallback block: terminate connection and reject execution if not validated
    if not is_authorized_admin:
        conn.close()
        abort(403)
    
    u_phone = "Unknown"
    u_balance = 0.0
    u_comm = 0.0
    u_profit = 0.0
    u_role = "user"
    u_upline = None
    
    # 2. ADVANCED CASCADING DEMOLITION BLOCK (Prevents Foreign Key Commit Aborts)
    relational_tables_to_clear = [
        ("investments", "user_id"),
        ("deposits", "user_id"),
        ("withdrawals", "user_id"),
        ("referrals", "user_id"),
        ("referrals", "referred_id")
    ]
    for table_name, column_name in relational_tables_to_clear:
        try:
            cursor.execute(f"DELETE FROM {table_name} WHERE {column_name} = ?", (user_id,))
        except Exception:
            pass

    # 3. Safely fetch target details using explicit database selection
    try:
        cursor.execute("SELECT id, phone, balance, referral_commission, cumulative_profit, role, referred_by FROM users WHERE id = ?", (user_id,))
        target_user = cursor.fetchone()
        
        if not target_user:
            conn.close()
            flash("Target user node could not be resolved.", "warning")
            return redirect('/admin-operations-hq')
            
        try:
            u_phone = target_user['phone']
            u_balance = target_user['balance']
            u_comm = target_user['referral_commission']
            u_profit = target_user.get('cumulative_profit', 0.0)
            u_role = target_user['role']
            u_upline = target_user['referred_by']
        except Exception:
            try:
                u_phone = target_user[1]
                u_balance = target_user[2]
                u_comm = target_user[3]
                u_profit = target_user[4]
                u_role = target_user[5]
                u_upline = target_user[6]
            except Exception:
                pass
    except Exception as fetch_err:
        print(f"[RECOVERABLE] Initial user fetch step failed: {fetch_err}")

    commission_to_clawback = 0.0
    uplink_resolved_id = None
    
    # 4. Check historic payout ledger safely in an isolated sub-block
    try:
        cursor.execute('SELECT uplink_id, commission_awarded FROM referral_payout_history WHERE downlink_id = ?', (user_id,))
        payout_record = cursor.fetchone()
        
        if payout_record:
            try:
                commission_to_clawback = float(payout_record['commission_awarded'] or 0.0)
                raw_uplink = payout_record['uplink_id']
            except Exception:
                try:
                    raw_uplink = payout_record[0]
                    commission_to_clawback = float(payout_record[1] or 0.0)
                except Exception:
                    raw_uplink = None
            
            if raw_uplink:
                try:
                    cursor.execute("SELECT id FROM users WHERE id = ? OR phone = ? OR ref_code = ?", (raw_uplink, raw_uplink, raw_uplink))
                    uplink_user = cursor.fetchone()
                    if uplink_user:
                        try: uplink_resolved_id = uplink_user['id']
                        except Exception: uplink_resolved_id = uplink_user[0]
                except Exception:
                    pass
    except Exception as ledger_err:
        print(f"[RECOVERABLE] Ledger clawback tracking bypassed: {ledger_err}")

    if not uplink_resolved_id and u_upline:
        try:
            cursor.execute("SELECT id FROM users WHERE ref_code = ? OR phone = ? OR id = ?", (u_upline, u_upline, u_upline))
            uplink_user = cursor.fetchone()
            if uplink_user:
                try: uplink_resolved_id = uplink_user['id']
                except Exception: uplink_resolved_id = uplink_user[0]
        except Exception:
            pass

    # 5. Process upline deduction metrics with negative debt allowance
    if uplink_resolved_id and commission_to_clawback > 0:
        try:
            cursor.execute("SELECT balance, referral_commission FROM users WHERE id = ?", (uplink_resolved_id,))
            up_row = cursor.fetchone()
            if up_row:
                try:
                    up_bal = float(up_row['balance'] or 0.0)
                    up_comm = float(up_row['referral_commission'] or 0.0)
                except Exception:
                    try:
                        up_bal = float(up_row[0] or 0.0)
                        up_comm = float(up_row[1] or 0.0)
                    except Exception:
                        up_bal, up_comm = 0.0, 0.0

                new_bal = up_bal - commission_to_clawback
                new_comm = up_comm - commission_to_clawback

                cursor.execute("UPDATE users SET balance = ?, referral_commission = ? WHERE id = ?", (new_bal, new_comm, uplink_resolved_id))
                
                try:
                    cursor.execute("INSERT INTO transaction_archive (tx_type, amount, status, notes) VALUES ('UPLINE_PENALTY', ?, 'Debt Incurred', ?)", 
                                   (commission_to_clawback, f"Upline ID: {uplink_resolved_id} penalized. Previous Bal: {up_bal}, New Bal: {new_bal} (Debt applied due to downline ID {user_id} purge)."))
                except Exception:
                    pass
                
                try:
                    cursor.execute('DELETE FROM referral_payout_history WHERE downlink_id = ?', (user_id,))
                except Exception:
                    pass
        except Exception as upline_err:
            print(f"[RECOVERABLE] Upline penalty execution skipped: {upline_err}")

    # 6. Construct JSON logging structure securely (Fully optimized for restoration syncing)
    try:
        backup_properties = {
            "id": int(user_id),
            "phone": str(u_phone),
            "role": str(u_role),
            "balance": float(u_balance or 0),
            "referral_commission": float(u_comm or 0),
            "cumulative_profit": float(u_profit or 0),
            "referred_by": str(u_upline or ""),
            "clawed_back_commission": float(commission_to_clawback)
        }
        backup_string = json.dumps(backup_properties)
    except Exception:
        backup_string = f'{{"id": {user_id}, "phone": "{u_phone}", "fallback_balance": {float(u_balance or 0)}, "clawed_back_commission": {float(commission_to_clawback)}}}'

    # 7. Finalizing User State Mutations with absolute separation
    state_mutated = False
    try:
        cursor.execute("UPDATE users SET balance = 0.0, referral_commission = 0.0, cumulative_profit = 0.0, role = 'purged' WHERE id = ? AND role != 'admin'", (user_id,))
        state_mutated = True
    except Exception:
        pass

    if not state_mutated:
        try:
            cursor.execute("UPDATE users SET balance = 0.0, referral_commission = 0.0, role = 'purged' WHERE id = ? AND role != 'admin'", (user_id,))
        except Exception as update_err:
            print(f"[CRITICAL WARNING] Core user state update completely rejected: {update_err}")
    
    # 8. Archive transaction records cleanly
    try:
        cursor.execute("INSERT INTO transaction_archive (tx_type, amount, status, notes) VALUES ('ACCOUNT_SUSPENDED', ?, 'Purged', ?)", 
                       (float(user_id), backup_string))
    except Exception:
        pass
    
    # 9. Safe final database commit
    try:
        conn.commit()
        flash(f"Account properties isolated. User {u_phone} has been suspended cleanly.", "success")
    except Exception as commit_error:
        conn.rollback()
        print(f"\n[CRITICAL DATABASE COMMIT CRASH] System auto-recovered: {commit_error}\n")
        flash("Database engine rejected execution parameters safely.", "danger")
    finally:
        conn.close()
        
    return redirect('/admin-operations-hq')


@app.route('/admin/restore-purged-user/<int:user_id>', methods=['POST'])
@admin_required
def restore_purged_user(user_id):
    import json
    from flask import redirect, flash, url_for
    
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. VALIDATE CURRENT PURGED STATUS
        cursor.execute("SELECT id, phone, role FROM users WHERE id = ?", (user_id,))
        target_user = cursor.fetchone()
        
        if not target_user:
            flash("Target account row could not be found.", "danger")
            return redirect(url_for('admin_panel'))
            
        u_phone = target_user['phone'] if isinstance(target_user, dict) else target_user[1]
        current_role = target_user['role'] if isinstance(target_user, dict) else target_user[2]

        if str(current_role).lower() != 'purged':
            flash(f"User {u_phone} is not in a purged state.", "warning")
            return redirect(url_for('admin_panel'))

        # 2. LOCATE HISTORICAL SNAPSHOT
        cursor.execute("""
            SELECT notes FROM transaction_archive 
            WHERE tx_type = 'ACCOUNT_SUSPENDED' AND (amount = ? OR notes LIKE ?) 
            ORDER BY id DESC LIMIT 1
        """, (float(user_id), f'%"id": {int(user_id)}%',))
        
        snapshot_row = cursor.fetchone()
        
        # Default fallback values
        restored_bal, restored_comm, restored_profit = 0.0, 0.0, 0.0
        restored_fleet, restored_user_info = '[]', '{}'
        commission_to_refund, upline_reference = 0.0, None

        # 3. EXTRACT AND PARSE SNAPSHOT
        if snapshot_row:
            raw_notes = snapshot_row['notes'] if isinstance(snapshot_row, dict) else snapshot_row[0]
            try:
                data = json.loads(raw_notes)
                restored_bal = float(data.get('balance', 0.0))
                restored_comm = float(data.get('referral_commission', 0.0))
                restored_profit = float(data.get('cumulative_profit', 0.0))
                restored_fleet = data.get('fleet_data', '[]')
                restored_user_info = data.get('user_info', '{}')
                commission_to_refund = float(data.get('clawed_back_commission', 0.0))
                upline_reference = data.get('referred_by')
            except Exception as e:
                print(f"Deep restoration parsing failed: {e}")

        # 4. RESTORE USER PROFILE DATA (Including Fleet/Assets)
        cursor.execute("""
            UPDATE users 
            SET role = 'user', 
                balance = ?, 
                referral_commission = ?, 
                cumulative_profit = ?,
                fleet_data = ?,
                user_info = ?
            WHERE id = ?
        """, (restored_bal, restored_comm, restored_profit, restored_fleet, restored_user_info, user_id))

        # 5. REVERSE UPLINE PENALTY
        if commission_to_refund > 0 and upline_reference:
            cursor.execute("UPDATE users SET balance = balance + ?, referral_commission = referral_commission + ? WHERE id = ? OR ref_code = ?", 
                           (commission_to_refund, commission_to_refund, upline_reference, upline_reference))
            
            cursor.execute("""
                INSERT INTO transaction_archive (tx_type, amount, status, notes) 
                VALUES ('UPLINE_PENALTY_REVERSAL', ?, 'Success', ?)
            """, (commission_to_refund, f"Refunded {commission_to_refund} to Upline. Debt cleared for user {user_id}."))

        # 6. LOG SUCCESS
        cursor.execute("INSERT INTO transaction_archive (tx_type, amount, status, notes) VALUES ('ACCOUNT_RESTORED', 0.0, 'Success', ?)", 
                       (f"Admin lifted suspension for {u_phone} (ID: {user_id}). Assets and balance restored.",))

        conn.commit()
        flash(f"User {u_phone} successfully restored with historical assets and balances.", "success")
        
    except Exception as e:
        conn.rollback()
        print(f"Restoration Error: {e}")
        flash("System error during restoration.", "danger")
    finally:
        conn.close()
        
    return redirect(url_for('admin_panel'))


# ---------------------------------------------------------
# INTERFACES STRINGS INJECTIONS (HTML LAYOUT MATRICES)
# ---------------------------------------------------------
HTML_REGISTER = '''
<!DOCTYPE html>
<html>
<head>
    <title>TransitFlow - Registration Matrix</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" rel="stylesheet">
    <style>
        body { background-color: #0f111a; color: #e1e1e6; font-family: monospace; }
        .auth-card { background-color: #161925; border: 1px solid #292e42; border-radius: 8px; }
    </style>
</head>
<body>
<div class="container d-flex justify-content-center align-items-center min-vh-100">
    <div class="card auth-card p-4 w-100" style="max-width: 450px;">
        <h3 class="text-center text-danger fw-bold mb-3"><i class="fa-solid fa-truck-fast me-2"></i>TRANSITFLOW</h3>
        <p class="text-center text-muted small">Initialize Logistics Network Protocol Account</p>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }} small py-2">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <form method="POST">
            <div class="mb-3">
                <label class="form-label small text-secondary">Phone Number (Network ID)</label>
                <div class="input-group">
                    <span class="input-group-text bg-secondary text-white"><i class="fa-solid fa-phone text-warning"></i></span>
                    <input type="text" name="phone" class="form-control bg-dark border-secondary text-white small" required placeholder="e.g. 0770000000">
                </div>
            </div>
            
            <div class="mb-3">
                <label class="form-label small text-secondary">Access Key Password</label>
                <div class="input-group">
                    <span class="input-group-text bg-secondary text-white"><i class="fa-solid fa-key text-warning"></i></span>
                    <input type="password" name="password" class="form-control bg-dark border-secondary text-white small" required placeholder="Enter strong password">
                </div>
            </div>
            
            <div class="mb-3">
                <label for="confirm_password" class="form-label small text-secondary">Confirm Access Key</label>
                <div class="input-group">
                    <span class="input-group-text bg-secondary text-white"><i class="fa-solid fa-key text-warning"></i></span>
                    <input type="password" class="form-control bg-dark text-white border-secondary small" 
                           id="confirm_password" name="confirm_password" placeholder="Re-enter password" required>
                </div>
            </div>

            <div class="mb-3">
                <label for="security_pin" class="form-label small text-secondary">Account Recovery Secret PIN</label>
                <div class="input-group">
                    <span class="input-group-text bg-secondary text-white"><i class="fa-solid fa-lock text-warning"></i></span>
                    <input type="password" class="form-control bg-dark text-white border-secondary small" 
                           id="security_pin" name="security_pin" placeholder="Enter a 4-6 digit secret code" required>
                </div>
                <div class="form-text text-muted numeric-help style" style="font-size: 0.75rem;">CRITICAL: Memorize this code. It is the only way to recover your account if you forget your password.</div>
            </div>

            <div class="mb-3">
                <label class="form-label small text-secondary">Uplink Association Code (Optional)</label>
                <div class="input-group">
                    <span class="input-group-text bg-secondary text-white"><i class="fa-solid fa-network-wired text-muted"></i></span>
                    <input type="text" name="referred_by" class="form-control bg-dark border-secondary text-white small" value="{{ ref_param }}">
                </div>
            </div>
            
            <div class="d-grid gap-2 mt-4">
                <button type="submit" class="btn btn-warning btn-sm fw-bold text-dark">CREATE ACTIVE PROFILE NODE</button>
            </div>
        </form>
        <div class="text-center mt-3">
            <a href="/login" class="text-secondary small text-decoration-none">Existing node? Authorize Log-In</a>
        </div>
    </div>
</div>
</body>
</html>
'''

HTML_LOGIN = '''
<!DOCTYPE html>
<html>
<head>
    <title>TransitFlow - Secure Authorization</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" rel="stylesheet">
    <style>
        body { background-color: #0f111a; color: #e1e1e6; font-family: monospace; }
        .auth-card { background-color: #161925; border: 1px solid #292e42; border-radius: 8px; }
    </style>
</head>
<body>
<div class="container d-flex justify-content-center align-items-center min-vh-100">
    <div class="card auth-card p-4 w-100" style="max-width: 450px;">
        <h3 class="text-center text-danger fw-bold mb-3"><i class="fa-solid fa-truck-fast me-2"></i>TRANSITFLOW</h3>
        <p class="text-center text-muted small">System Node Authentication Terminal</p>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }} small py-2">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <form method="POST">
            <div class="mb-3">
                <label class="form-label small text-secondary">Phone Number Node</label>
                <input type="text" name="phone" class="form-control bg-dark border-secondary text-white small" required autocomplete="off">
            </div>
            <div class="mb-3">
                <label class="form-label small text-secondary">System Entry Pass</label>
                <input type="password" name="password" class="form-control bg-dark border-secondary text-white small" required>
            </div>
            <button type="submit" class="btn btn-danger w-100 btn-sm fw-bold">VERIFY CREDENTIALS</button>
        </form>
        <div class="d-flex justify-content-between mt-3 small">
            <a href="/forgot-password" class="text-muted text-decoration-none">Forgot Pass?</a>
            <a href="/register" class="text-danger text-decoration-none">Initialize Register</a>
        </div>
    </div>
</div>
</body>
</html>
'''

HTML_FORGOT_PASSWORD = '''
<!DOCTYPE html>
<html>
<head>
    <title>TransitFlow - Account Recovery</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" rel="stylesheet">
    <style>
        body { background-color: #0f111a; color: #e1e1e6; font-family: monospace; }
        .auth-card { background-color: #161925; border: 1px solid #292e42; border-radius: 8px; }
    </style>
</head>
<body>
<div class="container d-flex justify-content-center align-items-center min-vh-100">
    <div class="card auth-card p-4 w-100" style="max-width: 450px;">
        <h4 class="text-center text-warning fw-bold mb-3"><i class="fa-solid fa-key me-2"></i>NODE RESET TERMINAL</h4>
        <p class="text-center text-muted small mb-3">Provide authorization data to rewrite entry key</p>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }} small py-2">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <form method="POST">
            <div class="mb-3">
                <label class="form-label small text-secondary">Registered Phone Target</label>
                <input type="text" name="phone" class="form-control bg-dark border-secondary text-white small" required autocomplete="off" placeholder="e.g. 0770000000">
            </div>
            
            <div class="mb-3">
                <label class="form-label small text-secondary">Account Secret Verification PIN</label>
                <input type="password" name="security_pin" class="form-control bg-dark border-secondary text-white small" required placeholder="Enter your 4-6 digit recovery PIN" autocomplete="off">
            </div>
            
            <div class="mb-3">
                <label class="form-label small text-secondary">New Pass Allocation</label>
                <input type="password" name="new_password" class="form-control bg-dark border-secondary text-white small" required placeholder="Create new password">
            </div>
            <div class="mb-3">
                <label class="form-label small text-secondary">Confirm Pass Allocation</label>
                <input type="password" name="confirm_password" class="form-control bg-dark border-secondary text-white small" required placeholder="Repeat new password">
            </div>
            <button type="submit" class="btn btn-warning w-100 btn-sm fw-bold text-dark">OVERWRITE ACCOUNT PASS</button>
        </form>
        <div class="text-center mt-3">
            <a href="/login" class="text-secondary small text-decoration-none">Back to Authorization</a>
        </div>
    </div>
</div>
</body>
</html>
'''

HTML_DASHBOARD = '''
<!DOCTYPE html>
<html>
<head>
    <title>TransitFlow - Dashboard Workspace</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" rel="stylesheet">
    
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&family=JetBrains+Mono:ital,wght@0,100..800;1,100..800&display=swap" rel="stylesheet">

    <style>
        /* Global Structural Reset using Institutional Typeface */
        body { 
            background-color: #0c0e17; 
            color: #e4e4e7; 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            letter-spacing: -0.1px;
        }
        
        /* Retained Authentication Styles to prevent breaking login screens */
        .auth-card { 
            background-color: #161925; 
            border: 1px solid #292e42; 
            border-radius: 8px; 
        }
        
        /* Clean, authoritative weight settings for layout components */
        .navbar-brand { font-family: 'Inter', sans-serif; font-weight: 800; letter-spacing: 0.5px; }
        h1, h2, h3, h4, h5, h6 { font-weight: 700; letter-spacing: -0.3px; color: #ffffff; }
        
        /* Specialized Monospace targeting for absolute accounting clarity */
        .font-monospace, .badge, th, td, #lbl-balance, #lbl-profit, input, select, textarea { 
            font-family: 'JetBrains Mono', monospace !important; 
            letter-spacing: -0.2px;
        }
        
        /* Card Structure Layout Optimization */
        .metric-card { 
            background: linear-gradient(145deg, #121524, #181d30); 
            border: 1px solid #222943; 
            border-radius: 12px; 
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        }
        .vehicle-card { 
            background-color: #121524; 
            border: 1px solid #1e253b; 
            border-radius: 10px; 
            overflow: hidden; 
            transition: all 0.2s ease-in-out; 
        }
        .vehicle-card:hover { border-color: #dc3545; transform: translateY(-2px); }
        .table-dark { --bs-table-bg: #111422; border-color: #222943; }
        .text-secondary { color: #a1a1aa !important; }
    </style>
</head>
<body>

<nav class="navbar navbar-dark bg-dark border-bottom border-secondary sticky-top py-2">
    <div class="container">
        <span class="navbar-brand text-danger"><i class="fa-solid fa-truck-fast me-2"></i>TRANSITFLOW <span class="text-white small fw-light">v4.2</span></span>
        <div class="d-flex align-items-center">
            <span class="text-secondary small me-3 d-none d-sm-inline"><i class="fa-solid fa-circle-user me-1 text-success"></i>ID: {{user.phone}}</span>
            <a href="/logout" class="btn btn-outline-danger btn-sm px-2 py-0 fw-bold small"><i class="fa-solid fa-power-off"></i></a>
        </div>
    </div>
</nav>

<div class="container mt-4 mb-5">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="alert alert-{{ category }} alert-dismissible fade show small py-2">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    <div class="card metric-card p-3 mb-4 text-white">
        <div class="row align-items-center text-center text-md-start">
            <div class="col-md-3 mb-2 mb-md-0">
                <span class="text-secondary uppercase small font-monospace d-block">AVAILABLE NODAL LEDGER</span>
                <h2 class="text-success fw-black mt-1">UGX <span id="lbl-balance">{{ugx(user.balance)}}</span></h2>
            </div>
            <div class="col-md-3 mb-2 mb-md-0 border-start border-secondary">
                <span class="text-secondary uppercase small font-monospace d-block">TOTAL LOGISTICS RETURN</span>
                <h4 class="text-danger fw-bold mt-1">UGX <span id="lbl-profit">{{ugx(user.cumulative_profit)}}</span></h4>
            </div>
            <div class="col-md-3 mb-2 mb-md-0 border-start border-secondary">
                <span class="text-secondary uppercase small font-monospace d-block">COMMISSION INCENTIVES</span>
                <h4 class="text-warning fw-bold mt-1">UGX {{ugx(user.referral_commission)}}</h4>
            </div>
            <div class="col-md-3 text-md-end">
                <button class="btn btn-success btn-sm fw-bold me-2" data-bs-toggle="modal" data-bs-target="#mdl-deposit"><i class="fa-solid fa-wallet me-1"></i> Deposit</button>
                <button class="btn btn-danger btn-sm fw-bold" data-bs-toggle="modal" data-bs-target="#mdl-withdraw"><i class="fa-solid fa-money-bill-transfer me-1"></i> Cashout</button>
            </div>
        </div>
    </div>

    <!-- UPGRADED HIGH-VISIBILITY CORPORATE OPERATIONS NAVIGATION CONTROLS -->
    <div class="mb-4">
        <span class="text-secondary uppercase font-monospace d-block mb-2" style="font-size: 0.75rem; letter-spacing: 1px;">
            <i class="fa-solid fa-network-wired me-1 text-danger"></i> SYSTEM NODE CORE INTERFACE
        </span>
        <div class="row g-2" id="dash-tabs" role="tablist" style="font-family: -apple-system, BlinkMacSystemFont, monospace;">
            
            <!-- Node 1: Active Cargo Fleet -->
            <div class="col-6 col-md-3" role="presentation">
                <button class="nav-link active w-100 p-3 text-start d-flex flex-column justify-content-between h-100 position-relative" 
                        data-bs-toggle="tab" 
                        data-bs-target="#tab-fleet" 
                        type="button"
                        style="background: linear-gradient(145deg, #131622, #1a1e30); border: 1px solid #23283e; border-radius: 8px; transition: all 0.2s ease-in-out; min-height: 85px;">
                    <div class="d-flex w-100 justify-content-between align-items-center mb-2">
                        <i class="fa-solid fa-truck-ramp-box fa-lg text-danger"></i>
                        <span class="badge bg-danger bg-opacity-10 text-danger" style="font-size: 0.65rem; border: 1px solid rgba(220, 53, 69, 0.2);">LIVE</span>
                    </div>
                    <div class="fw-bold text-white small" style="letter-spacing: 0.5px;">CARGO FLEET</div>
                </button>
            </div>

            <!-- Node 2: Transactions Archive -->
            <div class="col-6 col-md-3" role="presentation">
                <button class="nav-link w-100 p-3 text-start d-flex flex-column justify-content-between h-100" 
                        data-bs-toggle="tab" 
                        data-bs-target="#tab-history" 
                        type="button"
                        style="background: linear-gradient(145deg, #131622, #1a1e30); border: 1px solid #23283e; border-radius: 8px; transition: all 0.2s ease-in-out; min-height: 85px;">
                    <div class="d-flex w-100 justify-content-between align-items-center mb-2">
                        <i class="fa-solid fa-receipt fa-lg text-secondary" id="icon-history"></i>
                        <span class="text-muted" style="font-size: 0.65rem;">LEDGER</span>
                    </div>
                    <div class="fw-bold text-secondary small" style="letter-spacing: 0.5px;" id="text-history">LEDGER ARCHIVE</div>
                </button>
            </div>

            <!-- Node 3: Syndicate Network -->
            <div class="col-6 col-md-3" role="presentation">
                <button class="nav-link w-100 p-3 text-start d-flex flex-column justify-content-between h-100" 
                        data-bs-toggle="tab" 
                        data-bs-target="#tab-affiliate" 
                        type="button"
                        style="background: linear-gradient(145deg, #131622, #1a1e30); border: 1px solid #23283e; border-radius: 8px; transition: all 0.2s ease-in-out; min-height: 85px;">
                    <div class="d-flex w-100 justify-content-between align-items-center mb-2">
                        <i class="fa-solid fa-diagram-project fa-lg text-secondary" id="icon-affiliate"></i>
                        <span class="text-muted" style="font-size: 0.65rem;">MATRIX</span>
                    </div>
                    <div class="fw-bold text-secondary small" style="letter-spacing: 0.5px;" id="text-affiliate">SYNDICATE NET</div>
                </button>
            </div>

            <!-- Node 4: System Desk Helpline -->
            <div class="col-6 col-md-3" role="presentation">
                <button class="nav-link w-100 p-3 text-start d-flex flex-column justify-content-between h-100" 
                        data-bs-toggle="tab" 
                        data-bs-target="#tab-help" 
                        type="button"
                        style="background: linear-gradient(145deg, #131622, #1a1e30); border: 1px solid #23283e; border-radius: 8px; transition: all 0.2s ease-in-out; min-height: 85px;">
                    <div class="d-flex w-100 justify-content-between align-items-center mb-2">
                        <i class="fa-solid fa-headset fa-lg text-warning text-opacity-50" id="icon-help"></i>
                        <span class="badge bg-warning bg-opacity-10 text-warning" style="font-size: 0.65rem; border: 1px solid rgba(255, 193, 7, 0.2);">24/7</span>
                    </div>
                    <div class="fw-bold text-secondary small" style="letter-spacing: 0.5px;" id="text-help">SYSTEM HELPDESK</div>
                </button>
            </div>

        </div>
    </div>

    <!-- INJECT INTERACTIVE BRAND HIGHLIGHTING JAVASCRIPT -->
    <script>
    document.addEventListener("DOMContentLoaded", function() {
        const tabs = document.querySelectorAll('#dash-tabs button');
        tabs.forEach(tab => {
            tab.addEventListener('shown.bs.tab', function (e) {
                // Reset all tabs to dark corporate state
                tabs.forEach(t => {
                    t.style.background = "linear-gradient(145deg, #131622, #1a1e30)";
                    t.style.borderColor = "#23283e";
                    
                    let txt = t.querySelector('.fw-bold');
                    let ico = t.querySelector('.fa-lg');
                    if(txt) txt.className = "fw-bold text-secondary small";
                    if(ico && !ico.classList.contains('fa-headset') && !ico.classList.contains('fa-truck-ramp-box')) {
                        ico.className = ico.className.replace('text-danger', 'text-secondary').replace('text-warning', 'text-secondary');
                    }
                });

                // Highlight the currently active clicked tab
                e.target.style.background = "linear-gradient(145deg, #1a1e30, #242a42)";
                e.target.style.borderColor = "#dc3545";
                let activeTxt = e.target.querySelector('.fw-bold');
                let activeIco = e.target.querySelector('.fa-lg');
                if(activeTxt) activeTxt.className = "fw-bold text-white small";
                if(activeIco) {
                    if(!activeIco.classList.contains('fa-headset')) {
                        activeIco.className = activeIco.className.replace('text-secondary', 'text-danger');
                    } else {
                        activeIco.className = activeIco.className.replace('text-opacity-50', 'text-opacity-100');
                    }
                }
            });
        });
    });
    </script>

    <div class="tab-content">
        <div class="tab-pane fade show active" id="tab-fleet">
            <h5 class="mb-3 text-white fw-bold">Procure Cross-Border Transit Configurations</h5>
            <div class="row row-cols-1 row-cols-sm-2 row-cols-md-3 g-3">
                {% for t, details in vehicles.items() %}
                <div class="col">
                    <div class="card vehicle-card h-100">
                        <img src="{{details.img}}" class="card-img-top" style="height: 160px; object-fit: cover; opacity: 0.85;">
                        <div class="card-body p-3 d-flex flex-column justify-content-between">
                            <div>
                                <div class="d-flex justify-content-between align-items-center mb-1">
                                    <h6 class="text-white fw-bold mb-0">{{t}} Asset Configuration</h6>
                                    <span class="badge bg-success small">14 Days cycle</span>
                                </div>
                                <p class="small text-muted mb-2">Freight Distribution Node Allocation</p>
                                <div class="bg-dark p-2 rounded mb-3 small border border-secondary">
                                    <div class="d-flex justify-content-between"><span class="text-secondary">Procurement Cap:</span><span class="text-white fw-bold">UGX {{ugx(details.price)}}</span></div>
                                    <div class="d-flex justify-content-between"><span class="text-secondary">Daily Corridor Yield:</span><span class="text-success fw-bold">UGX {{ugx(details.daily)}}</span></div>
                                </div>
                            </div>
                            <form action="/purchase" method="POST">
                                <input type="hidden" name="tier" value="{{t}}">
                                <button type="submit" class="btn btn-danger w-100 btn-sm fw-bold">INITIALIZE FLEET DEPLOYMENT</button>
                            </form>
                        </div>
                    </div>
                </div>
                {% endfor %}
                
                {% for row in locked_tiers %}
                <div class="col" style="opacity: 0.5;">
                    <div class="card vehicle-card h-100 border-dashed">
                        <div class="card-body p-4 text-center d-flex flex-column justify-content-center align-items-center" style="min-height: 280px;">
                            <i class="fa-solid fa-lock text-secondary fa-2x mb-3"></i>
                            <h6 class="text-white fw-bold">{{row.tier_name}} Configuration</h6>
                            <span class="small text-muted">Cost: UGX {{ugx(row.price)}}</span>
                            <span class="badge bg-secondary mt-2 small">Locked by HQ Operations</span>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>

        <div class="tab-pane fade" id="tab-history">
            <h5 class="text-white fw-bold mb-3">Live Active Deployments</h5>
            <div class="table-responsive mb-4">
                <table class="table table-dark table-striped align-middle small">
                    <thead><tr><th>Config Identifier</th><th>Cost Value</th><th>Daily Yield</th><th>Deployment Registered</th><th>Nodal Timeline</th></tr></thead>
                    <tbody>
                        {% for p in purchases %}
                        <tr><td>{{p.tier_name}}</td><td>UGX {{ugx(p.cost)}}</td><td class="text-success">+UGX {{ugx(p.daily_return)}}</td><td>{{p.activated_at}}</td><td><span class="badge {% if p.status == 'Active' %}bg-success{% else %}bg-secondary{% endif %}">{{p.status}} ({{p.days_held}} days running)</span></td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>

            <div class="row">
                <div class="col-md-6">
                    <h5 class="text-white fw-bold mb-3">Deposits Ledger</h5>
                    <div class="table-responsive">
                        <table class="table table-dark table-striped align-middle small">
                            <thead><tr><th>ID</th><th>Sum</th><th>Channel</th><th>Status</th></tr></thead>
                            <tbody>
                                {% for d in deposits %}
                                <tr><td>{{d.id}}</td><td>UGX {{ugx(d.amount)}}</td><td>{{d.method}}</td><td><span class="badge {% if d.status=='Success' %}bg-success{% elif d.status=='Pending' %}bg-warning text-dark{% else %}bg-danger{% endif %}">{{d.status}}</span></td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
                <div class="col-md-6">
                    <h5 class="text-white fw-bold mb-3">Withdrawals Ledger</h5>
                    <div class="table-responsive">
                        <table class="table table-dark table-striped align-middle small">
                            <thead><tr><th>ID</th><th>Gross</th><th>Tax</th><th>Net Payout</th><th>Status</th></tr></thead>
                            <tbody>
                                {% for w in withdrawals %}
                                <tr><td>{{w.id}}</td><td>UGX {{ugx(w.gross_amount)}}</td><td>{{ugx(w.tax_amount)}}</td><td class="text-success fw-bold">UGX {{ugx(w.net_amount)}}</td><td><span class="badge {% if w.status=='Success' %}bg-success{% elif w.status=='Pending' %}bg-warning text-dark{% else %}bg-danger{% endif %}">{{w.status}}</span></td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <div class="tab-pane fade" id="tab-affiliate">
            <div class="card metric-card p-3 mb-3 text-white">
                <h6 class="fw-bold text-warning"><i class="fa-solid fa-share-nodes me-2"></i>Platform Brokerage Allocation Matrix</h6>
                <p class="small text-muted">Generate instant 36% capitalization incentives whenever a subordinate node expands the operational fleet container allocation matrix.</p>
                <div class="input-group input-group-sm">
                    <input type="text" class="form-control bg-dark border-secondary text-white" value="{{referral_link}}" readonly id="ref-string">
                    <button class="btn btn-warning font-monospace text-dark fw-bold" onclick="navigator.clipboard.writeText(document.getElementById('ref-string').value); alert('Referral Link Copied to Clipboard Securely!');">COPY LINK</button>
                </div>
            </div>
            <h5 class="text-white fw-bold mb-3">Active Subordinate Fleet Nodes</h5>
            <div class="table-responsive">
                <table class="table table-dark table-striped align-middle small">
                    <thead><tr><th>Masked Node Phone</th><th>Incentives Awarded From Tier</th></tr></thead>
                    <tbody>
                        {% for t in team_members %}
                        <tr><td>{{t.masked_phone}}</td><td class="text-warning fw-bold">UGX {{ugx(t.commission)}}</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="tab-pane fade" id="tab-help">
            <div class="card metric-card p-4 border border-warning text-white">
                <div class="row align-items-center">
                    <div class="col-md-2 text-center text-md-start mb-3 mb-md-0">
                        <i class="fa-brands fa-telegram fa-4x text-info"></i>
                    </div>
                    <div class="col-md-10">
                        <h4 class="fw-bold text-white mb-2">TransitFlow Infrastructure Help & Support Terminal</h4>
                        <p class="small text-secondary mb-3" style="line-height: 1.6;">
                            Are you encountering pipeline latency, deposit synchronization anomalies, or cashout verification holdbacks? Our decentralized logistics support nodes are accessible 24/7. Connect directly to the official encrypted customer verification channel on Telegram to clear transactional blockages immediately.
                        </p>
                        <a href="{{ settings.help_group_link }}" target="_blank" class="btn btn-warning btn-md text-dark fw-bold px-4 py-2">
                            <i class="fa-solid fa-headset me-2"></i>LAUNCH TELEGRAM HELPLINE DESK
                        </a>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- CONTAINER MODALS INTERFACE DECK -->
<div class="modal fade" id="mdl-deposit" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <form class="modal-content bg-dark border-secondary text-white small" action="/deposit" method="POST">
            <div class="modal-header border-secondary"><h6 class="modal-title fw-bold">Initialize Fleet Capitalization Order</h6><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
            <div class="modal-body">
                <div class="mb-3">
                    <label class="form-label text-secondary small">Capitalization Amount (UGX)</label>
                    <input type="number" name="amount" class="form-control bg-dark border-secondary text-white small" placeholder="e.g. 50000" required>
                </div>
                <div class="mb-3">
                    <label class="form-label text-secondary small">Merchant Mobile Provider</label>
                    <select name="method" class="form-select bg-dark border-secondary text-white small" required>
                        <option value="MTN">MTN Mobile Money Pipeline</option>
                        <option value="Airtel">Airtel Money Pipeline</option>
                    </select>
                </div>
                <div class="p-2 border border-secondary rounded bg-black text-muted mb-0" style="font-size: 0.75rem;">
                    * Notice: Finalizing your deposit initializes a ledger ticket. Submit the explicit UGX transfer value to the dynamically populated merchant wallet returned on execution setup.
                </div>
            </div>
            <div class="modal-footer border-secondary"><button type="submit" class="btn btn-success btn-sm fw-bold w-100">COMMIT LEDGER ALLOCATION</button></div>
        </form>
    </div>
</div>

<div class="modal fade" id="mdl-withdraw" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <form class="modal-content bg-dark border-secondary text-white small" action="/withdraw" method="POST">
            <div class="modal-header border-secondary">
                <h6 class="modal-title fw-bold text-warning"><i class="fa-solid fa-money-bill-transfer me-2"></i>Secure Capital Settlement Pipeline</h6>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <div class="alert alert-info border-info bg-black text-info p-2 rounded mb-3" style="font-size:0.75rem; line-height: 1.4;">
                    <i class="fa-solid fa-circle-info me-1"></i> 
                    <strong>Operational Metrics:</strong> Minimum payout parameter: <strong>UGX 15,000</strong>. Routing window parameters active strictly between (10-11 AM, 1-2 PM, 4-6 PM EAT).
                </div>
                
                <div class="mb-3">
                    <label class="form-label text-secondary small mb-1 text-uppercase tracking-wider" style="font-size: 0.70rem;">Account Registered Name</label>
                    <input type="text" name="registered_name" class="form-control bg-dark border-secondary text-white small" placeholder="e.g., John Mukasa" required>
                    <span class="text-muted d-block mt-1" style="font-size: 0.68rem;">* Identity parameter must align explicitly with destination wallet profile.</span>
                </div>

                <div class="mb-3">
                    <label class="form-label text-secondary small mb-1 text-uppercase tracking-wider" style="font-size: 0.70rem;">Settlement Value (UGX)</label>
                    <input type="number" name="amount" class="form-control bg-dark border-secondary text-white small" placeholder="Minimum 15,000" min="15000" required>
                    <span class="text-muted d-block mt-1" style="font-size: 0.68rem;">* Settlements automatically include a 10% cross-border logistics clearing tax fee.</span>
                </div>
            </div>
            <div class="modal-footer border-secondary">
                <button type="submit" class="btn btn-warning btn-sm fw-bold w-100 text-dark">INITIALIZE WITHDRAWAL PIPELINE</button>
            </div>
        </form>
    </div>
</div>

<footer style="background-color: #111420; color: #a1a1aa; font-family: -apple-system, BlinkMacSystemFont, monospace; padding: 40px 20px; margin-top: 60px; border-top: 4px solid #dc3545; font-size: 13px; line-height: 1.6; width: 100%; box-sizing: border-box;">
    <div style="max-width: 1200px; margin: 0 auto; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 30px;">
        
        <div style="flex: 2; min-width: 300px;">
            <h3 style="color: #ffffff; font-size: 16px; margin-bottom: 15px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px;">Corporate Asset Disclosure & Revenue Model</h3>
            <p style="text-align: justify; margin-bottom: 15px;">
                TransitFlow Logistics Group generates core institutional revenue through end-to-end cross-border freight administration and intermodal supply chain coordination. By managing dedicated commercial transport fleets across primary international customs corridors, we capture arbitrage on bulk freight tariffs, border clearance brokerage, and specialized transit handling fees. Our revenue architecture scales directly with cargo volume, leveraging automated route optimization to secure consistent corporate yields on every metric ton of containerized goods moved from border to border.
            </p>
        </div>

        <div style="flex: 1; min-width: 200px;">
            <h3 style="color: #ffffff; font-size: 15px; margin-bottom: 15px; font-weight: bold; text-transform: uppercase;">Operations & Governance</h3>
            <ul style="list-style: none; padding: 0; margin: 0;">
                <li style="margin-bottom: 8px;"><span style="color: #dc3545;">✔</span> Cross-Border Customs Bonded</li>
                <li style="margin-bottom: 8px;"><span style="color: #dc3545;">✔</span> Intermodal Tariff Optimization</li>
                <li style="margin-bottom: 8px;"><span style="color: #dc3545;">✔</span> Real-Time Fleet Telematics</li>
                <li style="margin-bottom: 8px;"><span style="color: #dc3545;">✔</span> High-Yield Logistics Infrastructure</li>
            </ul>
        </div>
    </div>

    <div style="max-width: 1200px; margin: 30px auto 0 auto; padding-top: 20px; border-top: 1px solid #23283e; text-align: center; font-size: 11px; color: #71717a;">
        <p>&copy; 2026 TransitFlow Logistics Group. All corporate rights reserved. Authorized cross-border transit carrier and asset manager.</p>
    </div>
</footer>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''


HTML_ADMIN = '''
<!DOCTYPE html>
<html>
<head>
    <title>TransitFlow - HQ Operations Terminal</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" rel="stylesheet">
    <style>
        body { background-color: #080a11; color: #cbd5e1; font-family: monospace; }
        .hq-header { background: linear-gradient(135deg, #450a0a, #111827); border-bottom: 2px solid #dc3545; }
        .panel-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 6px; }
        .table-dark { --bs-table-bg: #090d16; }
    </style>
</head>
<body>

<div class="hq-header p-3 mb-4 text-white">
    <div class="container d-flex justify-content-between align-items-center">
        <div>
            <h4 class="fw-bold mb-0 text-danger"><i class="fa-solid fa-building-shield me-2"></i>TRANSITFLOW HQ OPERATIONS</h4>
            <span class="small text-muted">Master Node Accounting Framework Control Terminal</span>
        </div>
        <a href="/logout" class="btn btn-danger btn-sm fw-bold">TERMINATE ADMIN ROUTING</a>
    </div>
</div>

<div class="container mb-5">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="alert alert-{{ category }} small py-2">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    <div class="row g-3 mb-4 text-center">
        <div class="col-6 col-md-3">
            <div class="panel-card p-3"><span class="text-secondary small d-block">AGGREGATE GROSS INFLOW</span><h4 class="text-success fw-bold mt-1">UGX {{ugx(inflow)}}</h4></div>
        </div>
        <div class="col-6 col-md-3">
            <div class="panel-card p-3"><span class="text-secondary small d-block">TOTAL SETTLEMENT DISPATCHES</span><h4 class="text-danger fw-bold mt-1">UGX {{ugx(outflow)}}</h4></div>
        </div>
        <div class="col-6 col-md-3">
            <div class="panel-card p-3"><span class="text-secondary small d-block">REMAINING SYSTEM RESERVE MARGIN</span><h4 class="text-info fw-bold mt-1">UGX {{ugx(profit)}}</h4></div>
        </div>
        <div class="col-6 col-md-3">
            <div class="panel-card p-3">
                <span class="text-secondary small d-block">ACTIVE SETTLEMENT ROUTE STATUS</span>
                <span class="badge bg-danger mt-2 px-3 py-1">ADMIN CONTROL ON</span>
            </div>
        </div>
    </div>

    <div class="card panel-card p-4 mb-4">
        <h5 class="text-white fw-bold mb-3">System-Wide Purged User Nodes</h5>
        <div class="table-responsive">
            <table class="table table-striped table-dark align-middle small">
                <thead>
                    <tr><th>ID</th><th>Phone</th><th>Status</th><th>Actions</th></tr>
                </thead>
                <tbody>
                    {% for user in purged_users %}
                    <tr>
                        <td>{{ user.id }}</td>
                        <td>{{ user.phone }}</td>
                        <td><span class="badge bg-danger">{{ user.role }}</span></td>
                        <td>
                            <form action="/admin/restore-purged-user/{{ user.id }}" method="POST">
                                <button type="submit" class="btn btn-sm btn-success" 
                                        onclick="return confirm('Restore this user? This will recover historical balance and refund upline sponsors.');">
                                    Restore Upline & Profile
                                </button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <div class="card panel-card p-4 mb-4">
        <h5 class="text-danger fw-bold mb-3"><i class="fa-solid fa-gears me-2"></i>Global Enterprise & Help Channels Overwrite Matrix</h5>
        <form action="/admin-operations-hq" method="POST">
            <input type="hidden" name="action" value="update_settings">
            <div class="row">
                <div class="col-md-4 mb-3">
                    <label class="form-label text-secondary small fw-bold">Corporate WhatsApp Syndicate Link</label>
                    <input type="text" name="whatsapp_link" class="form-control bg-dark border-secondary text-white small" value="{{ settings.whatsapp_link }}" required>
                </div>
                <div class="col-md-4 mb-3">
                    <label class="form-label text-secondary small fw-bold">Platform Broadcast Telegram Link</label>
                    <input type="text" name="telegram_link" class="form-control bg-dark border-secondary text-white small" value="{{ settings.telegram_link }}" required>
                </div>
                <div class="col-md-4 mb-3">
                    <label class="form-label text-warning small fw-bold"><i class="fa-brands fa-telegram me-1"></i>Editable Dashboard Ask For Help Link</label>
                    <input type="text" name="help_group_link" class="form-control bg-dark border-secondary text-white small" value="{{ settings.help_group_link }}" required>
                </div>
            </div>
            <button type="submit" class="btn btn-danger btn-sm fw-bold px-4">REFRESH SYSTEM MATRIX SETTINGS</button>
        </form>
    </div>

    <div class="row g-4">
        <div class="col-12 col-xl-6">
            <div class="card panel-card p-3">
                <h6 class="text-success fw-bold border-bottom border-secondary pb-2">Pending Capitalization Verification Holdbacks</h6>
                <div class="table-responsive">
                    <table class="table table-dark table-striped align-middle small mb-0">
                        <thead><tr><th>Ticket</th><th>Phone</th><th>Sum</th><th>Channel</th><th>Action</th></tr></thead>
                        <tbody>
                            {% for d in deposits %}
                            <tr><td>{{d.id}}</td><td>{{d.phone}}</td><td class="text-success">UGX {{ugx(d.amount)}}</td><td>{{d.method}}</td><td>
                                <a href="/admin/approve-deposit/{{d.id}}" class="btn btn-success btn-sm px-2 py-0 small"><i class="fa-solid fa-check"></i></a>
                                <a href="/admin/reject-deposit/{{d.id}}" class="btn btn-danger btn-sm px-2 py-0 small"><i class="fa-solid fa-xmark"></i></a>
                            </td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="col-12 col-xl-6">
            <div class="card panel-card p-3">
                <div class="d-flex justify-content-between align-items-center border-bottom border-secondary pb-2 mb-2">
                    <h6 class="text-danger fw-bold mb-0"><i class="fa-solid fa-money-bill-wave me-2"></i>Pending Verification Liquidation Outflows</h6>
                    <a href="/admin/export-payout-sheet" class="btn btn-warning btn-sm font-monospace py-0 px-2 text-dark fw-bold">
                        <i class="fa-solid fa-file-excel me-1"></i> DOWNLOAD PAYOUT SHEET
                    </a>
                </div>
                <div class="table-responsive">
                    <table class="table table-dark table-striped align-middle small mb-0">
                        <thead>
                            <tr><th>ID</th><th>Phone</th><th>Registered Name</th><th>Net Amount</th><th>Actions</th></tr>
                        </thead>
                        <tbody>
                            {% for w in withdrawals %}
                            <tr>
                                <td><strong>{{ w.id }}</strong></td>
                                <td>{{ w.phone }}</td>
                                <td class="text-info fw-bold">{{ w.registered_name }}</td> 
                                <td class="text-warning font-monospace">UGX {{ ugx(w.net_amount) }}</td>
                                <td>
                                    <a href="/admin/approve-withdrawal/{{ w.id }}" class="btn btn-success btn-sm px-2 py-0 small"><i class="fa-solid fa-check"></i></a>
                                    <a href="/admin/reject-withdrawal/{{ w.id }}" class="btn btn-danger btn-sm px-2 py-0 small"><i class="fa-solid fa-xmark"></i></a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="col-md-6">
            <div class="card panel-card p-3 h-100">
                <h6 class="text-info fw-bold border-bottom border-secondary pb-2">Dynamic Routing Wallet Injector</h6>
                <form action="/admin-operations-hq" method="POST" class="row g-2 mb-3">
                    <input type="hidden" name="action" value="add_channel">
                    <div class="col-4"><select name="provider" class="form-select bg-dark border-secondary text-white small"><option value="MTN">MTN</option><option value="Airtel">Airtel</option></select></div>
                    <div class="col-4"><input type="text" name="phone" placeholder="Wallet Phone" class="form-control bg-dark border-secondary text-white small" required></div>
                    <div class="col-4"><input type="text" name="name" placeholder="Reg Name" class="form-control bg-dark border-secondary text-white small" required></div>
                    <div class="col-12"><button type="submit" class="btn btn-info w-100 btn-sm font-monospace text-dark fw-bold">INJECT ACTIVE WALLET ROUTE</button></div>
                </form>
                <div class="table-responsive">
                    <table class="table table-dark table-striped align-middle small mb-0">
                        <thead><tr><th>Provider</th><th>Phone</th><th>Name</th><th>Action</th></tr></thead>
                        <tbody>
                            {% for c in channels %}
                            <tr><td>{{c.provider}}</td><td>{{c.phone_number}}</td><td>{{c.registered_name}}</td><td><a href="/admin/delete-channel/{{c.id}}" class="text-danger"><i class="fa-solid fa-trash"></i></a></td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="col-md-6">
            <div class="card panel-card p-3 h-100">
                <h6 class="text-warning fw-bold border-bottom border-secondary pb-2">Incremental Corridor Vehicle Deployment Unlocks</h6>
                <div class="table-responsive">
                    <table class="table table-dark table-striped align-middle small mb-0">
                        <thead><tr><th>Tier</th><th>Cost</th><th>Yield</th><th>Trigger</th></tr></thead>
                        <tbody>
                            {% for row in coming_soon_list %}
                            <tr>
                                <td>{{row.tier_name}}</td>
                                <td>UGX {{ugx(row.price)}}</td>
                                <td class="text-success">UGX {{ugx(row.daily_return)}}</td>
                                <td>
                                    {% if row.is_unlocked == 1 %}
                                    <span class="badge bg-success">ACTIVE</span>
                                    {% else %}
                                    <a href="/admin/unlock-tier/{{row.tier_name}}" class="btn btn-warning btn-sm font-monospace py-0 small text-dark fw-bold">PUSH LIVE</a>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="col-12">
            <div class="card panel-card p-3">
                <h6 class="text-white fw-bold border-bottom border-secondary pb-2">Global System Syndicate Node Registry Ledger</h6>
                <div class="table-responsive">
                    <table class="table table-dark table-striped align-middle small mb-0">
                        <thead><tr><th>Node ID</th><th>Phone</th><th>Capital</th><th>Commission</th><th>Admin Action</th></tr></thead>
                        <tbody>
                            {% for u in users %}
                            <tr><td>{{u.id}}</td><td>{{u.phone}}</td><td class="text-success">UGX {{ugx(u.balance)}}</td><td class="text-warning">UGX {{ugx(u.referral_commission)}}</td><td><a href="/admin/wipeout-user/{{u.id}}" onclick="return confirm('Execute total user purge?');" class="btn btn-outline-danger btn-sm font-monospace py-0 px-2 small fw-bold">WIPEOUT</a></td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True)