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
import threading
import time
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
BACKUP_DIR = os.path.join(ROOT_DIR, 'backup')
BACKUP_INTERVAL_SEC = int(os.environ.get('BACKUP_INTERVAL_SEC', '3600'))
_STATIC_EXT = {'.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.json'}
JAM_KELUAR_NORMAL = "17:00:00"
# Jam kerja efektif per bulan (pembagi upah lembur umum)
JAM_KERJA_BULAN_PEMBAGI = 173
TUNJANGAN_STAFF_PER_HARI = 25_000
TUNJANGAN_SUPERVISOR_PER_HARI = 35_000

def _get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    return row["value"]


def _get_ppn_persen(conn):
    """Persen potongan PPN dari penghasilan bruto slip (0–100), default 12."""
    raw = _get_setting(conn, "ppn_persen", "12")
    try:
        p = float(raw)
        return max(0.0, min(100.0, p))
    except (TypeError, ValueError):
        return 12.0


def _next_nip(conn):
    """NIP format: NIP + YY + MM + '-' + urutan 3 digit (per bulan)."""
    now = datetime.now()
    yy = now.strftime('%y')
    mm = now.strftime('%m')
    prefix = f'NIP{yy}{mm}-'
    row = conn.execute(
        "SELECT nip FROM users WHERE nip LIKE ? ORDER BY nip DESC LIMIT 1",
        (prefix + '%',)
    ).fetchone()
    nxt = 1
    if row and row['nip']:
        val = row['nip']
        if val.startswith(prefix) and len(val) > len(prefix):
            try:
                nxt = int(val[len(prefix):]) + 1
            except ValueError:
                pass
    return f'{prefix}{nxt:03d}'


def _normalize_tunjangan_tipe(raw):
    t = (raw or 'staff').strip().lower()
    return 'supervisor' if t == 'supervisor' else 'staff'


def _tunjangan_per_hari(tipe):
    return float(
        TUNJANGAN_SUPERVISOR_PER_HARI
        if _normalize_tunjangan_tipe(tipe) == 'supervisor'
        else TUNJANGAN_STAFF_PER_HARI
    )


def _tarif_lembur_per_jam(gaji_pokok):
    """Upah lembur per jam = (gaji pokok / 173) × 1,5"""
    g = float(gaji_pokok or 0)
    return (g / JAM_KERJA_BULAN_PEMBAGI) * 1.5 if g > 0 else 0.0


def _sync_karyawan_payroll_fields(conn):
    """Samakan daily_rate & overtime_rate dengan tunjangan tipe dan formula lembur."""
    rows = conn.execute(
        "SELECT id, gaji_pokok, tunjangan_tipe FROM users WHERE role = 'karyawan'"
    ).fetchall()
    for r in rows:
        tp = _normalize_tunjangan_tipe(r['tunjangan_tipe'])
        daily = _tunjangan_per_hari(tp)
        ot = _tarif_lembur_per_jam(r['gaji_pokok'])
        conn.execute(
            "UPDATE users SET tunjangan_tipe = ?, daily_rate = ?, overtime_rate = ? WHERE id = ?",
            (tp, daily, ot, r['id'])
        )


def _log_change(conn, entity, record_id, action, actor_id, actor_name, detail):
    conn.execute(
        """INSERT INTO change_history (entity, record_id, action, changed_by_user_id, changed_by_name, detail)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (entity, record_id, action, actor_id, actor_name or None, detail or '')
    )


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _hash(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def _user_is_superadmin(conn, user_id):
    """True jika user_id terdaftar di tabel superadmin."""
    if user_id is None:
        return False
    row = conn.execute(
        "SELECT 1 FROM superadmin WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row is not None


def _login_user_payload(conn, row):
    """Objek user untuk respons login (manual & wajah)."""
    nip_val = row["nip"] or row["nik"]
    uid = row["id"]
    return {
        "id": uid,
        "nip": nip_val,
        "nama": row["nama"],
        "role": row["role"],
        "superadmin": _user_is_superadmin(conn, uid),
    }


_backup_lock = threading.Lock()
_last_scheduled_backup_at = None
_last_scheduled_backup_name = None
_last_manual_backup_at = None
_last_manual_backup_name = None


def _ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def _perform_database_backup(trigger):
    """
    Salin database aktif ke backup/ dengan sqlite3.backup (aman untuk WAL).
    trigger: 'scheduled' | 'manual'
    """
    global _last_scheduled_backup_at, _last_scheduled_backup_name
    global _last_manual_backup_at, _last_manual_backup_name

    _ensure_backup_dir()
    dest_name = f"payrollface_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    dest_path = os.path.join(BACKUP_DIR, dest_name)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with _backup_lock:
        src_conn = sqlite3.connect(DB_PATH, timeout=60)
        try:
            dest_conn = sqlite3.connect(dest_path)
            try:
                src_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        finally:
            src_conn.close()

    if trigger == 'scheduled':
        _last_scheduled_backup_at = ts
        _last_scheduled_backup_name = dest_name
    else:
        _last_manual_backup_at = ts
        _last_manual_backup_name = dest_name

    return {"ok": True, "filename": dest_name, "at": ts, "trigger": trigger}


def _list_backup_files():
    _ensure_backup_dir()
    out = []
    try:
        names = sorted(os.listdir(BACKUP_DIR), reverse=True)
    except OSError:
        return out
    for name in names:
        if not name.endswith('.db'):
            continue
        full = os.path.join(BACKUP_DIR, name)
        try:
            st = os.stat(full)
            out.append({
                "filename": name,
                "size_bytes": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            })
        except OSError:
            continue
    return out


def _hourly_backup_loop():
    while True:
        time.sleep(BACKUP_INTERVAL_SEC)
        try:
            _perform_database_backup('scheduled')
        except Exception as e:
            print(f"[backup] Otomatis gagal: {e}")


def start_scheduled_database_backups():
    t = threading.Thread(target=_hourly_backup_loop, daemon=True, name='payrollface-db-backup')
    t.start()


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
                foto_masuk TEXT,
                foto_keluar TEXT,
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
            CREATE TABLE IF NOT EXISTS change_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity TEXT NOT NULL,
                record_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                changed_by_user_id INTEGER,
                changed_by_name TEXT,
                detail TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_change_history_lookup ON change_history (entity, record_id);
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
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
            ('foto_masuk', 'TEXT'),
            ('foto_keluar', 'TEXT'),
        ]:
            try:
                conn.execute(f"ALTER TABLE attendance_logs ADD COLUMN {col} {spec}")
            except sqlite3.OperationalError:
                pass

        try:
            conn.execute("ALTER TABLE users ADD COLUMN nip TEXT")
        except sqlite3.OperationalError:
            pass

        conn.execute("UPDATE users SET nip = nik WHERE nip IS NULL OR nip = ''")

        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN tunjangan_tipe TEXT DEFAULT 'staff'"
            )
        except sqlite3.OperationalError:
            pass
        conn.execute(
            "UPDATE users SET tunjangan_tipe = 'staff' WHERE tunjangan_tipe IS NULL OR TRIM(tunjangan_tipe) = ''"
        )
        conn.execute(
            """UPDATE users SET tunjangan_tipe = 'supervisor'
               WHERE role = 'karyawan' AND COALESCE(daily_rate, 0) >= 30000"""
        )
        _sync_karyawan_payroll_fields(conn)

        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN pending_hr_verification INTEGER DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
        conn.execute(
            "UPDATE users SET pending_hr_verification = 0 WHERE pending_hr_verification IS NULL"
        )

        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN is_superadmin INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS superadmin (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('ppn_persen', '12')"
        )

        admin = conn.execute("SELECT id, password FROM users WHERE nik = 'ADMIN001' OR nip = 'ADMIN001'").fetchone()
        if not admin:
            conn.execute(
                "INSERT INTO users (nik, nama, nip, role, password, gaji_pokok) VALUES (?, ?, ?, ?, ?, ?)",
                ('ADMIN001', 'Admin HRD', 'ADMIN001', 'admin', _hash('admin123'), 0)
            )
        elif not admin['password']:
            conn.execute("UPDATE users SET password = ? WHERE id = ?", (_hash('admin123'), admin['id']))

        # Akun demo Super Admin — password diset ke super123 setiap init agar sama dengan teks di login.html.
        super_nip = "NIP2604-001"
        sa = conn.execute(
            "SELECT id FROM users WHERE nip = ? OR nik = ?", (super_nip, super_nip)
        ).fetchone()
        if not sa:
            conn.execute(
                """INSERT INTO users (nik, nama, nip, role, password, gaji_pokok)
                   VALUES (?, ?, ?, 'admin', ?, 0)""",
                (super_nip, "Super Admin", super_nip, _hash("super123")),
            )
        else:
            conn.execute(
                "UPDATE users SET role = 'admin', password = ? WHERE id = ?",
                (_hash("super123"), sa["id"]),
            )

        sa_row = conn.execute(
            "SELECT id FROM users WHERE nip = ? OR nik = ?", (super_nip, super_nip)
        ).fetchone()
        if sa_row:
            conn.execute(
                "INSERT OR IGNORE INTO superadmin (user_id) VALUES (?)",
                (sa_row["id"],),
            )
        conn.execute(
            "INSERT OR IGNORE INTO superadmin (user_id) SELECT id FROM users WHERE COALESCE(is_superadmin, 0) = 1"
        )

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


# Sama seperti login / absensi agar perilaku konsisten
FACE_COMPARE_TOLERANCE = 0.5


def _find_user_by_face(conn, face_vector):
    """Jika wajah cocok dengan pengguna yang sudah punya encoding, kembalikan baris user; jika tidak, None."""
    rows = conn.execute(
        "SELECT id, nip, nik, nama, role, face_encoding FROM users WHERE face_encoding IS NOT NULL"
    ).fetchall()
    for r in rows:
        try:
            db_enc = np.array(json.loads(r['face_encoding']))
            if face_recognition.compare_faces(
                [db_enc], face_vector, tolerance=FACE_COMPARE_TOLERANCE
            )[0]:
                return r
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def _calc_overtime(jam_keluar):
    if not jam_keluar:
        return 0
    pk = jam_keluar.split(':')
    pn = JAM_KELUAR_NORMAL.split(':')
    diff = (int(pk[0]) * 60 + int(pk[1])) - (int(pn[0]) * 60 + int(pn[1]))
    return max(0, diff // 60)


def _upload_photo(data_url, folder="AttendancePhoto"):
    """Upload a base64 image to Cloudinary and return the secure URL."""
    if not data_url or not data_url.startswith('data:'):
        return None
    try:
        result = cloudinary.uploader.upload(
            data_url, folder=folder, resource_type="image",
            transformation={"width": 480, "height": 480, "crop": "limit", "quality": "auto"}
        )
        return result.get('secure_url')
    except Exception as e:
        print(f"[Cloudinary] Foto upload gagal: {e}")
        return None


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
                """SELECT id, nip, nik, nama, role, face_encoding, pending_hr_verification
                   FROM users WHERE face_encoding IS NOT NULL"""
            ).fetchall()
            for u in users:
                db_enc = np.array(json.loads(u['face_encoding']))
                if face_recognition.compare_faces([db_enc], face, tolerance=0.5)[0]:
                    pend = u['pending_hr_verification'] if 'pending_hr_verification' in u.keys() else 0
                    if u['role'] == 'karyawan' and pend:
                        return jsonify({
                            "status": "failed",
                            "message": "Akun belum diverifikasi HR. Tunggu persetujuan HRD atau hubungi bagian personalia."
                        })
                    return jsonify({"status": "success", "user": _login_user_payload(conn, u)})
            return jsonify({"status": "failed", "message": "Wajah tidak terdaftar dalam sistem"})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/login/manual', methods=['POST'])
def login_manual():
    data = request.json
    ident = (data.get('nip') or data.get('nik') or '').strip()
    pw = data.get('password', '')
    conn = get_db()
    try:
        user = conn.execute(
            """SELECT id, nip, nik, nama, role, password, pending_hr_verification
               FROM users WHERE nip = ? OR nik = ?""",
            (ident, ident)
        ).fetchone()
        if not user:
            return jsonify({"status": "failed", "message": "NIP tidak ditemukan"})
        if user['password'] != _hash(pw):
            return jsonify({"status": "failed", "message": "Password salah"})
        pend = user['pending_hr_verification'] if 'pending_hr_verification' in user.keys() else 0
        if user['role'] == 'karyawan' and pend:
            return jsonify({
                "status": "failed",
                "message": "Akun belum diverifikasi HR. Tunggu persetujuan HRD."
            })
        return jsonify({"status": "success", "user": _login_user_payload(conn, user)})
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

        if lat is None or lng is None:
            return jsonify({
                "status": "error",
                "message": "Lokasi wajib untuk absensi. Aktifkan izin lokasi di pengaturan browser lalu coba lagi.",
            }), 200

        conn = get_db()
        try:
            if user_id_hint:
                users = conn.execute(
                    """SELECT id, nama, face_encoding, pending_hr_verification, role
                       FROM users WHERE id = ? AND face_encoding IS NOT NULL""",
                    (user_id_hint,)
                ).fetchall()
            else:
                users = conn.execute(
                    """SELECT id, nama, face_encoding, pending_hr_verification, role
                       FROM users WHERE face_encoding IS NOT NULL"""
                ).fetchall()

            found = None
            for u in users:
                db_enc = np.array(json.loads(u['face_encoding']))
                if face_recognition.compare_faces([db_enc], face, tolerance=0.5)[0]:
                    found = u
                    break

            if not found:
                return jsonify({"status": "failed", "message": "Wajah tidak cocok"}), 200

            pend = found['pending_hr_verification'] if 'pending_hr_verification' in found.keys() else 0
            if found['role'] == 'karyawan' and pend:
                return jsonify({
                    "status": "error",
                    "message": "Akun belum diverifikasi HR. Absensi tidak dapat dilakukan sampai HR menyetujui identitas Anda."
                }), 200

            now = datetime.now()
            tgl = now.strftime("%Y-%m-%d")
            jam = now.strftime("%H:%M:%S")

            log = conn.execute(
                "SELECT id, jam_keluar FROM attendance_logs WHERE user_id = ? AND tanggal = ?",
                (found['id'], tgl)
            ).fetchone()

            if absensi_type == 'Masuk':
                if log:
                    return jsonify({"status": "error", "message": "Sudah absen masuk hari ini"}), 200
                foto_url = _upload_photo(image_data)
                conn.execute(
                    "INSERT INTO attendance_logs (user_id, tanggal, jam_masuk, latitude, longitude, foto_masuk) VALUES (?, ?, ?, ?, ?, ?)",
                    (found['id'], tgl, jam, lat, lng, foto_url)
                )
            else:
                if not log:
                    return jsonify({"status": "error", "message": "Belum absen masuk hari ini"}), 200
                if log['jam_keluar']:
                    return jsonify({"status": "error", "message": "Sudah absen pulang hari ini"}), 200
                foto_url = _upload_photo(image_data)
                ot = _calc_overtime(jam)
                conn.execute(
                    "UPDATE attendance_logs SET jam_keluar = ?, overtime_hours = ?, latitude = COALESCE(latitude, ?), longitude = COALESCE(longitude, ?), foto_keluar = ? WHERE id = ?",
                    (jam, ot, lat, lng, foto_url, log['id'])
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

@app.route('/api/v1/nip/preview', methods=['GET'])
def preview_nip():
    conn = get_db()
    try:
        return jsonify({"nip": _next_nip(conn)})
    finally:
        conn.close()


@app.route('/api/v1/face/register', methods=['POST'])
def enroll_user():
    data = request.json
    try:
        face = _decode_face(data['image'])
        if face is None:
            return jsonify({"status": "error", "message": "Wajah tidak terdeteksi pada gambar"}), 200

        nama = (data.get('nama') or '').strip()
        if not nama:
            return jsonify({"status": "error", "message": "Nama wajib diisi"}), 200

        actor_id = data.get('actor_user_id')
        actor_name = (data.get('actor_name') or '').strip() or None

        conn = get_db()
        try:
            dup = _find_user_by_face(conn, face)
            if dup:
                nip_d = dup['nip'] or dup['nik']
                return jsonify({
                    "status": "error",
                    "message": (
                        f"Wajah ini sudah terdaftar ({nip_d} — {dup['nama']}). "
                        "Tidak dapat mendaftarkan wajah yang sama dua kali."
                    ),
                }), 200

            nip_new = _next_nip(conn)
            tp = _normalize_tunjangan_tipe(data.get('tunjangan_tipe'))
            gp = float(data.get('gaji_pokok', 0))
            daily_amt = _tunjangan_per_hari(tp)
            ot_rate = _tarif_lembur_per_jam(gp)
            cur = conn.execute(
                """INSERT INTO users (nik, nip, nama, gaji_pokok, daily_rate, overtime_rate, tunjangan_tipe, face_encoding, pending_hr_verification, role)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'karyawan')""",
                (nip_new, nip_new, nama, gp, daily_amt, ot_rate, tp,
                 json.dumps(face.tolist()))
            )
            new_id = cur.lastrowid
            _log_change(
                conn, 'users', new_id, 'create', actor_id, actor_name,
                f'Pendaftaran karyawan baru: NIP {nip_new}, nama {nama}'
            )
            conn.commit()
            return jsonify({"status": "success", "message": "Karyawan berhasil didaftarkan!", "nip": nip_new})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/employee/self-register', methods=['POST'])
def self_register_employee():
    """Pendaftaran mandiri (nama + wajah); menunggu verifikasi HR."""
    data = request.json
    try:
        face = _decode_face(data.get('image', ''))
        if face is None:
            return jsonify({"status": "error", "message": "Wajah tidak terdeteksi pada gambar"}), 200

        nama = (data.get('nama') or '').strip()
        if not nama:
            return jsonify({"status": "error", "message": "Nama wajib diisi"}), 200

        conn = get_db()
        try:
            dup = _find_user_by_face(conn, face)
            if dup:
                nip_d = dup['nip'] or dup['nik']
                return jsonify({
                    "status": "error",
                    "message": (
                        f"Wajah ini sudah terdaftar ({nip_d} — {dup['nama']}). "
                        "Anda tidak dapat mendaftar ulang dengan wajah yang sama."
                    ),
                }), 200

            nip_new = _next_nip(conn)
            tp = 'staff'
            gp = 0.0
            daily_amt = _tunjangan_per_hari(tp)
            ot_rate = _tarif_lembur_per_jam(gp)
            cur = conn.execute(
                """INSERT INTO users (nik, nip, nama, gaji_pokok, daily_rate, overtime_rate, tunjangan_tipe, face_encoding, pending_hr_verification, role)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'karyawan')""",
                (nip_new, nip_new, nama, gp, daily_amt, ot_rate, tp,
                 json.dumps(face.tolist()))
            )
            new_id = cur.lastrowid
            _log_change(
                conn, 'users', new_id, 'self_register', None, None,
                f'Pendaftaran mandiri: NIP {nip_new}, nama {nama} — menunggu verifikasi HR'
            )
            conn.commit()
            return jsonify({
                "status": "success",
                "message": "Pendaftaran berhasil. Data masuk ke daftar karyawan; tunggu verifikasi HR untuk login & absensi.",
                "nip": nip_new
            })
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/employee/hr-verify/<int:user_id>', methods=['POST'])
def hr_verify_employee(user_id):
    """HR menyetujui identitas pegawai yang mendaftar mandiri."""
    data = request.json or {}
    actor_id = data.get('actor_user_id')
    actor_name = (data.get('actor_name') or '').strip() or None
    conn = get_db()
    try:
        if not actor_id:
            return jsonify({"status": "error", "message": "Akses ditolak."}), 403

        actor = conn.execute(
            "SELECT id, role, nama FROM users WHERE id = ?", (actor_id,)
        ).fetchone()
        if not actor or actor['role'] != 'admin':
            return jsonify({"status": "error", "message": "Hanya Admin HR yang dapat memverifikasi."}), 403

        row = conn.execute(
            """SELECT nama, nip, nik, pending_hr_verification FROM users
               WHERE id = ? AND role = 'karyawan'""",
            (user_id,)
        ).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Karyawan tidak ditemukan."}), 404

        pend = row['pending_hr_verification'] if 'pending_hr_verification' in row.keys() else 0
        if not pend:
            return jsonify({"status": "success", "message": "Karyawan ini sudah terverifikasi sebelumnya."})

        conn.execute(
            "UPDATE users SET pending_hr_verification = 0 WHERE id = ?",
            (user_id,)
        )
        nip_v = row['nip'] or row['nik']
        _log_change(
            conn, 'users', user_id, 'hr_verify', actor_id, actor_name,
            f"HR memverifikasi identitas: NIP {nip_v}, nama {row['nama']}"
        )
        conn.commit()
        return jsonify({"status": "success", "message": "Identitas karyawan telah diverifikasi."})
    finally:
        conn.close()


@app.route('/api/v1/employees', methods=['GET'])
def list_employees():
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, COALESCE(NULLIF(TRIM(nip), ''), nik) AS nip, nama,
                      gaji_pokok, tunjangan_tipe, daily_rate, overtime_rate,
                      pending_hr_verification, created_at
               FROM users WHERE role = 'karyawan' ORDER BY id DESC"""
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['tunjangan_per_hari'] = _tunjangan_per_hari(d.get('tunjangan_tipe'))
            d['tarif_lembur_per_jam'] = _tarif_lembur_per_jam(d.get('gaji_pokok'))
            out.append(d)
        return jsonify({"total": len(out), "employees": out})
    finally:
        conn.close()


@app.route('/api/v1/employee/data/<int:user_id>', methods=['GET'])
def get_employee_data(user_id):
    conn = get_db()
    try:
        user = conn.execute(
            """SELECT id, nama, COALESCE(NULLIF(TRIM(nip), ''), nik) AS nip,
                      gaji_pokok, tunjangan_tipe, daily_rate, overtime_rate FROM users WHERE id = ?""",
            (user_id,)
        ).fetchone()
        logs = conn.execute(
            "SELECT tanggal, jam_masuk, jam_keluar, overtime_hours, latitude, longitude, foto_masuk, foto_keluar, status FROM attendance_logs WHERE user_id = ? ORDER BY tanggal DESC",
            (user_id,)
        ).fetchall()
        uj = None
        if user:
            uj = dict(user)
            uj['tunjangan_per_hari'] = _tunjangan_per_hari(uj.get('tunjangan_tipe'))
            uj['tarif_lembur_per_jam'] = _tarif_lembur_per_jam(uj.get('gaji_pokok'))
        return jsonify({
            "user": uj,
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
            old = conn.execute(
                "SELECT nama, gaji_pokok, tunjangan_tipe, nip, nik FROM users WHERE id=? AND role='karyawan'",
                (user_id,)
            ).fetchone()
            if not old:
                return jsonify({"status": "error", "message": "Karyawan tidak ditemukan."}), 404

            nama = (data.get('nama') or '').strip()
            if not nama:
                return jsonify({"status": "error", "message": "Nama wajib diisi."}), 400

            gaji = float(data.get('gaji_pokok', 0))
            tp = _normalize_tunjangan_tipe(data.get('tunjangan_tipe'))
            daily_amt = _tunjangan_per_hari(tp)
            ot = _tarif_lembur_per_jam(gaji)

            conn.execute(
                """UPDATE users SET nama=?, gaji_pokok=?, tunjangan_tipe=?, daily_rate=?, overtime_rate=?
                   WHERE id=? AND role='karyawan'""",
                (nama, gaji, tp, daily_amt, ot, user_id)
            )

            actor_id = data.get('actor_user_id')
            actor_name = (data.get('actor_name') or '').strip() or None
            parts = []
            if old['nama'] != nama:
                parts.append(f"nama: {old['nama']} → {nama}")
            if (old['gaji_pokok'] or 0) != gaji:
                parts.append(f"gaji_pokok: {old['gaji_pokok']} → {gaji}")
            old_tp = old['tunjangan_tipe'] if 'tunjangan_tipe' in old.keys() else None
            otp = _normalize_tunjangan_tipe(old_tp)
            if otp != tp:
                parts.append(f"tunjangan_tipe: {otp} → {tp}")
            detail = '; '.join(parts) if parts else 'Perubahan data (tanpa diff)'
            _log_change(conn, 'users', user_id, 'update', actor_id, actor_name, detail)

            conn.commit()
            return jsonify({"status": "success", "message": "Data karyawan berhasil diperbarui."})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/employee/delete/<int:user_id>', methods=['DELETE'])
def delete_employee(user_id):
    try:
        data = request.json or {}
        actor_id = data.get('actor_user_id')
        actor_name = (data.get('actor_name') or '').strip() or None
        conn = get_db()
        try:
            if not actor_id:
                return jsonify({"status": "error", "message": "Akses ditolak."}), 403
            actor = conn.execute(
                "SELECT id, role FROM users WHERE id = ?", (actor_id,)
            ).fetchone()
            if not actor or actor["role"] != "admin":
                return jsonify({"status": "error", "message": "Akses ditolak."}), 403
            if not _user_is_superadmin(conn, actor_id):
                return jsonify({
                    "status": "error",
                    "message": "Hanya Super Admin yang dapat menghapus data karyawan.",
                }), 403

            row = conn.execute(
                "SELECT nama, COALESCE(nip, nik) AS nip FROM users WHERE id = ? AND role = 'karyawan'",
                (user_id,)
            ).fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Karyawan tidak ditemukan."}), 404
            _log_change(
                conn, 'users', user_id, 'delete', actor_id, actor_name,
                f"Hapus karyawan: NIP {row['nip']}, nama {row['nama']}"
            )
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
                   a.latitude, a.longitude, a.foto_masuk, a.foto_keluar,
                   a.status, u.nama, COALESCE(u.nip, u.nik) AS nip
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
        uid = data.get('user_id')
        actor_name = (data.get('actor_name') or '').strip()
        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO leaves (user_id, jenis_cuti, tanggal, alasan, attachment) VALUES (?, ?, ?, ?, ?)",
                (uid, data.get('jenis'), data.get('tanggal'),
                 data.get('alasan'), attachment_url)
            )
            lid = cur.lastrowid
            _log_change(
                conn, 'leaves', lid, 'create', uid,
                actor_name or None,
                f"Pengajuan cuti: {data.get('jenis')} tanggal {data.get('tanggal')}"
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
        lid = data.get('leave_id')
        actor_id = data.get('actor_user_id')
        actor_name = (data.get('actor_name') or '').strip() or None
        conn = get_db()
        try:
            row = conn.execute("SELECT status FROM leaves WHERE id=?", (lid,)).fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Data tidak ditemukan."}), 404
            cur = conn.execute("UPDATE leaves SET status='Cancelled' WHERE id=? AND status='Pending'", (lid,))
            if cur.rowcount:
                _log_change(conn, 'leaves', lid, 'cancel', actor_id, actor_name, "Pembatalan pengajuan oleh karyawan")
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
        lid = data.get('leave_id')
        action = data.get('action', 'Approved')
        actor_id = data.get('actor_user_id')
        actor_name = (data.get('actor_name') or '').strip() or None
        conn = get_db()
        try:
            old = conn.execute("SELECT status, jenis_cuti, tanggal FROM leaves WHERE id=?", (lid,)).fetchone()
            cur = conn.execute(
                "UPDATE leaves SET status=? WHERE id=? AND status='Pending'",
                (action, lid)
            )
            if cur.rowcount and old:
                _log_change(
                    conn, 'leaves', lid, 'approve' if action == 'Approved' else 'reject',
                    actor_id, actor_name,
                    f"Status: {old['status']} → {action}; {old['jenis_cuti']} {old['tanggal']}"
                )
            conn.commit()
            return jsonify({"status": "success", "message": f"Cuti {action}."})
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

@app.route('/api/v1/history', methods=['GET'])
def get_change_history():
    entity = (request.args.get('entity') or '').strip()
    record_id = request.args.get('record_id', type=int)
    if entity not in ('users', 'leaves') or not record_id:
        return jsonify({"status": "error", "message": "Parameter entity dan record_id wajib."}), 400
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, action, changed_by_name, detail, created_at
               FROM change_history WHERE entity = ? AND record_id = ?
               ORDER BY id DESC""",
            (entity, record_id)
        ).fetchall()
        return jsonify({"history": [dict(r) for r in rows]})
    finally:
        conn.close()


@app.route('/api/v1/payroll/<int:user_id>', methods=['GET'])
def get_payroll(user_id):
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    conn = get_db()
    try:
        user = conn.execute(
            """SELECT id, nama, COALESCE(NULLIF(TRIM(nip), ''), nik) AS nip,
                      gaji_pokok, tunjangan_tipe, daily_rate, overtime_rate FROM users WHERE id=?""",
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
        tp = _normalize_tunjangan_tipe(user['tunjangan_tipe'])
        tnj_per_hari = _tunjangan_per_hari(tp)
        ot_rate = _tarif_lembur_per_jam(gp)
        tunjangan_total = total_days * tnj_per_hari
        ot_pay = total_ot * ot_rate

        bruto_bulan = gp + tunjangan_total + ot_pay
        ppn_persen = _get_ppn_persen(conn)
        potongan_ppn = bruto_bulan * (ppn_persen / 100.0)
        gaji_bersih = bruto_bulan - potongan_ppn

        ud = dict(user)
        ud['tunjangan_tipe'] = tp
        ud['tunjangan_per_hari'] = tnj_per_hari
        ud['tarif_lembur_per_jam'] = ot_rate
        ud['overtime_rate'] = ot_rate

        return jsonify({
            "user": ud,
            "month": month,
            "total_days": total_days,
            "total_overtime_hours": total_ot,
            "gaji_pokok": gp,
            "tunjangan_per_hari": tnj_per_hari,
            "tunjangan_total": tunjangan_total,
            "daily_total": tunjangan_total,
            "overtime_rate_efektif": ot_rate,
            "overtime_total": ot_pay,
            "bruto_bulan": bruto_bulan,
            "ppn_persen": ppn_persen,
            "potongan_ppn": potongan_ppn,
            "grand_total": bruto_bulan,
            "gaji_bersih_setelah_pajak": gaji_bersih,
            "lembur_formula": f"(gaji pokok ÷ {JAM_KERJA_BULAN_PEMBAGI}) × 1,5",
            "ppn_formula": f"{ppn_persen:g}% × penghasilan bruto bulan",
            "logs": [dict(r) for r in logs]
        })
    finally:
        conn.close()


@app.route('/api/v1/settings', methods=['GET'])
def get_settings():
    conn = get_db()
    try:
        return jsonify({"ppn_persen": _get_ppn_persen(conn)})
    finally:
        conn.close()


@app.route('/api/v1/settings', methods=['PUT'])
def put_settings():
    data = request.json or {}
    actor_id = data.get('actor_user_id')
    conn = get_db()
    try:
        if not actor_id:
            return jsonify({"status": "error", "message": "Akses ditolak."}), 403
        actor = conn.execute("SELECT role FROM users WHERE id = ?", (actor_id,)).fetchone()
        if not actor or actor['role'] != 'admin':
            return jsonify({"status": "error", "message": "Hanya admin yang dapat mengubah pengaturan."}), 403
        raw = data.get('ppn_persen')
        if raw is None:
            return jsonify({"status": "error", "message": "Nilai PPN wajib diisi."}), 400
        try:
            p = float(raw)
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Nilai PPN tidak valid."}), 400
        p = max(0.0, min(100.0, p))
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES ('ppn_persen', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(p),),
        )
        conn.commit()
        return jsonify({"status": "success", "message": "Pengaturan PPN disimpan.", "ppn_persen": p})
    finally:
        conn.close()


def _require_superadmin_actor(actor_id):
    """Kembalikan (True, None) atau (False, (response, status_code))."""
    if actor_id is None or actor_id == '':
        return False, (jsonify({"status": "error", "message": "Akses ditolak."}), 403)
    try:
        aid = int(actor_id)
    except (TypeError, ValueError):
        return False, (jsonify({"status": "error", "message": "Akses ditolak."}), 403)
    conn = get_db()
    try:
        if not _user_is_superadmin(conn, aid):
            return False, (jsonify({"status": "error", "message": "Hanya Super Admin yang dapat mengakses backup database."}), 403)
        return True, None
    finally:
        conn.close()


@app.route('/api/v1/backup/status', methods=['GET'])
def backup_status():
    actor_id = request.args.get('actor_user_id', type=int)
    ok, err = _require_superadmin_actor(actor_id)
    if not ok:
        return err
    return jsonify({
        "status": "success",
        "interval_seconds": BACKUP_INTERVAL_SEC,
        "backup_folder": "backup",
        "last_scheduled_at": _last_scheduled_backup_at,
        "last_scheduled_file": _last_scheduled_backup_name,
        "last_manual_at": _last_manual_backup_at,
        "last_manual_file": _last_manual_backup_name,
        "files": _list_backup_files(),
    })


@app.route('/api/v1/backup/run', methods=['POST'])
def backup_run_manual():
    data = request.json or {}
    actor_id = data.get('actor_user_id')
    ok, err = _require_superadmin_actor(actor_id)
    if not ok:
        return err
    try:
        r = _perform_database_backup('manual')
        return jsonify({
            "status": "success",
            "message": f"Backup disimpan: {r['filename']}",
            "filename": r["filename"],
            "at": r["at"],
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


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
    start_scheduled_database_backups()
    print(f'Backup database otomatis setiap {BACKUP_INTERVAL_SEC}s → folder backup/')
    app.run(debug=True, host=host, port=port, ssl_context=ssl_ctx)
