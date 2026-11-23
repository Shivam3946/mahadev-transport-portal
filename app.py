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
from sqlalchemy import func
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
    challan_no = db.Column(db.String(60), nullable=False, index=True)
    dispatch_date = db.Column(db.String(20), nullable=False, index=True)
    vehicle_no = db.Column(db.String(60), nullable=False, index=True)
    driver_name = db.Column(db.String(120), nullable=False)
    driver_mobile = db.Column(db.String(40), default="")
    owner_mobile = db.Column(db.String(40), default="")
    from_location = db.Column(db.String(160), nullable=False)
    to_location = db.Column(db.String(160), nullable=False)
    material = db.Column(db.String(160), default="Goods / माल")
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


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def bootstrap_database():
    """Safely initialize tables without ever dropping existing production data."""
    db.create_all()

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


def next_serial_number() -> int:
    max_sr = db.session.query(func.max(DispatchEntry.sr_no)).scalar()
    return (max_sr or 0) + 1


def next_challan_number() -> str:
    last_entry = DispatchEntry.query.order_by(DispatchEntry.id.desc()).first()
    if last_entry and last_entry.challan_no.isdigit():
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
    show_archived = request.args.get("archived", "0") == "1"

    query = DispatchEntry.query.filter_by(is_archived=show_archived)

    if date_filter:
        query = query.filter(DispatchEntry.dispatch_date == date_filter)

    if q:
        like_pat = f"%{q}%"
        query = query.filter(
            db.or_(
                DispatchEntry.challan_no.ilike(like_pat),
                DispatchEntry.vehicle_no.ilike(like_pat),
                DispatchEntry.driver_name.ilike(like_pat),
                DispatchEntry.from_location.ilike(like_pat),
                DispatchEntry.to_location.ilike(like_pat),
                DispatchEntry.material.ilike(like_pat),
            )
        )

    entries = query.order_by(DispatchEntry.sr_no.desc()).all()

    totals = {
        "count": len(entries),
        "freight": round(sum(e.freight_amount for e in entries), 2),
        "advance_diesel": round(sum(e.driver_advance + e.diesel + e.party_advance for e in entries), 2),
        "bilty_ac": round(sum(e.bilty_charge + e.ac_transfer for e in entries), 2),
        "deduction": round(sum(e.total_deduction for e in entries), 2),
        "balance": round(sum(e.balance for e in entries), 2),
    }

    custom_cols = CustomColumn.query.order_by(CustomColumn.sort_order.asc(), CustomColumn.id.asc()).all()
    custom_rows_raw = CustomRow.query.order_by(CustomRow.id.desc()).all()
    custom_rows = [{"id": r.id, "row_date": r.row_date, "data": r.get_data()} for r in custom_rows_raw]

    db_mode = "PostgreSQL Cloud (100% Persistent)" if "postgresql" in app.config["SQLALCHEMY_DATABASE_URI"] else "Local SQLite (Set DATABASE_URL on Render)"

    return render_template(
        "dashboard.html",
        entries=entries,
        totals=totals,
        next_sr=next_serial_number(),
        next_challan=next_challan_number(),
        today_str=date.today().isoformat(),
        q=q,
        date_filter=date_filter,
        show_archived=show_archived,
        custom_cols=custom_cols,
        custom_rows=custom_rows,
        db_mode=db_mode,
    )


@app.route("/dispatch/add", methods=["POST"])
@login_required
def add_dispatch():
    try:
        sr_val = int(request.form.get("sr_no") or next_serial_number())
        entry = DispatchEntry(
            sr_no=sr_val,
            challan_no=request.form.get("challan_no", "").strip() or next_challan_number(),
            dispatch_date=request.form.get("dispatch_date", "").strip() or date.today().isoformat(),
            vehicle_no=request.form.get("vehicle_no", "").strip().upper(),
            driver_name=request.form.get("driver_name", "").strip(),
            driver_mobile=request.form.get("driver_mobile", "").strip(),
            owner_mobile=request.form.get("owner_mobile", "").strip(),
            from_location=request.form.get("from_location", "").strip(),
            to_location=request.form.get("to_location", "").strip(),
            material=request.form.get("material", "").strip() or "Goods / माल",
            qty=to_float(request.form.get("qty")),
            receive_weight=request.form.get("receive_weight", "").strip(),
            rate=to_float(request.form.get("rate")),
            driver_advance=to_float(request.form.get("driver_advance")),
            diesel=to_float(request.form.get("diesel")),
            party_advance=to_float(request.form.get("party_advance")),
            bilty_charge=to_float(request.form.get("bilty_charge")),
            ac_transfer=to_float(request.form.get("ac_transfer")),
            remarks=request.form.get("remarks", "").strip(),
        )
        entry.recalculate()
        db.session.add(entry)
        db.session.commit()
        flash(f"चालान #{entry.challan_no} (Sr. {entry.sr_no}) सफलतापूर्वक सेव हो गया / Saved successfully!", "success")
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
            entry.challan_no = request.form.get("challan_no", "").strip()
            entry.dispatch_date = request.form.get("dispatch_date", "").strip()
            entry.vehicle_no = request.form.get("vehicle_no", "").strip().upper()
            entry.driver_name = request.form.get("driver_name", "").strip()
            entry.driver_mobile = request.form.get("driver_mobile", "").strip()
            entry.owner_mobile = request.form.get("owner_mobile", "").strip()
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
            entry.remarks = request.form.get("remarks", "").strip()
            entry.recalculate()
            db.session.commit()
            flash("रिकॉर्ड अपडेट हो गया / Record updated successfully!", "success")
            return redirect(url_for("dashboard"))
        except Exception as exc:
            db.session.rollback()
            flash(f"Update error: {exc}", "danger")

    return render_template("edit_dispatch.html", entry=entry)


@app.route("/dispatch/<int:entry_id>/toggle-archive", methods=["POST"])
@login_required
def toggle_archive_dispatch(entry_id):
    entry = db.get_or_404(DispatchEntry, entry_id)
    entry.is_archived = not entry.is_archived
    db.session.commit()
    msg = "रिकॉर्ड आर्काइव में भेजा गया / Moved to archive." if entry.is_archived else "रिकॉर्ड वापस सक्रिय किया गया / Restored to active records."
    flash(msg, "info")
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
        "freight": round(sum(e.freight_amount for e in entries), 2),
        "advance": round(sum(e.driver_advance + e.party_advance for e in entries), 2),
        "expense": round(sum(e.diesel + e.bilty_charge + e.ac_transfer for e in entries), 2),
        "balance": round(sum(e.balance for e in entries), 2),
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
        "From", "To", "Material", "Qty", "Rate", "Freight (INR)",
        "Driver Advance", "Diesel", "Party Advance", "Bilty Charge", "A/c Transfer",
        "Total Deduction", "Balance (INR)", "Remarks"
    ])
    for e in entries:
        writer.writerow([
            e.sr_no, e.challan_no, e.dispatch_date, e.vehicle_no, e.driver_name, e.driver_mobile,
            e.from_location, e.to_location, e.material, e.qty, e.rate, e.freight_amount,
            e.driver_advance, e.diesel, e.party_advance, e.bilty_charge, e.ac_transfer,
            e.total_deduction, e.balance, e.remarks
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=mahadev_transport_backup_{date.today().isoformat()}.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
