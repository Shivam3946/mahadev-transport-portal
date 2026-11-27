import csv
import io
import json
import os
from datetime import date, datetime
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, text
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "mahadev-transport-secure-key-2026")

# Normalize PostgreSQL URL so SQLAlchemy uses psycopg2-binary cleanly
raw_db_url = os.environ.get("DATABASE_URL", "").strip()
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif raw_db_url.startswith("postgresql://") and not raw_db_url.startswith("postgresql+psycopg2://"):
    raw_db_url = raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

if not raw_db_url:
    os.makedirs(app.instance_path, exist_ok=True)
    raw_db_url = "sqlite:///" + os.path.join(app.instance_path, "mahadev_local.db")

app.config["SQLALCHEMY_DATABASE_URI"] = raw_db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "कृपया आगे बढ़ने के लिए लॉगिन करें / Please log in to continue."


# -------------------- DATABASE MODELS --------------------

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False, default="Prakash Rai")
    role = db.Column(db.String(40), nullable=False, default="Director")
    password_hash = db.Column(db.String(255), nullable=False)
    recovery_hint = db.Column(db.String(200), default="Director Recovery Key")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, raw_password: str):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)


class DispatchEntry(db.Model):
    __tablename__ = "dispatch_entries"
    id = db.Column(db.Integer, primary_key=True)
    sr_no = db.Column(db.Integer, nullable=False, index=True)
    challan_no = db.Column(db.String(60), default="", index=True)
    dispatch_date = db.Column(db.String(20), default="", index=True)
    vehicle_no = db.Column(db.String(60), default="", index=True)
    driver_name = db.Column(db.String(120), default="")
    driver_mobile = db.Column(db.String(40), default="")
    owner_mobile = db.Column(db.String(40), default="")
    party_name = db.Column(db.String(160), default="")
    from_location = db.Column(db.String(160), default="")
    to_location = db.Column(db.String(160), default="")
    material = db.Column(db.String(160), default="")
    qty = db.Column(db.Float, default=0.0)
    receive_weight = db.Column(db.String(60), default="")
    rate = db.Column(db.Float, default=0.0)
    freight_amount = db.Column(db.Float, default=0.0)
    driver_advance = db.Column(db.Float, default=0.0)
    diesel = db.Column(db.Float, default=0.0)
    party_advance = db.Column(db.Float, default=0.0)
    bilty_charge = db.Column(db.Float, default=0.0)
    ac_transfer = db.Column(db.Float, default=0.0)
    total_deduction = db.Column(db.Float, default=0.0)
    balance = db.Column(db.Float, default=0.0)
    received_amount = db.Column(db.Float, default=0.0)
    payment_status = db.Column(db.String(30), default="Pending")  # Pending | Partial | Settled
    remarks = db.Column(db.String(255), default="")
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def recalculate(self):
        self.qty = float(self.qty or 0.0)
        self.rate = float(self.rate or 0.0)
        self.driver_advance = float(self.driver_advance or 0.0)
        self.diesel = float(self.diesel or 0.0)
        self.party_advance = float(self.party_advance or 0.0)
        self.bilty_charge = float(self.bilty_charge or 0.0)
        self.ac_transfer = float(self.ac_transfer or 0.0)
        self.received_amount = float(self.received_amount or 0.0)

        self.freight_amount = round(self.qty * self.rate, 2)
        self.total_deduction = round(
            self.driver_advance
            + self.diesel
            + self.party_advance
            + self.bilty_charge
            + self.ac_transfer,
            2,
        )
        self.balance = round(self.freight_amount - self.total_deduction, 2)

        if self.payment_status not in {"Pending", "Partial", "Settled"}:
            if self.received_amount <= 0:
                self.payment_status = "Pending"
            elif self.balance > 0 and self.received_amount < self.balance:
                self.payment_status = "Partial"
            elif self.balance > 0 and self.received_amount >= self.balance:
                self.payment_status = "Settled"
            else:
                self.payment_status = "Pending"

    def to_dict(self):
        return {
            "id": self.id,
            "sr_no": self.sr_no,
            "challan_no": self.challan_no,
            "dispatch_date": self.dispatch_date,
            "vehicle_no": self.vehicle_no,
            "driver_name": self.driver_name,
            "driver_mobile": self.driver_mobile,
            "owner_mobile": self.owner_mobile,
            "party_name": self.party_name,
            "from_location": self.from_location,
            "to_location": self.to_location,
            "material": self.material,
            "qty": self.qty,
            "receive_weight": self.receive_weight,
            "rate": self.rate,
            "freight_amount": self.freight_amount,
            "driver_advance": self.driver_advance,
            "diesel": self.diesel,
            "party_advance": self.party_advance,
            "bilty_charge": self.bilty_charge,
            "ac_transfer": self.ac_transfer,
            "total_deduction": self.total_deduction,
            "balance": self.balance,
            "received_amount": self.received_amount,
            "payment_status": self.payment_status,
            "remarks": self.remarks,
        }


class CustomColumn(db.Model):
    __tablename__ = "custom_columns"
    id = db.Column(db.Integer, primary_key=True)
    name_en = db.Column(db.String(100), nullable=False)
    name_hi = db.Column(db.String(100), default="")
    col_type = db.Column(db.String(30), default="text")  # text | number | date
    sort_order = db.Column(db.Integer, default=0)


class CustomRow(db.Model):
    __tablename__ = "custom_rows"
    id = db.Column(db.Integer, primary_key=True)
    row_date = db.Column(db.String(20), nullable=False)
    data_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_data(self):
        try:
            return json.loads(self.data_json or "{}")
        except Exception:
            return {}


class PaymentVoucher(db.Model):
    __tablename__ = "payment_vouchers"
    id = db.Column(db.Integer, primary_key=True)
    voucher_no = db.Column(db.String(80), default="")
    voucher_date = db.Column(db.String(20), default="")
    debited_to = db.Column(db.String(160), default="MAHADEV TRANSPORT")
    pan_no = db.Column(db.String(40), default="")
    top_bank = db.Column(db.String(120), default="")
    top_ac = db.Column(db.String(80), default="")
    ifsc_code = db.Column(db.String(40), default="")
    rupees_words = db.Column(db.String(300), default="")
    bot_bank = db.Column(db.String(120), default="")
    bot_ac = db.Column(db.String(80), default="")
    cheque_no = db.Column(db.String(80), default="")
    cheque_date = db.Column(db.String(20), default="")
    total_deduct = db.Column(db.Float, default=0.0)
    net_payable = db.Column(db.Float, default=0.0)
    routes_summary = db.Column(db.Text, default="")
    vehicles_summary = db.Column(db.Text, default="")
    payload_json = db.Column(db.Text, nullable=False)
    is_archived = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def sync_dispatch_columns():
    """Safely add new optional columns to dispatch_entries without dropping data."""
    inspector = inspect(db.engine)
    if not inspector.has_table("dispatch_entries"):
        return

    existing_cols = {col["name"] for col in inspector.get_columns("dispatch_entries")}
    alter_statements = []

    if "party_name" not in existing_cols:
        alter_statements.append("ALTER TABLE dispatch_entries ADD COLUMN party_name VARCHAR(160) DEFAULT ''")
    if "received_amount" not in existing_cols:
        alter_statements.append("ALTER TABLE dispatch_entries ADD COLUMN received_amount FLOAT DEFAULT 0.0")
    if "payment_status" not in existing_cols:
        alter_statements.append("ALTER TABLE dispatch_entries ADD COLUMN payment_status VARCHAR(30) DEFAULT 'Pending'")

    for stmt in alter_statements:
        db.session.execute(text(stmt))
    if alter_statements:
        db.session.commit()


def sync_payment_voucher_columns():
    """Safely add missing columns to payment_vouchers without dropping data."""
    inspector = inspect(db.engine)
    if not inspector.has_table("payment_vouchers"):
        return

    existing_cols = {col["name"] for col in inspector.get_columns("payment_vouchers")}
    alter_statements = []

    if "routes_summary" not in existing_cols:
        alter_statements.append("ALTER TABLE payment_vouchers ADD COLUMN routes_summary TEXT DEFAULT ''")
    if "vehicles_summary" not in existing_cols:
        alter_statements.append("ALTER TABLE payment_vouchers ADD COLUMN vehicles_summary TEXT DEFAULT ''")
    if "is_archived" not in existing_cols:
        alter_statements.append("ALTER TABLE payment_vouchers ADD COLUMN is_archived BOOLEAN DEFAULT FALSE")
    if "updated_at" not in existing_cols:
        alter_statements.append("ALTER TABLE payment_vouchers ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    if "created_at" not in existing_cols:
        alter_statements.append("ALTER TABLE payment_vouchers ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    for stmt in alter_statements:
        db.session.execute(text(stmt))
    if alter_statements:
        db.session.commit()


def bootstrap_database():
    """Safely initialize tables and columns without ever dropping existing production data."""
    db.create_all()
    sync_dispatch_columns()
    sync_payment_voucher_columns()

    if User.query.count() == 0:
        default_admin = User(
            username="prakash",
            full_name="Prakash Rai (प्रकाश राय)",
            role="Director",
            recovery_hint="Use ADMIN_RECOVERY_KEY to reset password",
        )
        default_admin.set_password("Mahadev@123")
        db.session.add(default_admin)
        db.session.commit()

    if CustomColumn.query.count() == 0:
        starter_cols = [
            CustomColumn(name_en="Party / Firm Name", name_hi="पार्टी / फर्म नाम", col_type="text", sort_order=1),
            CustomColumn(name_en="Vehicle No.", name_hi="गाड़ी नंबर", col_type="text", sort_order=2),
            CustomColumn(name_en="Toll / Loading Expense (₹)", name_hi="टोल / लोडिंग खर्च", col_type="number", sort_order=3),
            CustomColumn(name_en="Payment Status", name_hi="भुगतान स्थिति", col_type="text", sort_order=4),
        ]
        db.session.add_all(starter_cols)
        db.session.commit()


with app.app_context():
    bootstrap_database()


def to_float(val, default=0.0):
    try:
        if val is None or str(val).strip() == "":
            return default
        return float(val)
    except ValueError:
        return default


def _compute_voucher_totals(routes_list):
    total_deduct = 0.0
    total_net = 0.0
    route_names = []
    vehicle_nos = []

    for grp in (routes_list or []):
        r_name = (grp.get("route") or "").strip()
        m_name = (grp.get("material") or "").strip()
        if r_name or m_name:
            route_names.append(f"{r_name or '-'} ({m_name})" if m_name else r_name)

        for row in (grp.get("rows") or []):
            veh = (row.get("veh") or "").strip()
            if veh:
                vehicle_nos.append(veh)

            cqty = to_float(row.get("cqty"))
            rqty = to_float(row.get("rqty"))
            raw_fqty = str(row.get("fqty") if row.get("fqty") is not None else "").strip()
            fqty = to_float(raw_fqty) if raw_fqty != "" else (rqty if rqty > 0 else cqty)
            rate = to_float(row.get("rate"))

            samt = to_float(row.get("samt"))
            bilty = to_float(row.get("bilty"))
            adv = to_float(row.get("adv"))
            party_adv = to_float(row.get("party_adv"))
            trans = to_float(row.get("trans"))
            fuel = to_float(row.get("fuel"))
            gps_amt = to_float(row.get("gps_amt"))
            tarpaulin = to_float(row.get("tarpaulin"))

            freight_amt = fqty * rate
            row_deduct = samt + bilty + adv + party_adv + trans + fuel + gps_amt + tarpaulin
            row_net = freight_amt - row_deduct

            total_deduct += row_deduct
            total_net += row_net

    return (
        round(total_deduct, 2),
        round(total_net, 2),
        ", ".join(dict.fromkeys(route_names)),
        ", ".join(dict.fromkeys(vehicle_nos)),
    )


def next_serial_number() -> int:
    max_sr = db.session.query(func.max(DispatchEntry.sr_no)).scalar()
    return (max_sr or 0) + 1


def next_challan_number() -> str:
    last_entry = DispatchEntry.query.order_by(DispatchEntry.id.desc()).first()
    if last_entry and last_entry.challan_no and last_entry.challan_no.isdigit():
        return str(int(last_entry.challan_no) + 1)
    return "1209"


# -------------------- AUTH & PASSWORD ROUTES --------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter(func.lower(User.username) == username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash("स्वागत है Prakash Rai जी! लॉगिन सफल रहा / Welcome back!", "success")
            return redirect(url_for("dashboard"))
        flash("गलत यूज़रनेम या पासवर्ड / Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        recovery_key = request.form.get("recovery_key", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        expected_key = os.environ.get("ADMIN_RECOVERY_KEY", "MAHADEV-PRAKASH-2026")
        user = User.query.filter(func.lower(User.username) == username).first()

        if not user:
            flash("यूज़र नहीं मिला / Username not found.", "danger")
        elif recovery_key != expected_key:
            flash("गलत रिकवरी की / Invalid Admin Recovery Key.", "danger")
        elif len(new_password) < 6:
            flash("नया पासवर्ड कम से कम 6 अक्षरों का होना चाहिए / Password must be at least 6 characters.", "danger")
        elif new_password != confirm_password:
            flash("दोनों पासवर्ड मेल नहीं खा रहे / Passwords do not match.", "danger")
        else:
            user.set_password(new_password)
            db.session.commit()
            flash("पासवर्ड सफलतापूर्वक रीसेट हो गया! अब लॉगिन करें / Password reset successful!", "success")
            return redirect(url_for("login"))

    return render_template("reset_password.html")


@app.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current_pw = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    confirm_pw = request.form.get("confirm_password", "")

    if not current_user.check_password(current_pw):
        flash("पुराना पासवर्ड गलत है / Current password is incorrect.", "danger")
    elif len(new_pw) < 6:
        flash("नया पासवर्ड कम से कम 6 अक्षरों का रखें / New password must be at least 6 characters.", "danger")
    elif new_pw != confirm_pw:
        flash("नया पासवर्ड और कन्फर्म पासवर्ड समान नहीं हैं / New passwords do not match.", "danger")
    else:
        current_user.set_password(new_pw)
        db.session.commit()
        flash("पासवर्ड अपडेट हो गया / Password updated securely!", "success")

    return redirect(url_for("dashboard"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("आप सुरक्षित रूप से लॉगआउट हो गए हैं। आपका सारा डेटा सुरक्षित है / Logged out safely. All records are preserved.", "info")
    return redirect(url_for("login"))


# -------------------- MAIN DASHBOARD & DISPATCH CRUD --------------------

@app.route("/")
@login_required
def dashboard():
    q = request.args.get("q", "").strip()
    date_filter = request.args.get("date", "").strip()
    status_filter = request.args.get("status", "").strip()
    show_archived = request.args.get("archived", "0") == "1"

    query = DispatchEntry.query.filter_by(is_archived=show_archived)

    if date_filter:
        query = query.filter(DispatchEntry.dispatch_date == date_filter)

    if status_filter in {"Pending", "Partial", "Settled"}:
        query = query.filter(DispatchEntry.payment_status == status_filter)

    if q:
        like_pat = f"%{q}%"
        query = query.filter(
            db.or_(
                DispatchEntry.challan_no.ilike(like_pat),
                DispatchEntry.vehicle_no.ilike(like_pat),
                DispatchEntry.driver_name.ilike(like_pat),
                DispatchEntry.party_name.ilike(like_pat),
                DispatchEntry.from_location.ilike(like_pat),
                DispatchEntry.to_location.ilike(like_pat),
                DispatchEntry.material.ilike(like_pat),
            )
        )

    entries = query.order_by(DispatchEntry.sr_no.desc()).all()

    total_received = round(sum(to_float(e.received_amount) for e in entries), 2)
    total_balance = round(sum(to_float(e.balance) for e in entries), 2)
    pending_party_amount = round(
        sum(max(to_float(e.balance) - to_float(e.received_amount), 0.0) for e in entries), 2
    )

    totals = {
        "count": len(entries),
        "freight": round(sum(to_float(e.freight_amount) for e in entries), 2),
        "advance_diesel": round(
            sum(to_float(e.driver_advance) + to_float(e.diesel) + to_float(e.party_advance) for e in entries), 2
        ),
        "bilty_ac": round(sum(to_float(e.bilty_charge) + to_float(e.ac_transfer) for e in entries), 2),
        "deduction": round(sum(to_float(e.total_deduction) for e in entries), 2),
        "balance": total_balance,
        "received": total_received,
        "pending_party": pending_party_amount,
    }

    custom_cols = CustomColumn.query.order_by(CustomColumn.sort_order.asc(), CustomColumn.id.asc()).all()
    custom_rows_raw = CustomRow.query.order_by(CustomRow.id.desc()).all()
    custom_rows = [{"id": r.id, "row_date": r.row_date, "data": r.get_data()} for r in custom_rows_raw]

    db_mode = (
        "PostgreSQL Cloud (100% Persistent)"
        if "postgresql" in app.config["SQLALCHEMY_DATABASE_URI"]
        else "Local SQLite (Set DATABASE_URL on Render)"
    )

    return render_template(
        "dashboard.html",
        entries=entries,
        totals=totals,
        next_sr=next_serial_number(),
        next_challan=next_challan_number(),
        today_str=date.today().isoformat(),
        q=q,
        date_filter=date_filter,
        status_filter=status_filter,
        show_archived=show_archived,
        custom_cols=custom_cols,
        custom_rows=custom_rows,
        db_mode=db_mode,
    )


@app.route("/dispatch/add", methods=["POST"])
@login_required
def add_dispatch():
    try:
        raw_sr = (request.form.get("sr_no") or "").strip()
        sr_val = int(float(raw_sr)) if raw_sr else next_serial_number()
        status_val = request.form.get("payment_status", "Pending").strip()
        if status_val not in {"Pending", "Partial", "Settled"}:
            status_val = "Pending"

        entry = DispatchEntry(
            sr_no=sr_val if sr_val > 0 else next_serial_number(),
            challan_no=request.form.get("challan_no", "").strip(),
            dispatch_date=request.form.get("dispatch_date", "").strip(),
            vehicle_no=request.form.get("vehicle_no", "").strip().upper(),
            driver_name=request.form.get("driver_name", "").strip(),
            driver_mobile=request.form.get("driver_mobile", "").strip(),
            owner_mobile=request.form.get("owner_mobile", "").strip(),
            party_name=request.form.get("party_name", "").strip(),
            from_location=request.form.get("from_location", "").strip(),
            to_location=request.form.get("to_location", "").strip(),
            material=request.form.get("material", "").strip(),
            qty=to_float(request.form.get("qty")),
            receive_weight=request.form.get("receive_weight", "").strip(),
            rate=to_float(request.form.get("rate")),
            driver_advance=to_float(request.form.get("driver_advance")),
            diesel=to_float(request.form.get("diesel")),
            party_advance=to_float(request.form.get("party_advance")),
            bilty_charge=to_float(request.form.get("bilty_charge")),
            ac_transfer=to_float(request.form.get("ac_transfer")),
            received_amount=to_float(request.form.get("received_amount")),
            payment_status=status_val,
            remarks=request.form.get("remarks", "").strip(),
        )
        entry.recalculate()
        db.session.add(entry)
        db.session.commit()
        label = f"चालान #{entry.challan_no}" if entry.challan_no else f"Sr. {entry.sr_no}"
        flash(f"{label} सफलतापूर्वक सेव हो गया / Saved successfully!", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"त्रुटि / Error saving entry: {exc}", "danger")

    return redirect(url_for("dashboard"))


@app.route("/dispatch/<int:entry_id>/edit", methods=["GET", "POST"])
@login_required
def edit_dispatch(entry_id):
    entry = db.get_or_404(DispatchEntry, entry_id)
    if request.method == "POST":
        try:
            status_val = request.form.get("payment_status", entry.payment_status or "Pending").strip()
            if status_val not in {"Pending", "Partial", "Settled"}:
                status_val = "Pending"

            entry.challan_no = request.form.get("challan_no", "").strip()
            entry.dispatch_date = request.form.get("dispatch_date", "").strip()
            entry.vehicle_no = request.form.get("vehicle_no", "").strip().upper()
            entry.driver_name = request.form.get("driver_name", "").strip()
            entry.driver_mobile = request.form.get("driver_mobile", "").strip()
            entry.owner_mobile = request.form.get("owner_mobile", "").strip()
            entry.party_name = request.form.get("party_name", "").strip()
            entry.from_location = request.form.get("from_location", "").strip()
            entry.to_location = request.form.get("to_location", "").strip()
            entry.material = request.form.get("material", "").strip()
            entry.qty = to_float(request.form.get("qty"))
            entry.receive_weight = request.form.get("receive_weight", "").strip()
            entry.rate = to_float(request.form.get("rate"))
            entry.driver_advance = to_float(request.form.get("driver_advance"))
            entry.diesel = to_float(request.form.get("diesel"))
            entry.party_advance = to_float(request.form.get("party_advance"))
            entry.bilty_charge = to_float(request.form.get("bilty_charge"))
            entry.ac_transfer = to_float(request.form.get("ac_transfer"))
            entry.received_amount = to_float(request.form.get("received_amount"))
            entry.payment_status = status_val
            entry.remarks = request.form.get("remarks", "").strip()
            entry.recalculate()
            db.session.commit()
            flash("रिकॉर्ड अपडेट हो गया / Record updated successfully!", "success")
            return redirect(url_for("dashboard"))
        except Exception as exc:
            db.session.rollback()
            flash(f"Update error: {exc}", "danger")

    return render_template("edit_dispatch.html", entry=entry)


@app.route("/dispatch/<int:entry_id>/payment", methods=["POST"])
@login_required
def update_dispatch_payment(entry_id):
    entry = db.get_or_404(DispatchEntry, entry_id)
    try:
        entry.received_amount = to_float(request.form.get("received_amount"))
        status_val = request.form.get("payment_status", "").strip()
        if status_val in {"Pending", "Partial", "Settled"}:
            entry.payment_status = status_val
        else:
            if entry.received_amount <= 0:
                entry.payment_status = "Pending"
            elif entry.balance > 0 and entry.received_amount < entry.balance:
                entry.payment_status = "Partial"
            elif entry.balance > 0 and entry.received_amount >= entry.balance:
                entry.payment_status = "Settled"
            else:
                entry.payment_status = "Pending"
        db.session.commit()
        label = f"चालान #{entry.challan_no}" if entry.challan_no else f"Sr. {entry.sr_no}"
        flash(f"भुगतान स्थिति ({entry.payment_status}) अपडेट हो गई — {label}!", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Payment update error: {exc}", "danger")
    return redirect(url_for("dashboard"))


@app.route("/dispatch/<int:entry_id>/toggle-archive", methods=["POST"])
@login_required
def toggle_archive_dispatch(entry_id):
    entry = db.get_or_404(DispatchEntry, entry_id)
    entry.is_archived = not entry.is_archived
    db.session.commit()
    msg = (
        "रिकॉर्ड आर्काइव में भेजा गया / Moved to archive."
        if entry.is_archived
        else "रिकॉर्ड वापस सक्रिय किया गया / Restored to active records."
    )
    flash(msg, "info")
    return redirect(url_for("dashboard"))


@app.route("/dispatch/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_dispatch(entry_id):
    entry = db.get_or_404(DispatchEntry, entry_id)
    label = f"चालान #{entry.challan_no}" if entry.challan_no else f"Sr. {entry.sr_no}"
    try:
        db.session.delete(entry)
        db.session.commit()
        flash(f"रिकॉर्ड ({label}) स्थायी रूप से डिलीट हो गया / Permanently deleted.", "warning")
    except Exception as exc:
        db.session.rollback()
        flash(f"डिलीट करने में त्रुटि / Delete error: {exc}", "danger")
    return redirect(url_for("dashboard"))


# -------------------- PRINTABLE FORMATS (REGISTER & CHALLAN) --------------------

@app.route("/print/register")
@login_required
def print_register():
    date_filter = request.args.get("date", "").strip()
    query = DispatchEntry.query.filter_by(is_archived=False)
    if date_filter:
        query = query.filter(DispatchEntry.dispatch_date == date_filter)
    entries = query.order_by(DispatchEntry.sr_no.asc()).all()

    summary = {
        "freight": round(sum(to_float(e.freight_amount) for e in entries), 2),
        "advance": round(sum(to_float(e.driver_advance) + to_float(e.party_advance) for e in entries), 2),
        "expense": round(sum(to_float(e.diesel) + to_float(e.bilty_charge) + to_float(e.ac_transfer) for e in entries), 2),
        "balance": round(sum(to_float(e.balance) for e in entries), 2),
        "received": round(sum(to_float(e.received_amount) for e in entries), 2),
    }
    return render_template(
        "print_register.html",
        entries=entries,
        summary=summary,
        register_date=date_filter or date.today().isoformat(),
    )


@app.route("/print/challan/<int:entry_id>")
@login_required
def print_challan(entry_id):
    entry = db.get_or_404(DispatchEntry, entry_id)
    return render_template("print_challan.html", entry=entry)


# -------------------- PAYMENT VOUCHER ROUTES --------------------

@app.route("/payment-voucher-form", methods=["GET"])
@login_required
def payment_voucher_form():
    today_str = datetime.now().strftime("%Y-%m-%d")
    q = (request.args.get("q") or "").strip().lower()
    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()
    view_tab = (request.args.get("tab") or "active").strip().lower()

    query = PaymentVoucher.query.filter_by(is_archived=(view_tab == "archived"))
    if date_from:
        query = query.filter(PaymentVoucher.voucher_date >= date_from)
    if date_to:
        query = query.filter(PaymentVoucher.voucher_date <= date_to)

    all_vouchers = query.order_by(PaymentVoucher.id.desc()).all()
    if q:
        filtered = []
        for v in all_vouchers:
            hay = " ".join([
                v.voucher_no or "",
                v.voucher_date or "",
                v.debited_to or "",
                v.routes_summary or "",
                v.vehicles_summary or "",
                f"{v.net_payable or 0:.2f}",
            ]).lower()
            if q in hay:
                filtered.append(v)
        all_vouchers = filtered

    period_total_payable = round(sum((v.net_payable or 0.0) for v in all_vouchers), 2)
    period_total_deduct = round(sum((v.total_deduct or 0.0) for v in all_vouchers), 2)

    return render_template(
        "payment_voucher_form.html",
        today_str=today_str,
        vouchers=all_vouchers,
        q=request.args.get("q") or "",
        date_from=date_from,
        date_to=date_to,
        view_tab=view_tab,
        period_total_payable=period_total_payable,
        period_total_deduct=period_total_deduct,
    )


@app.route("/payment-voucher/save", methods=["POST"])
@login_required
def save_payment_voucher():
    try:
        data = request.get_json(silent=True) or {}
        raw_vid = data.get("voucher_id")
        voucher_id = int(raw_vid) if str(raw_vid or "").strip().isdigit() else None

        routes_list = data.get("routes") or []
        calc_deduct, calc_net, routes_sum, vehicles_sum = _compute_voucher_totals(routes_list)

        if voucher_id is not None:
            v = db.session.get(PaymentVoucher, voucher_id)
            if not v:
                return jsonify({"ok": False, "error": "Voucher not found"}), 404
        else:
            v = PaymentVoucher()
            db.session.add(v)

        data["total_deduct"] = calc_deduct
        data["net_payable"] = calc_net

        v.voucher_no = (data.get("voucher_no") or "").strip()
        v.voucher_date = (data.get("voucher_date") or "").strip()
        v.debited_to = (data.get("debited_to") or "MAHADEV TRANSPORT").strip()
        v.pan_no = (data.get("pan_no") or "").strip()
        v.top_bank = (data.get("top_bank") or "").strip()
        v.top_ac = (data.get("top_ac") or "").strip()
        v.ifsc_code = (data.get("ifsc_code") or "").strip()
        v.rupees_words = (data.get("rupees_words") or "").strip()
        v.bot_bank = (data.get("bot_bank") or "").strip()
        v.bot_ac = (data.get("bot_ac") or "").strip()
        v.cheque_no = (data.get("cheque_no") or "").strip()
        v.cheque_date = (data.get("cheque_date") or "").strip()
        v.total_deduct = calc_deduct
        v.net_payable = calc_net
        v.routes_summary = routes_sum
        v.vehicles_summary = vehicles_sum
        v.payload_json = json.dumps(data, ensure_ascii=False)

        db.session.commit()
        return jsonify({
            "ok": True,
            "voucher_id": v.id,
            "total_deduct": calc_deduct,
            "net_payable": calc_net,
        })
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/payment-voucher/<int:voucher_id>/archive", methods=["POST"])
@login_required
def toggle_archive_payment_voucher(voucher_id):
    v = db.get_or_404(PaymentVoucher, voucher_id)
    v.is_archived = not bool(v.is_archived)
    db.session.commit()
    flash("Voucher archive status updated.", "success")
    return redirect(url_for("payment_voucher_form", tab="archived" if v.is_archived else "active"))


@app.route("/payment-voucher/<int:voucher_id>/delete", methods=["POST"])
@login_required
def delete_payment_voucher(voucher_id):
    v = db.get_or_404(PaymentVoucher, voucher_id)
    tab = "archived" if v.is_archived else "active"
    db.session.delete(v)
    db.session.commit()
    flash("Payment voucher permanently deleted.", "success")
    return redirect(url_for("payment_voucher_form", tab=tab))


# -------------------- CUSTOM REGISTER (DYNAMIC ADD / DELETE COLUMNS) --------------------

@app.route("/custom-register/columns/add", methods=["POST"])
@login_required
def add_custom_column():
    name_en = request.form.get("name_en", "").strip()
    name_hi = request.form.get("name_hi", "").strip()
    col_type = request.form.get("col_type", "text").strip()
    if name_en:
        max_order = db.session.query(func.max(CustomColumn.sort_order)).scalar() or 0
        col = CustomColumn(name_en=name_en, name_hi=name_hi, col_type=col_type, sort_order=max_order + 1)
        db.session.add(col)
        db.session.commit()
        flash(f"नया कॉलम '{name_en}' जोड़ा गया / Column added!", "success")
    return redirect(url_for("dashboard") + "#custom-register")


@app.route("/custom-register/columns/<int:col_id>/delete", methods=["POST"])
@login_required
def delete_custom_column(col_id):
    col = db.get_or_404(CustomColumn, col_id)
    db.session.delete(col)
    db.session.commit()
    flash(f"कॉलम '{col.name_en}' हटाया गया / Column removed.", "info")
    return redirect(url_for("dashboard") + "#custom-register")


@app.route("/custom-register/rows/add", methods=["POST"])
@login_required
def add_custom_row():
    cols = CustomColumn.query.order_by(CustomColumn.sort_order.asc(), CustomColumn.id.asc()).all()
    row_date = request.form.get("row_date", "").strip() or date.today().isoformat()
    payload = {}
    for c in cols:
        payload[str(c.id)] = request.form.get(f"col_{c.id}", "").strip()
    row = CustomRow(row_date=row_date, data_json=json.dumps(payload, ensure_ascii=False))
    db.session.add(row)
    db.session.commit()
    flash("कस्टम रजिस्टर एंट्री सेव हो गई / Custom register row saved!", "success")
    return redirect(url_for("dashboard") + "#custom-register")


@app.route("/custom-register/rows/<int:row_id>/delete", methods=["POST"])
@login_required
def delete_custom_row(row_id):
    row = db.get_or_404(CustomRow, row_id)
    db.session.delete(row)
    db.session.commit()
    flash("कस्टम एंट्री हटाई गई / Custom row deleted.", "info")
    return redirect(url_for("dashboard") + "#custom-register")


# -------------------- CSV BACKUP EXPORT --------------------

@app.route("/export/csv")
@login_required
def export_csv():
    entries = DispatchEntry.query.filter_by(is_archived=False).order_by(DispatchEntry.sr_no.asc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Sr No", "Challan No", "Date", "Vehicle No", "Driver Name", "Driver Mobile",
        "Party Name", "From", "To", "Material", "Qty", "Rate", "Freight (INR)",
        "Driver Advance", "Diesel", "Party Advance", "Bilty Charge", "A/c Transfer",
        "Total Deduction", "Balance (INR)", "Received Amount (INR)", "Payment Status", "Remarks"
    ])
    for e in entries:
        writer.writerow([
            e.sr_no, e.challan_no, e.dispatch_date, e.vehicle_no, e.driver_name, e.driver_mobile,
            e.party_name, e.from_location, e.to_location, e.material, e.qty, e.rate, e.freight_amount,
            e.driver_advance, e.diesel, e.party_advance, e.bilty_charge, e.ac_transfer,
            e.total_deduction, e.balance, e.received_amount, e.payment_status, e.remarks
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=mahadev_transport_backup_{date.today().isoformat()}.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
