# MAHADEV TRANSPORT — Goods Transport & Logistics Portal
**Director:** Prakash Rai (प्रकाश राय)  
**Tagline:** भरोसेमंद माल ढुलाई, समय पर डिलीवरी — Reliable Freight & Seamless Logistics Partner

## Key Features
1. **Zero Data Loss Architecture:** Automatically connects to PostgreSQL (`DATABASE_URL`) on Render/Neon so data never resets on logout, restart, or redeploy. Falls back to SQLite only for local testing.
2. **Authentication + Password Set & Reset:** Secure login, password change inside dashboard, and recovery-key password reset flow if forgotten.
3. **Bilingual UI (Hindi + English):** Full Hindi + English interface with quick language toggle.
4. **Automated Billing & Calculations:** Auto-incrementing Serial Number, auto-filled Date, auto Freight (`Qty × Rate`), auto Deductions, and auto Net Balance.
5. **Dual Printable Formats with Watermark:**
   - **16-Column Daily Dispatch Register** with live Today's Summary
   - **Transport Challan / Receipt** with `MAHADEV TRANSPORT` watermark and `Director: Prakash Rai`
6. **Custom Register Builder:** Add or delete custom columns dynamically and maintain custom business records.
7. **Search, Filter, Edit, Soft-Archive & CSV Backup Export.**

## Deploy on GitHub + Render
1. Push this folder to a GitHub repository.
2. On Render, create a **PostgreSQL** database and copy its `Internal Database URL` (or use `render.yaml` Blueprint).
3. Create a **Web Service** linked to your GitHub repo:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Environment Variables:**
     - `DATABASE_URL`: `<your-postgresql-connection-string>`
     - `SECRET_KEY`: `<any-strong-random-secret>`
     - `ADMIN_RECOVERY_KEY`: `MAHADEV-PRAKASH-2026` (change to your own secret recovery code)
4. Default initial login (if no admin exists yet):
   - **Username:** `prakash`
   - **Password:** `Mahadev@123` (change immediately after first login!)
