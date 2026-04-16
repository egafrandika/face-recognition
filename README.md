# PayrollFace - Sistem Absensi & Payroll Berbasis Face Recognition

Sistem informasi absensi dan payroll yang mengintegrasikan verifikasi biometrik wajah untuk memastikan kehadiran karyawan yang akurat dan aman.

## Fitur Utama

- **Face Recognition Login**: Login dan absensi menggunakan verifikasi wajah real-time.
- **NIP (Nomor Induk Pegawai)**: Nomor pegawai otomatis dengan format `NIP{YY}{MM}-{urutan}` (contoh: `NIP2604-001`); tidak diisi manual oleh HRD.
- **Registrasi Mandiri (`registrasi.html`)**: Pegawai dapat mendaftar sendiri dengan **nama + sampel wajah** (tanpa login). Data masuk ke daftar karyawan HR dengan status **menunggu verifikasi**; **login dan absensi diblokir** sampai HR menyetujui identitas lewat tombol **Verifikasi** di panel admin.
- **Verifikasi HR**: Kolom **Status HR** di daftar karyawan (Menunggu / Terverifikasi); HR melengkapi gaji, tunjangan, dll. setelah atau sebelum verifikasi sesuai kebijakan.
- **Anti-duplikat wajah**: Pendaftaran HR maupun registrasi mandiri **ditolak** jika wajah sudah cocok dengan pengguna yang terdaftar (perbandingan encoding, toleransi sama seperti login).
- **Manajemen Absensi**: Pencatatan jam masuk/pulang dengan perhitungan lembur otomatis (setelah jam kerja normal).
- **Foto Absensi**: Foto wajah karyawan saat masuk & keluar otomatis tersimpan di Cloudinary dan ditampilkan di rekap kehadiran (satu kali per hari, tidak bisa diulang).
- **Geolokasi**: Titik lokasi GPS saat absensi, ditampilkan sebagai link Google Maps di tabel HR.
- **Cloudinary Storage**: Lampiran surat dokter (cuti sakit) dan foto absensi disimpan di cloud via Cloudinary.
- **Tunjangan Kehadiran**: Menggantikan “gaji harian” — dua tipe: **Staff Rp25.000** dan **Supervisor Rp35.000** per hari hadir (dipilih saat pendaftaran/edit karyawan).
- **Tarif Lembur Otomatis**: Dihitung dari gaji pokok, **tidak dapat diubah manual**: `(gaji pokok ÷ 173) × 1,5` per jam (173 = jam kerja efektif per bulan).
- **Sistem Payroll**: Gaji pokok + tunjangan (sesuai tipe × hari hadir) + uang lembur; estimasi **PPh21** progresif (disetahunkan dari bruto bulan) dan tampilan gaji bersih.
- **Slip Gaji**: Cetak atau download slip gaji bulanan (PDF via print / gambar PNG).
- **Riwayat Perubahan (Audit)**: Tabel `change_history` — siapa yang mengubah data dan kapan; di panel HR tombol **Riwayat** pada **Daftar Karyawan** dan **Persetujuan Cuti** membuka modal riwayat.
- **Izin Kamera**: Jika kamera ditolak, pengguna mendapat pesan agar mengaktifkan izin kamera di pengaturan browser.
- **Pengajuan Cuti**: Formulir digital lengkap dengan upload surat dokter untuk cuti sakit.
- **Panel Admin HRD**: Enrollment karyawan, rekap kehadiran, persetujuan cuti, slip gaji, dan absensi HR.
- **Loading Indicator**: Spinner animasi pada semua tabel dan tombol aksi saat fetching data.
- **Responsive**: Tampilan menyesuaikan desktop, tablet, dan mobile.

## Teknologi

- **Frontend**: HTML5, CSS3, JavaScript (Vanilla), Font Awesome
- **Backend**: Python 3.x, Flask
- **Computer Vision**: OpenCV, face_recognition, dlib
- **Database**: SQLite (otomatis dibuat saat pertama jalan)
- **Cloud Storage**: Cloudinary (foto absensi & lampiran cuti)
- **Deployment**: ngrok (untuk akses publik / dari HP)

## Struktur File

```
project_skripsi/
├── app.py                  # Backend Flask (API server)
├── camera.js               # Modul kamera (init, capture, izin kamera)
├── style.css               # Stylesheet global + responsive
├── index.html              # Halaman landing page
├── login.html              # Login (face recognition + manual admin)
├── registrasi.html         # Pendaftaran mandiri pegawai (nama + wajah, tanpa login)
├── admin.html              # Panel HR (kelola karyawan, rekap, cuti, slip gaji, absensi HR)
├── dashboard.html          # Dashboard karyawan (absensi, riwayat, cuti, slip gaji)
├── slip_gaji.html          # Halaman cetak/download slip gaji
├── rekap_kehadiran.html    # (opsional) Riwayat kehadiran — navigasi lama
├── pengajuan_cuti.html     # (opsional) Form cuti — navigasi lama
├── requirements.txt        # Dependensi Python
├── payrollface.db          # Database SQLite (auto-generated)
└── README.md
```

## Cara Menjalankan

### 1. Prasyarat

- **Python 3.10+** sudah terinstal
- **pip** (Python package manager)
- Koneksi internet (untuk instalasi library pertama kali)

### 2. Instalasi Dependensi

Buka terminal / PowerShell di folder proyek:

```bash
pip install flask flask-cors opencv-python-headless numpy Pillow
pip install dlib-bin
pip install face_recognition --no-deps
pip install face-recognition-models
pip install "setuptools<81"
pip install cloudinary
```

### 3. Konfigurasi Cloudinary

Aplikasi ini menggunakan **Cloudinary** untuk menyimpan foto absensi dan lampiran surat cuti di cloud.

#### 3a. Buat Akun Cloudinary

1. Buka **https://cloudinary.com/** dan buat akun gratis
2. Setelah login, buka **Dashboard** — catat 3 nilai berikut:
   - **Cloud Name** (contoh: `dfypljeaj`)
   - **API Key** (contoh: `198827775726965`)
   - **API Secret** (contoh: `eRroGuOLjdHBme3jLyYO2tAn2wA`)

#### 3b. Konfigurasi di `app.py`

Buka file `app.py`, cari bagian konfigurasi Cloudinary di baris atas:

```python
cloudinary.config(
    cloud_name="dfyplxxx",
    api_key="19882777xxxxxx",
    api_secret="eRroGuOLjdHBme3xxxxxxx",
    secure=True
)
```

Ganti nilai `cloud_name`, `api_key`, dan `api_secret` dengan milik Anda.

#### 3c. Folder Otomatis di Cloudinary

Aplikasi akan membuat folder secara otomatis di Cloudinary:

| Folder | Isi |
|--------|-----|
| `AttendancePhoto/` | Foto wajah saat absen masuk & pulang |
| `LeaveImg/` | Lampiran surat dokter (cuti sakit) |

Anda bisa melihat file yang ter-upload di **Media Library** pada dashboard Cloudinary.

### 4. Jalankan Server

```bash
python app.py
```

Server berjalan di **http://127.0.0.1:5000**. Database `payrollface.db` dibuat otomatis dengan akun admin default:

| Field    | Value      |
|----------|------------|
| NIP      | `ADMIN001` |
| Password | `admin123` |

### 5. Buka di Browser

Buka **http://127.0.0.1:5000/** di Chrome / Edge / Firefox.

---

## Deploy dengan ngrok (Akses dari Internet / HP)

ngrok membuat URL publik HTTPS yang mengarah ke server lokal Anda. Ini diperlukan agar kamera bisa diakses dari HP (browser memblokir kamera pada HTTP non-localhost).

### Step 1: Download & Install ngrok

1. Buka **https://ngrok.com/**
2. **Sign Up** / buat akun gratis
3. Download ngrok sesuai OS (Windows / macOS / Linux)
4. Ekstrak file yang didownload
5. Pindahkan `ngrok.exe` ke folder yang mudah diakses (misalnya `C:\ngrok\` atau tambahkan ke PATH)

### Step 2: Tambahkan Auth Token

Setelah login di dashboard ngrok (https://dashboard.ngrok.com/), salin **Authtoken** Anda, lalu jalankan:

```bash
ngrok config add-authtoken YOUR_AUTH_TOKEN_HERE
```

Ganti `YOUR_AUTH_TOKEN_HERE` dengan token dari dashboard. Ini hanya perlu dilakukan **satu kali**.

### Step 3: Jalankan Server + ngrok

**Terminal 1** — jalankan Flask server:

```bash
python app.py
```

**Terminal 2** — jalankan ngrok (buka terminal/PowerShell baru):

```bash
ngrok http 5000
```

ngrok akan menampilkan URL publik seperti:

```
Forwarding    https://xxxxx-xxxxx-xxxxx.ngrok-free.dev -> http://localhost:5000
```

### Step 4: Akses dari Mana Saja

Buka URL `https://xxxxx-xxxxx-xxxxx.ngrok-free.dev` di browser HP atau komputer lain. Semua fitur termasuk kamera akan berfungsi karena HTTPS.

### Catatan Penting ngrok

| Hal | Keterangan |
|-----|------------|
| **URL berubah** | Setiap kali ngrok dimatikan dan dijalankan ulang, URL publik berubah (plan gratis). |
| **Matikan komputer** | Jika komputer mati, Flask dan ngrok ikut mati. Jalankan ulang keduanya saat menyalakan komputer. |
| **Urutan** | Selalu jalankan `python app.py` **duluan**, baru `ngrok http 5000`. |
| **Visitor Warning** | Saat pertama buka URL ngrok, mungkin muncul halaman peringatan ngrok — klik **Visit Site**. |

### Ringkasan Command

```bash
# Instalasi (sekali saja)
pip install flask flask-cors opencv-python-headless numpy Pillow
pip install dlib-bin
pip install face_recognition --no-deps
pip install face-recognition-models
pip install "setuptools<81"
pip install cloudinary
ngrok config add-authtoken YOUR_TOKEN

# Setiap kali mau jalankan (2 terminal)
# Terminal 1:
python app.py

# Terminal 2:
ngrok http 5000
```

---

## Panduan Penggunaan

### Beranda & akses publik

- Dari **landing page** (`index.html`) atau **login** ada tautan ke **Registrasi Pegawai** (`registrasi.html`).

### Registrasi mandiri (pegawai)

1. Buka **Registrasi Pegawai**, isi **nama lengkap**, izinkan **kamera**, lalu **Kirim Pendaftaran**.
2. Jika wajah **sudah terdaftar** pada akun lain, sistem menolak dan menampilkan pesan (beserta NIP pemilik wajah yang ada).
3. Setelah berhasil, catat **NIP** yang ditampilkan; **login dan absensi belum aktif** sampai HR memverifikasi.
4. HR memeriksa di **Kelola Karyawan** → kolom **Status HR** → tombol **Verifikasi** (ikon centang) jika status masih menunggu.

### Login

- **Face Recognition**: Arahkan wajah ke kamera, sistem mencocokkan otomatis. **Izin kamera wajib** — jika ditolak, ikuti petunjuk di browser. Akun **belum diverifikasi HR** tidak dapat login (pesan khusus).
- **Manual (Admin)**: Toggle ke form manual, masukkan **NIP** `ADMIN001` dan password `admin123`. Karyawan dengan status menunggu verifikasi tidak dapat login manual.

### Admin HRD

1. **Kelola Karyawan** — Daftarkan karyawan baru dengan foto wajah; atur **gaji pokok** dan **tipe tunjangan** (Staff / Supervisor). **NIP** dibuat otomatis; **tarif lembur** dihitung otomatis dari gaji pokok (field readonly). Wajah yang sama dengan pegawai lain **tidak dapat didaftarkan**. Untuk pegawai dari **registrasi mandiri**, gunakan **Verifikasi** agar bisa login/absensi; gunakan **Riwayat** untuk audit. Edit atau hapus data.
2. **Rekap Kehadiran** — Lihat absensi seluruh karyawan per bulan, lengkap dengan foto masuk/keluar, jam masuk/keluar, lembur, dan lokasi GPS.
3. **Persetujuan Cuti** — Setujui atau tolak pengajuan cuti. Tombol **Riwayat** menampilkan siapa yang menyetujui/menolak dan kapan (jika tercatat).
4. **Slip Gaji** — Pilih karyawan dan bulan; rincian memuat gaji pokok, tunjangan, lembur, estimasi PPh21, dan gaji bersih.
5. **Absensi HR** — Absen masuk/pulang dengan face recognition. Daftarkan wajah admin jika belum.

### Karyawan

1. **Absensi** — Pilih Masuk/Pulang, verifikasi wajah via kamera (izin kamera harus aktif). Akun yang **belum diverifikasi HR** tidak dapat absensi.
2. **Riwayat Kehadiran** — Tabel harian: foto masuk/keluar, jam, lembur, lokasi, dan keterangan.
3. **Pengajuan Cuti** — Isi formulir, upload surat dokter jika sakit (tersimpan di Cloudinary).
4. **Slip Gaji** — Pilih bulan; tampilan mencakup tunjangan, lembur (sesuai rumus), PPh21 perkiraan, dan gaji bersih.

### Rumus Payroll (ringkas)

| Komponen | Perhitungan |
|----------|-------------|
| Tunjangan | `hari hadir × Rp25.000` (Staff) atau `× Rp35.000` (Supervisor) |
| Lembur/jam | `(gaji pokok ÷ 173) × 1,5` |
| PPh21 (estimasi) | Tarif progresif tahunan dari PKP perkiraan = `12 × penghasilan bruto bulan ini` |

*PPh21 adalah penyederhanaan untuk tampilan slip; kepatuhan penuh mengikuti peraturan perpajakan yang berlaku.*

## API Endpoints

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| POST | `/api/v1/login/face` | Login dengan face recognition |
| POST | `/api/v1/login/manual` | Login manual (**NIP** atau alias lama + password) |
| POST | `/api/v1/verify-liveness` | Absensi masuk/pulang + geolokasi |
| GET | `/api/v1/nip/preview` | Pratinjau NIP berikutnya (otomatis) |
| POST | `/api/v1/face/register` | Enrollment karyawan oleh HR (`nama`, `gaji_pokok`, `tunjangan_tipe`, `image`, …); tolak jika wajah duplikat |
| POST | `/api/v1/employee/self-register` | Registrasi mandiri (`nama`, `image`); `pending_hr_verification=1`; tolak jika wajah duplikat |
| POST | `/api/v1/employee/hr-verify/<id>` | HR memverifikasi identitas (body: `actor_user_id` admin); hanya admin |
| GET | `/api/v1/employees` | Daftar karyawan + tunjangan, tarif lembur, status verifikasi |
| GET | `/api/v1/employee/data/<id>` | Data & riwayat kehadiran karyawan |
| PUT | `/api/v1/employee/update/<id>` | Edit data (`nama`, `gaji_pokok`, `tunjangan_tipe`, …) |
| DELETE | `/api/v1/employee/delete/<id>` | Hapus karyawan (body JSON: actor opsional) |
| GET | `/api/v1/attendance/all` | Rekap kehadiran semua karyawan (HR) |
| GET | `/api/v1/history?entity=users&record_id=<id>` atau `entity=leaves` | Riwayat perubahan untuk karyawan atau cuti |
| POST | `/api/v1/leave/request` | Ajukan cuti |
| POST | `/api/v1/leave/cancel` | Batalkan pengajuan cuti |
| GET | `/api/v1/leave/my/<id>` | Riwayat cuti per karyawan |
| GET | `/api/v1/leave/list` | Daftar semua cuti (HR) |
| POST | `/api/v1/leave/approve` | Setujui/tolak cuti |
| GET | `/api/v1/payroll/<id>` | Hitung slip gaji bulanan (tunjangan, lembur, PPh21, …) |
| POST | `/api/v1/admin/register-face` | Daftarkan wajah admin |

## Database Schema

Tabel utama (SQLite, auto-generated / dimigrasi saat `app.py` dijalankan):

- **users** — `id`, `nik` (legacy), `nip`, `nama`, `role`, `password`, `gaji_pokok`, `tunjangan_tipe` (`staff` / `supervisor`), `daily_rate` (disinkronkan dengan nominal tunjangan per hari), `overtime_rate` (disinkronkan dengan rumus lembur), `pending_hr_verification` (`1` = menunggu verifikasi HR setelah registrasi mandiri; `0` = boleh login/absensi), `face_encoding`, `created_at`
- **attendance_logs** — `id`, `user_id` (FK), `tanggal`, `jam_masuk`, `jam_keluar`, `overtime_hours`, `latitude`, `longitude`, `foto_masuk`, `foto_keluar`, `status`
- **leaves** — `id`, `user_id` (FK), `jenis_cuti`, `tanggal`, `alasan`, `attachment` (URL Cloudinary), `status`
- **change_history** — `id`, `entity` (`users` / `leaves`), `record_id`, `action`, `changed_by_user_id`, `changed_by_name`, `detail`, `created_at`
