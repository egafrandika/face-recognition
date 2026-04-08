from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS
import cv2
import numpy as np
import base64
import sqlite3
import json
import os
import face_recognition
from datetime import datetime
import hashlib
import cloudinary
import cloudinary.uploader

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

cloudinary.config(
    cloud_name="dfypljeaj",
    api_key="198827775726965",
    api_secret="eRroGuOLjdHBme3jLyYO2tAn2wA",
    secure=True
)

app = Flask(__name__)
CORS(app)

DB_PATH = os.path.join(ROOT_DIR, 'payrollface.db')
_STATIC_EXT = {'.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.json'}
JAM_KELUAR_NORMAL = "17:00:00"


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _hash(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def init_db():
    conn = get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nik TEXT NOT NULL UNIQUE,
                nama TEXT NOT NULL,
                role TEXT DEFAULT 'karyawan' CHECK(role IN ('admin','karyawan')),
                password TEXT,
                gaji_pokok REAL NOT NULL DEFAULT 0,
                daily_rate REAL NOT NULL DEFAULT 0,
                overtime_rate REAL NOT NULL DEFAULT 0,
                face_encoding TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                tanggal DATE NOT NULL,
                jam_masuk TEXT,
                jam_keluar TEXT,
                overtime_hours INTEGER DEFAULT 0,
                latitude REAL,
                longitude REAL,
                status TEXT DEFAULT 'Hadir',
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS leaves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                jenis_cuti TEXT,
                tanggal DATE,
                alasan TEXT,
                attachment TEXT,
                status TEXT DEFAULT 'Pending' CHECK(status IN ('Pending','Approved','Rejected','Cancelled')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        for col, spec in [
            ('daily_rate', 'REAL NOT NULL DEFAULT 0'),
            ('overtime_rate', 'REAL NOT NULL DEFAULT 0'),
            ('password', 'TEXT'),
        ]:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {spec}")
            except sqlite3.OperationalError:
                pass

        for col, spec in [
            ('overtime_hours', 'INTEGER DEFAULT 0'),
            ('latitude', 'REAL'),
            ('longitude', 'REAL'),
        ]:
            try:
                conn.execute(f"ALTER TABLE attendance_logs ADD COLUMN {col} {spec}")
            except sqlite3.OperationalError:
                pass

        admin = conn.execute("SELECT id, password FROM users WHERE nik = 'ADMIN001'").fetchone()
        if not admin:
            conn.execute(
                "INSERT INTO users (nik, nama, role, password, gaji_pokok) VALUES (?, ?, ?, ?, ?)",
                ('ADMIN001', 'Admin HRD', 'admin', _hash('admin123'), 0)
            )
        elif not admin['password']:
            conn.execute("UPDATE users SET password = ? WHERE id = ?", (_hash('admin123'), admin['id']))

        conn.commit()
    finally:
        conn.close()


init_db()


def _decode_face(image_data):
    header, encoded = image_data.split(",", 1)
    nparr = np.frombuffer(base64.b64decode(encoded), np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    encodings = face_recognition.face_encodings(rgb)
    return encodings[0] if encodings else None


def _calc_overtime(jam_keluar):
    if not jam_keluar:
        return 0
    pk = jam_keluar.split(':')
    pn = JAM_KELUAR_NORMAL.split(':')
    diff = (int(pk[0]) * 60 + int(pk[1])) - (int(pn[0]) * 60 + int(pn[1]))
    return max(0, diff // 60)


# ─── LOGIN ────────────────────────────────────────────────

@app.route('/api/v1/login/face', methods=['POST'])
def login_face():
    data = request.json
    try:
        face = _decode_face(data.get('image', ''))
        if face is None:
            return jsonify({"status": "failed", "message": "Wajah tidak terdeteksi"})

        conn = get_db()
        try:
            users = conn.execute(
                "SELECT id, nik, nama, role, face_encoding FROM users WHERE face_encoding IS NOT NULL"
            ).fetchall()
            for u in users:
                db_enc = np.array(json.loads(u['face_encoding']))
                if face_recognition.compare_faces([db_enc], face, tolerance=0.5)[0]:
                    return jsonify({
                        "status": "success",
                        "user": {"id": u['id'], "nik": u['nik'], "nama": u['nama'], "role": u['role']}
                    })
            return jsonify({"status": "failed", "message": "Wajah tidak terdaftar dalam sistem"})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/login/manual', methods=['POST'])
def login_manual():
    data = request.json
    nik = data.get('nik', '').strip()
    pw = data.get('password', '')
    conn = get_db()
    try:
        user = conn.execute("SELECT id, nik, nama, role, password FROM users WHERE nik = ?", (nik,)).fetchone()
        if not user:
            return jsonify({"status": "failed", "message": "NIK tidak ditemukan"})
        if user['password'] != _hash(pw):
            return jsonify({"status": "failed", "message": "Password salah"})
        return jsonify({
            "status": "success",
            "user": {"id": user['id'], "nik": user['nik'], "nama": user['nama'], "role": user['role']}
        })
    finally:
        conn.close()


# ─── ATTENDANCE ───────────────────────────────────────────

@app.route('/api/v1/verify-liveness', methods=['POST'])
def verify_absensi():
    data = request.json
    image_data = data.get('image')
    absensi_type = data.get('type')
    user_id_hint = data.get('user_id')
    lat = data.get('latitude')
    lng = data.get('longitude')

    try:
        face = _decode_face(image_data)
        if face is None:
            return jsonify({"status": "failed", "message": "Wajah tidak terdeteksi"}), 200

        conn = get_db()
        try:
            if user_id_hint:
                users = conn.execute(
                    "SELECT id, nama, face_encoding FROM users WHERE id = ? AND face_encoding IS NOT NULL",
                    (user_id_hint,)
                ).fetchall()
            else:
                users = conn.execute(
                    "SELECT id, nama, face_encoding FROM users WHERE face_encoding IS NOT NULL"
                ).fetchall()

            found = None
            for u in users:
                db_enc = np.array(json.loads(u['face_encoding']))
                if face_recognition.compare_faces([db_enc], face, tolerance=0.5)[0]:
                    found = u
                    break

            if not found:
                return jsonify({"status": "failed", "message": "Wajah tidak cocok"}), 200

            now = datetime.now()
            tgl = now.strftime("%Y-%m-%d")
            jam = now.strftime("%H:%M:%S")

            log = conn.execute(
                "SELECT id FROM attendance_logs WHERE user_id = ? AND tanggal = ?",
                (found['id'], tgl)
            ).fetchone()

            if absensi_type == 'Masuk':
                if log:
                    return jsonify({"status": "error", "message": "Sudah absen masuk hari ini"}), 200
                conn.execute(
                    "INSERT INTO attendance_logs (user_id, tanggal, jam_masuk, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
                    (found['id'], tgl, jam, lat, lng)
                )
            else:
                if not log:
                    return jsonify({"status": "error", "message": "Belum absen masuk hari ini"}), 200
                ot = _calc_overtime(jam)
                conn.execute(
                    "UPDATE attendance_logs SET jam_keluar = ?, overtime_hours = ?, latitude = COALESCE(latitude, ?), longitude = COALESCE(longitude, ?) WHERE id = ?",
                    (jam, ot, lat, lng, log['id'])
                )

            conn.commit()
            return jsonify({
                "status": "success",
                "message": f"Halo, {found['nama']}!",
                "user_id": found['id']
            })
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── EMPLOYEE MANAGEMENT ─────────────────────────────────

@app.route('/api/v1/face/register', methods=['POST'])
def enroll_user():
    data = request.json
    try:
        face = _decode_face(data['image'])
        if face is None:
            return jsonify({"status": "error", "message": "Wajah tidak terdeteksi pada gambar"}), 200

        conn = get_db()
        try:
            conn.execute(
                """INSERT INTO users (nik, nama, gaji_pokok, daily_rate, overtime_rate, face_encoding, role)
                   VALUES (?, ?, ?, ?, ?, ?, 'karyawan')""",
                (data['nik'], data['nama'],
                 float(data.get('gaji_pokok', 0)),
                 float(data.get('daily_rate', 0)),
                 float(data.get('overtime_rate', 0)),
                 json.dumps(face.tolist()))
            )
            conn.commit()
            return jsonify({"status": "success", "message": "Karyawan berhasil didaftarkan!"})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/employees', methods=['GET'])
def list_employees():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, nik, nama, gaji_pokok, daily_rate, overtime_rate, created_at FROM users WHERE role = 'karyawan' ORDER BY id DESC"
        ).fetchall()
        return jsonify({"total": len(rows), "employees": [dict(r) for r in rows]})
    finally:
        conn.close()


@app.route('/api/v1/employee/data/<int:user_id>', methods=['GET'])
def get_employee_data(user_id):
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, nama, nik, gaji_pokok, daily_rate, overtime_rate FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        logs = conn.execute(
            "SELECT tanggal, jam_masuk, jam_keluar, overtime_hours, latitude, longitude, status FROM attendance_logs WHERE user_id = ? ORDER BY tanggal DESC",
            (user_id,)
        ).fetchall()
        return jsonify({
            "user": dict(user) if user else None,
            "logs": [dict(r) for r in logs]
        })
    finally:
        conn.close()


@app.route('/api/v1/employee/update/<int:user_id>', methods=['PUT'])
def update_employee(user_id):
    data = request.json
    try:
        conn = get_db()
        try:
            conn.execute(
                """UPDATE users SET nik=?, nama=?, gaji_pokok=?, daily_rate=?, overtime_rate=?
                   WHERE id=? AND role='karyawan'""",
                (data['nik'], data['nama'],
                 float(data.get('gaji_pokok', 0)),
                 float(data.get('daily_rate', 0)),
                 float(data.get('overtime_rate', 0)),
                 user_id)
            )
            conn.commit()
            return jsonify({"status": "success", "message": "Data karyawan berhasil diperbarui."})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/employee/delete/<int:user_id>', methods=['DELETE'])
def delete_employee(user_id):
    try:
        conn = get_db()
        try:
            conn.execute("DELETE FROM users WHERE id = ? AND role = 'karyawan'", (user_id,))
            conn.commit()
            return jsonify({"status": "success", "message": "Karyawan berhasil dihapus."})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── ATTENDANCE ALL (HR) ─────────────────────────────────

@app.route('/api/v1/attendance/all', methods=['GET'])
def all_attendance():
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT a.tanggal, a.jam_masuk, a.jam_keluar, a.overtime_hours,
                   a.latitude, a.longitude, a.status, u.nama, u.nik
            FROM attendance_logs a JOIN users u ON a.user_id = u.id
            WHERE strftime('%Y-%m', a.tanggal) = ?
            ORDER BY a.tanggal DESC, a.jam_masuk DESC
        """, (month,)).fetchall()
        return jsonify({"logs": [dict(r) for r in rows]})
    finally:
        conn.close()


# ─── LEAVE MANAGEMENT ────────────────────────────────────

def _save_attachment(data_url):
    """Upload attachment to Cloudinary (folder LeaveImg)."""
    if not data_url or not data_url.startswith('data:'):
        return None
    try:
        result = cloudinary.uploader.upload(
            data_url,
            folder="LeaveImg",
            resource_type="auto"
        )
        return result.get('secure_url')
    except Exception as e:
        print(f"[Cloudinary] Upload gagal: {e}")
        return None


@app.route('/api/v1/leave/request', methods=['POST'])
def request_leave():
    data = request.json
    try:
        attachment_url = _save_attachment(data.get('attachment'))
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO leaves (user_id, jenis_cuti, tanggal, alasan, attachment) VALUES (?, ?, ?, ?, ?)",
                (data.get('user_id'), data.get('jenis'), data.get('tanggal'),
                 data.get('alasan'), attachment_url)
            )
            conn.commit()
            return jsonify({"status": "success", "message": "Pengajuan cuti berhasil!"})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/leave/cancel', methods=['POST'])
def cancel_leave():
    data = request.json
    try:
        conn = get_db()
        try:
            conn.execute("UPDATE leaves SET status='Cancelled' WHERE id=? AND status='Pending'", (data.get('leave_id'),))
            conn.commit()
            return jsonify({"status": "success", "message": "Pengajuan dibatalkan."})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/leave/list', methods=['GET'])
def list_leaves():
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT l.id, u.nama as karyawan, l.jenis_cuti, l.tanggal, l.alasan, l.attachment, l.status
            FROM leaves l JOIN users u ON l.user_id = u.id ORDER BY l.id DESC
        """).fetchall()
        return jsonify({"leaves": [dict(r) for r in rows]})
    finally:
        conn.close()


@app.route('/api/v1/leave/approve', methods=['POST'])
def approve_leave():
    data = request.json
    try:
        conn = get_db()
        try:
            conn.execute(
                "UPDATE leaves SET status=? WHERE id=? AND status='Pending'",
                (data.get('action', 'Approved'), data.get('leave_id'))
            )
            conn.commit()
            return jsonify({"status": "success", "message": f"Cuti {data.get('action', 'Approved')}."})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/leave/my/<int:user_id>', methods=['GET'])
def my_leaves(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, jenis_cuti, tanggal, alasan, attachment, status FROM leaves WHERE user_id=? ORDER BY id DESC",
            (user_id,)
        ).fetchall()
        return jsonify({"leaves": [dict(r) for r in rows]})
    finally:
        conn.close()


# ─── PAYROLL ──────────────────────────────────────────────

@app.route('/api/v1/payroll/<int:user_id>', methods=['GET'])
def get_payroll(user_id):
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, nama, nik, gaji_pokok, daily_rate, overtime_rate FROM users WHERE id=?",
            (user_id,)
        ).fetchone()
        if not user:
            return jsonify({"status": "error", "message": "Karyawan tidak ditemukan"}), 404

        logs = conn.execute(
            "SELECT tanggal, jam_masuk, jam_keluar, overtime_hours, status FROM attendance_logs WHERE user_id=? AND strftime('%Y-%m', tanggal)=? ORDER BY tanggal",
            (user_id, month)
        ).fetchall()

        total_days = len(logs)
        total_ot = sum(r['overtime_hours'] or 0 for r in logs)

        gp = user['gaji_pokok'] or 0
        daily = total_days * (user['daily_rate'] or 0)
        ot_pay = total_ot * (user['overtime_rate'] or 0)

        return jsonify({
            "user": dict(user),
            "month": month,
            "total_days": total_days,
            "total_overtime_hours": total_ot,
            "gaji_pokok": gp,
            "daily_total": daily,
            "overtime_total": ot_pay,
            "grand_total": gp + daily + ot_pay,
            "logs": [dict(r) for r in logs]
        })
    finally:
        conn.close()


# ─── ADMIN FACE REGISTRATION ─────────────────────────────

@app.route('/api/v1/admin/register-face', methods=['POST'])
def admin_register_face():
    data = request.json
    try:
        face = _decode_face(data['image'])
        if face is None:
            return jsonify({"status": "error", "message": "Wajah tidak terdeteksi"}), 200

        conn = get_db()
        try:
            conn.execute("UPDATE users SET face_encoding=? WHERE id=?",
                         (json.dumps(face.tolist()), data.get('user_id')))
            conn.commit()
            return jsonify({"status": "success", "message": "Wajah berhasil didaftarkan!"})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── STATIC FILES ────────────────────────────────────────

@app.route('/')
def serve_index():
    return send_from_directory(ROOT_DIR, 'index.html')


@app.route('/<path:filename>')
def serve_frontend(filename):
    if '..' in filename or filename.startswith(('/', '\\')):
        abort(404)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _STATIC_EXT:
        abort(404)
    full = os.path.normpath(os.path.join(ROOT_DIR, filename))
    if not full.startswith(os.path.normpath(ROOT_DIR)):
        abort(403)
    if not os.path.isfile(full):
        abort(404)
    return send_from_directory(ROOT_DIR, filename)


if __name__ == '__main__':
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '5000'))
    use_https = os.environ.get('USE_HTTPS', '').lower() in ('1', 'true', 'yes')

    ssl_ctx = None
    if use_https:
        try:
            import cryptography  # noqa: F401
        except ImportError:
            raise SystemExit('USE_HTTPS=1 needs: pip install cryptography')
        ssl_ctx = 'adhoc'

    scheme = 'https' if ssl_ctx else 'http'
    print(f'Server: {scheme}://0.0.0.0:{port}/')
    app.run(debug=True, host=host, port=port, ssl_context=ssl_ctx)
