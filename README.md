# PayrollFace - Sistem Absensi & Payroll Berbasis Face Recognition

Sistem informasi absensi dan payroll yang mengintegrasikan verifikasi biometrik wajah untuk memastikan kehadiran karyawan yang akurat dan aman.

## Fitur Utama

- **Face Recognition Login**: Verifikasi wajah di server. **Liveness (kedip) di browser**: sebelum foto dikirim, `blink-liveness.js` memuat **face-api.js** (CDN) + model; pengguna melewati **satu kali kedip** (ear landmark). Butuh **internet** saat pertama memuat pustaka/bobot (bisa di-cache).
- **NIP (Nomor Induk Pegawai)**: Nomor pegawai otomatis dengan format `NIP{YY}{MM}-{urutan}` (contoh: `NIP2604-001`); tidak diisi manual oleh HRD.
- **Registrasi Mandiri (`registrasi.html`)**: Pegawai dapat mendaftar sendiri dengan **nama + sampel wajah** (tanpa login). Data masuk ke daftar karyawan HR dengan status **menunggu verifikasi**; **login dan absensi diblokir** sampai HR menyetujui identitas lewat tombol **Verifikasi** di panel admin.
- **Verifikasi HR**: Kolom **Status HR** di daftar karyawan (Menunggu / Terverifikasi); HR melengkapi gaji, tunjangan, dll. setelah atau sebelum verifikasi sesuai kebijakan.
- **Anti-duplikat wajah**: Pendaftaran HR maupun registrasi mandiri **ditolak** jika wajah sudah cocok dengan pengguna yang terdaftar (perbandingan encoding, toleransi sama seperti login).
- **Manajemen Absensi**: Pencatatan jam masuk/pulang dengan perhitungan lembur otomatis (setelah jam kerja normal).
- **Foto Absensi**: Foto wajah karyawan saat masuk & keluar otomatis tersimpan di Cloudinary dan ditampilkan di rekap kehadiran (satu kali per hari, tidak bisa diulang).
- **Geolokasi wajib**: **Izin lokasi** harus diaktifkan untuk absensi (karyawan & HR); jika ditolak, absensi tidak diproses. Koordinat ditampilkan sebagai link Google Maps di rekap.
- **Cloudinary Storage**: Lampiran surat dokter (cuti sakit) dan foto absensi disimpan di cloud via Cloudinary.
- **Tunjangan Kehadiran**: Menggantikan “gaji harian” — dua tipe: **Staff Rp25.000** dan **Supervisor Rp35.000** per hari hadir (dipilih saat pendaftaran/edit karyawan).
- **Tarif Lembur Otomatis**: Dihitung dari gaji pokok, **tidak dapat diubah manual**: `(gaji pokok ÷ 173) × 1,5` per jam (173 = jam kerja efektif per bulan).
- **Sistem Payroll & PPN**: Gaji pokok + tunjangan (sesuai tipe × hari hadir) + uang lembur; potongan **PPN** sederhana = persen × penghasilan bruto bulan (persen diatur admin, default **12%** di atas tabel **Daftar Karyawan**), lalu tampilan gaji bersih.
- **Slip Gaji**: Cetak atau download slip gaji bulanan (PDF via print / gambar PNG).
- **Riwayat Perubahan (Audit)**: Tabel `change_history` — siapa yang mengubah data dan kapan; di panel HR tombol **Riwayat** pada **Daftar Karyawan** dan **Persetujuan Cuti** membuka modal riwayat.
- **Izin Kamera & Lokasi**: Kamera wajib untuk semua alur wajah; **lokasi GPS wajib** hanya untuk **absensi** (dashboard karyawan & panel Absensi HR). Helper di `camera.js`: `getLocationRequired()`, `geoErrorToMessage()`.
- **Pengajuan Cuti**: Formulir digital lengkap dengan upload surat dokter untuk cuti sakit.
- **Panel Admin HRD**: Enrollment karyawan, **Daftar Karyawan** (urut NIP, kolom **Cari** NIP/nama), rekap kehadiran, persetujuan cuti, slip gaji, dan absensi HR.
- **Super Admin**: Hak khusus untuk **menghapus karyawan** di **Kelola Karyawan**, **menghapus baris rekap kehadiran** (tombol sampah di Rekap — hanya Super Admin), menu **Backup Database**, dan **Kelola Akun Admin** (ubah nama/password akun Admin HR & Super Admin; riwayat perubahan password dari `change_history`). Daftar superadmin di tabel **`superadmin`** (`user_id` → `users.id`). File salinan **`payrollface.db`** di folder **`backup/`** (`sqlite3.backup`); backup otomatis tiap **1 jam** (env **`BACKUP_INTERVAL_SEC`**, default `3600`) + backup manual dari panel.
- **Loading Indicator**: Spinner animasi pada semua tabel dan tombol aksi saat fetching data.
- **Responsive**: Tampilan menyesuaikan desktop, tablet, dan mobile.

## Teknologi

- **Frontend**: HTML5, CSS3, JavaScript (Vanilla), Font Awesome
- **Liveness (browser)**: [face-api.js](https://github.com/justadudewhohacks/face-api.js) (TinyFaceDetector + landmark) — pemuatan dari CDN; logika di `blink-liveness.js` (kalibrasi + EAR, kedip sekali).
- **Backend**: Python 3.x, Flask
- **Computer Vision**: OpenCV, face_recognition, dlib
- **Database**: SQLite (otomatis dibuat saat pertama jalan)
- **Cloud Storage**: Cloudinary (foto absensi & lampiran cuti)
- **Deployment**: **ngrok** (HTTPS publik untuk kamera dari HP) — baca bagian *Deploy dengan ngrok*; pengguna cukup mengklik **Visit Site** pada peringatan pembuka bila muncul.

## Struktur File

```
project_skripsi/
├── app.py                  # Backend Flask (API server)
├── camera.js               # Kamera, capture, geolokasi wajib absensi (`getLocationRequired`)
├── blink-liveness.js       # Verifikasi kedip sebelum capture wajah (face-api, CDN)
├── test_api.py             # Skrip uji API (register / absensi; kirim koordinat dummy)
├── style.css               # Stylesheet global + responsive
├── index.html              # Halaman landing page
├── login.html              # Login (face recognition + manual admin)
├── registrasi.html         # Pendaftaran mandiri pegawai (nama + wajah, tanpa login)
├── admin.html              # Panel HR (+ backup, kelola akun admin, hapus rekap — Super Admin)
├── dashboard.html          # Dashboard karyawan (absensi, riwayat, cuti, slip gaji)
├── slip_gaji.html          # Halaman cetak/download slip gaji
├── rekap_kehadiran.html    # (opsional) Riwayat kehadiran — navigasi lama
├── pengajuan_cuti.html     # (opsional) Form cuti — navigasi lama
├── requirements.txt        # Dependensi Python
├── payrollface.db          # Database SQLite (auto-generated)
├── backup/                 # Salinan DB (otomatis + manual; di-.gitignore)
└── README.md
```

## Cara Menjalankan

### 1. Prasyarat

- **Python 3.10+** sudah terinstal
- **pip** (Python package manager)
- Koneksi internet (untuk `pip install` pustaka Python; halaman dengan liveness memuat **face-api.js + model** dari CDN saat **pertama** dipakai)

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

Server berjalan di **http://127.0.0.1:5000**. Database `payrollface.db` dibuat otomatis dengan akun default:

| Peran        | NIP            | Password bootstrap | Keterangan |
|--------------|----------------|--------------------|------------|
| Admin HR     | `ADMIN001`     | Lihat bawah        | Panel HR penuh; **tanpa** hapus karyawan |
| Super Admin  | `SUPERUSER`    | Lihat bawah        | Nama tampilan **SUPER USER**; sama seperti admin HR + **boleh hapus** karyawan |

**Password bootstrap (dinamis):** set variabel lingkungan **`PAYROLLFACE_BOOTSTRAP_HR_PASSWORD`** dan **`PAYROLLFACE_BOOTSTRAP_SUPER_PASSWORD`** sebelum menjalankan server pertama kali. Jika tidak diset, dipakai nilai demo **`admin123`** / **`super123`** (hanya untuk insert pertama atau jika password HR masih kosong). Password **Super Admin yang sudah ada tidak ditimpa** saat `app.py` dijalankan ulang — ubah lewat menu **Kelola Akun Admin** (Super Admin). Admin HR tanpa password akan diisi ulang dari env/bootstrap saat init.

**Login manual:** NIP dibandingkan **tanpa membedakan huruf besar/kecil** (`ADMIN001` = `admin001`).

**Migrasi data (sekali saat `init_db`):** jika ada pengguna **`role = 'admin'`** dengan NIP **`NIP2604-001`**, peran diubah menjadi **`karyawan`** (agar tampil di Daftar Karyawan), baris **`superadmin`** untuk `user_id` tersebut dihapus, lalu field payroll disinkronkan. Flag tersimpan di **`app_settings`** (`nip2604_001_demoted_from_admin`) agar tidak diulang.

**Respons login** (`/api/v1/login/manual` dan `/api/v1/login/face`) menyertakan field boolean **`superadmin`** untuk menyesuaikan UI (tombol hapus, menu backup, kelola akun admin).

### 5. Backup database (opsional dibaca)

| Hal | Keterangan |
|-----|------------|
| **Folder** | `backup/` di root proyek (otomatis dibuat). File: `payrollface_YYYYMMDD_HHMMSS.db`. |
| **Metode** | `sqlite3.backup` — salinan konsisten meski DB memakai WAL. |
| **Otomatis** | Thread berjalan **hanya** saat server dimulai lewat `python app.py` (bukan `flask run` kecuali Anda menambahkan pemanggilan scheduler). Interval default **3600 detik (1 jam)**. Backup **pertama** jalan setelah **satu interval** penuh sejak server menyala, lalu berulang. |
| **Manual** | Menu **Backup Database** di `admin.html` (hanya Super Admin) atau `POST /api/v1/backup/run`. |
| **Interval** | Variabel lingkungan **`BACKUP_INTERVAL_SEC`** (detik). Contoh PowerShell: `$env:BACKUP_INTERVAL_SEC=1800; python app.py` |
| **Git** | Isi `backup/` diabaikan (lihat `.gitignore`). |
| **Restore** | Tutup aplikasi, salin file backup ke nama `payrollface.db` (cadangkan dulu file lama), lalu jalankan ulang server. |

### 6. Buka di Browser

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
| **Visitor Warning** | Saat pertama buka URL ngrok, mungkin muncul halaman peringatan — klik **Visit Site** untuk melanjutkan. |

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

1. Buka **Registrasi Pegawai**, isi **nama lengkap**, izinkan **kamera**; ikuti **satu kali kedip** lalu **Kirim Pendaftaran**.
2. Jika wajah **sudah terdaftar** pada akun lain, sistem menolak dan menampilkan pesan (beserta NIP pemilik wajah yang ada).
3. Setelah berhasil, catat **NIP** yang ditampilkan; **login dan absensi belum aktif** sampai HR memverifikasi.
4. HR memeriksa di **Kelola Karyawan** → kolom **Status HR** → tombol **Verifikasi** (ikon centang) jika status masih menunggu.

### Login

- **Face Recognition**: Izinkan kamera, pilih **Login dengan Wajah**; lulus **verifikasi kedip** lalu foto dikirim. **Izin kamera wajib**. Akun **belum diverifikasi HR** tidak dapat login (pesan khusus).
- **Manual (Admin)**: Toggle ke form manual. **Admin HR:** NIP `ADMIN001` (disimpan huruf besar) — password sesuai `PAYROLLFACE_BOOTSTRAP_HR_PASSWORD` atau default demo di tabel di atas. **Super Admin:** NIP `SUPERUSER` (nama **SUPER USER**) — password awal dari `PAYROLLFACE_BOOTSTRAP_SUPER_PASSWORD` / default demo; setelah login, kelola lewat **Kelola Akun Admin**. NIP berpola `NIP2604-001` adalah **nomor karyawan**, bukan akun Super Admin. Lihat kotak petunjuk di halaman login. Karyawan dengan status menunggu verifikasi tidak dapat login manual.

### Admin HRD

1. **Kelola Karyawan** — Atur **PPN slip gaji (%)** di atas tabel daftar (tombol Simpan). **Daftar** diurut berdasarkan **NIP naik**; gunakan kotak **Cari** untuk menyaring NIP atau nama. **Daftarkan** karyawan: foto wajah setelah **verifikasi kedip**. Atur **gaji pokok** dan **tipe tunjangan** (Staff / Supervisor). **NIP** dibuat otomatis; **tarif lembur** dihitung otomatis dari gaji pokok (field readonly). Wajah yang sama dengan pegawai lain **tidak dapat didaftarkan**. Untuk pegawai dari **registrasi mandiri**, gunakan **Verifikasi** agar bisa login/absensi; gunakan **Riwayat** untuk audit. **Edit** untuk semua admin; **hapus** karyawan hanya untuk pengguna yang terdaftar sebagai **Super Admin** (tombol sampah disembunyikan untuk admin biasa).
2. **Rekap Kehadiran** — Lihat absensi seluruh karyawan per bulan, lengkap dengan foto masuk/keluar, jam masuk/keluar, lembur, dan lokasi GPS. **Super Admin** melihat tombol **hapus** per baris (API `DELETE /api/v1/attendance/log/<id>`); Admin HR biasa tidak.
3. **Persetujuan Cuti** — Setujui atau tolak pengajuan cuti. Tombol **Riwayat** menampilkan siapa yang menyetujui/menolak dan kapan (jika tercatat).
4. **Slip Gaji** — Pilih karyawan dan bulan; rincian memuat gaji pokok, tunjangan, lembur, potongan **PPN** (sesuai persen pengaturan), dan gaji bersih.
5. **Absensi HR** — Sama seperti karyawan: **kamera + lokasi** wajib; liveness (kedip) lalu **verify** wajah. **Daftarkan Wajah Saya**: kedip + foto (tanpa lokasi).
6. **Backup Database** (hanya **Super Admin**) — Menu **Backup Database**: status backup otomatis/manual terakhir, daftar file di `backup/`, tombol **Backup sekarang**. Backup otomatis tiap jam berjalan selama server Flask aktif.
7. **Kelola Akun Admin** (hanya **Super Admin**) — Ubah nama dan/atau password untuk **Admin HR** (`ADMIN001`) dan akun **Super Admin** (`SUPERUSER`); tampilan status password (hash), cuplikan hash, dan riwayat perubahan password dari audit.

### Karyawan

1. **Absensi** — Pilih Masuk/Pulang; **lokasi** + **kamera**; verifikasi **kedip** lalu foto wajah dikirim. Akun **belum diverifikasi HR** tidak dapat absensi.
2. **Riwayat Kehadiran** — Tabel harian: foto masuk/keluar, jam, lembur, lokasi, dan keterangan.
3. **Pengajuan Cuti** — Isi formulir, upload surat dokter jika sakit (tersimpan di Cloudinary).
4. **Slip Gaji** — Pilih bulan; tampilan mencakup tunjangan, lembur (sesuai rumus), potongan **PPN**, dan gaji bersih.

### Rumus Payroll (ringkas)

**Penghasilan bruto (bulan)** untuk slip = **gaji pokok** + **total tunjangan** (hari hadir dalam bulan × tarif harian) + **total lembur** (jam × tarif lembur/jam).

| Komponen | Perhitungan |
|----------|-------------|
| Tunjangan bulan | `hari hadir (di bulan slip) × Rp25.000` (Staff) atau `× Rp35.000` (Supervisor) |
| Lembur/jam | `(gaji pokok ÷ 173) × 1,5` |
| PPN | `ppn_persen% × penghasilan bruto bulan` — `ppn_persen` di **Kelola Karyawan** (simpan ke `app_settings`; default **12%**) |
| Gaji bersih | bruto bulan − potongan PPN |

*PPN di aplikasi ini adalah penyederhanaan untuk tampilan slip, bukan pengganti ketentuan perpajakan resmi.*

### Mengubah persen PPN (admin)

1. Login sebagai admin → **Kelola Karyawan**.
2. Isi **PPN slip gaji (%)** (0–100) di atas tabel Daftar Karyawan → **Simpan**.
3. API alternatif: `PUT /api/v1/settings` dengan JSON, misalnya:

```json
{ "ppn_persen": 12, "actor_user_id": <id_admin_dari_localStorage> }
```

### Verifikasi kedip (liveness, browser)

| Hal | Keterangan |
|-----|------------|
| **Alur** | Kalibrasi wajah singkat (tetap fokus), lalu **kedip sekali**; selesai → foto diambil. |
| **Internet** | `face-api.js` + model (CDN) saat **pertama** dipakai per sisi/penyegaran cache. |
| **File** | Konstanta deteksi: `blink-liveness.js` |

## API Endpoints

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| POST | `/api/v1/login/face` | Login dengan face recognition; respons `user` berisi `superadmin` (boolean) |
| POST | `/api/v1/login/manual` | Login manual (**NIP** atau alias lama + password); respons `user` berisi `superadmin` |
| POST | `/api/v1/verify-liveness` | Absensi masuk/pulang; **wajib** `latitude` & `longitude` (izin lokasi) |
| GET | `/api/v1/settings` | Baca `ppn_persen` (untuk slip) |
| PUT | `/api/v1/settings` | Simpan PPN — body JSON: `ppn_persen` (0–100), `actor_user_id` (wajib, user admin) |
| GET | `/api/v1/nip/preview` | Pratinjau NIP berikutnya (otomatis) |
| POST | `/api/v1/face/register` | Enrollment karyawan oleh HR (`nama`, `gaji_pokok`, `tunjangan_tipe`, `image`, …); tolak jika wajah duplikat |
| POST | `/api/v1/employee/self-register` | Registrasi mandiri (`nama`, `image`); `pending_hr_verification=1`; tolak jika wajah duplikat |
| POST | `/api/v1/employee/hr-verify/<id>` | HR memverifikasi identitas (body: `actor_user_id` admin); hanya admin |
| GET | `/api/v1/employees` | Daftar karyawan + tunjangan, tarif lembur, status verifikasi (urut NIP ASC) |
| GET | `/api/v1/employee/data/<id>` | Data & riwayat kehadiran karyawan |
| PUT | `/api/v1/employee/update/<id>` | Edit data (`nama`, `gaji_pokok`, `tunjangan_tipe`, …) |
| DELETE | `/api/v1/employee/delete/<id>` | Hapus karyawan — **hanya Super Admin** (body JSON: `actor_user_id`, `actor_name`; pelaku harus ada di tabel `superadmin`) |
| GET | `/api/v1/attendance/all` | Rekap kehadiran semua karyawan (HR); respons berisi `log_id` untuk hapus |
| DELETE | `/api/v1/attendance/log/<id>` | Hapus satu baris kehadiran — **hanya Super Admin** (body: `actor_user_id`, `actor_name`) |
| GET | `/api/v1/admin/admin-accounts?actor_user_id=<id>` | Daftar akun `role=admin` + riwayat password — **hanya Super Admin** |
| PUT | `/api/v1/admin/admin-accounts/<id>` | Ubah nama/password akun admin — **hanya Super Admin** (body: `actor_user_id`, `nama`, `new_password`, …) |
| GET | `/api/v1/history?entity=users&record_id=<id>` atau `entity=leaves` | Riwayat perubahan untuk karyawan atau cuti |
| POST | `/api/v1/leave/request` | Ajukan cuti |
| POST | `/api/v1/leave/cancel` | Batalkan pengajuan cuti |
| GET | `/api/v1/leave/my/<id>` | Riwayat cuti per karyawan |
| GET | `/api/v1/leave/list` | Daftar semua cuti (HR) |
| POST | `/api/v1/leave/approve` | Setujui/tolak cuti |
| GET | `/api/v1/payroll/<id>` | Hitung slip gaji bulanan (tunjangan, lembur, PPN, gaji bersih) |
| POST | `/api/v1/admin/register-face` | Daftarkan wajah admin |
| GET | `/api/v1/backup/status?actor_user_id=<id>` | Status backup + daftar file di `backup/` — **hanya Super Admin** |
| POST | `/api/v1/backup/run` | Backup manual (`actor_user_id` di body JSON) — **hanya Super Admin** |

## Database Schema

Tabel utama (SQLite, auto-generated / dimigrasi saat `app.py` dijalankan):

- **users** — `id`, `nik` (legacy), `nip`, `nama`, `role`, `password`, `gaji_pokok`, `tunjangan_tipe` (`staff` / `supervisor`), `daily_rate` (disinkronkan dengan nominal tunjangan per hari), `overtime_rate` (disinkronkan dengan rumus lembur), `pending_hr_verification` (`1` = menunggu verifikasi HR setelah registrasi mandiri; `0` = boleh login/absensi), `face_encoding`, `created_at`
- **attendance_logs** — `id`, `user_id` (FK), `tanggal`, `jam_masuk`, `jam_keluar`, `overtime_hours`, `latitude`, `longitude`, `foto_masuk`, `foto_keluar`, `status`
- **leaves** — `id`, `user_id` (FK), `jenis_cuti`, `tanggal`, `alasan`, `attachment` (URL Cloudinary), `status`
- **change_history** — `id`, `entity` (`users` / `leaves`), `record_id`, `action`, `changed_by_user_id`, `changed_by_name`, `detail`, `created_at`
- **app_settings** — `key`, `value` (mis. `ppn_persen` = persen PPN dari bruto slip; `nip2604_001_demoted_from_admin` = flag migrasi admin→karyawan untuk NIP `NIP2604-001`)
- **superadmin** — `user_id` (PRIMARY KEY, FK ke `users.id`, ON DELETE CASCADE). Isi baris = Super Admin: boleh **hapus karyawan**, **mengakses backup** (API & menu), kolom opsional `users.is_superadmin` (legacy) dipakai sekali saat migrasi.

**Folder `backup/`** — bukan tabel; berisi salinan file `payrollface.db` yang dihasilkan backup otomatis/manual.

### Menambahkan atau mencabut Super Admin (manual)

Super Admin harus berupa pengguna dengan **`role` = `admin`** di tabel `users`. Keanggotaan diatur lewat tabel **`superadmin`** (bukan kolom boolean terpisah, kecuali migrasi legacy).

1. Cari `id` admin yang ingin dijadikan Super Admin:
   ```sql
   SELECT id, nip, nama, role FROM users WHERE role = 'admin';
   ```
2. Tambahkan baris (ganti `123` dengan `id` yang benar):
   ```sql
   INSERT OR IGNORE INTO superadmin (user_id) VALUES (123);
   ```
3. Untuk **menghapus** hak Super Admin tanpa menghapus akun:
   ```sql
   DELETE FROM superadmin WHERE user_id = 123;
   ```

Gunakan **DB Browser for SQLite**, ekstensi editor, atau `sqlite3` CLI dengan file `payrollface.db`. Setelah mengubah data, pengguna yang bersangkutan disarankan **logout dan login ulang** agar `localStorage` memuat field `superadmin` terbaru.
---

## Ringkasan peran

| Peran | Login (NIP / password) | Hapus karyawan | Menu backup |
|-------|------------------------|----------------|-------------|
| Admin HR | `ADMIN001` + bootstrap HR (env atau demo) | Tidak | Tidak |
| Super Admin | `SUPERUSER` + bootstrap Super (env atau demo) | Ya | Ya |