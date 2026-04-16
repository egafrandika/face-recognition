const _cameras = {};

function setHint(elementId, text, color) {
    const el = elementId && document.getElementById(elementId);
    if (el) { el.innerText = text; if (color) el.style.color = color; }
}

function getUserMediaCompat(constraints) {
    if (navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === 'function') {
        return navigator.mediaDevices.getUserMedia(constraints);
    }
    const legacy = navigator.getUserMedia || navigator.webkitGetUserMedia ||
                   navigator.mozGetUserMedia || navigator.msGetUserMedia;
    if (!legacy) return Promise.reject(new Error('NO_GET_USER_MEDIA'));
    return new Promise((resolve, reject) => legacy.call(navigator, constraints, resolve, reject));
}

function explainCameraBlocked(hintId) {
    if (location.protocol === 'file:') {
        setHint(hintId, 'Jalankan python app.py lalu buka http://127.0.0.1:5000/', '#ef4444');
        return;
    }
    if (typeof window.isSecureContext === 'boolean' && !window.isSecureContext) {
        if (location.hostname !== 'localhost' && location.hostname !== '127.0.0.1' && location.protocol === 'http:') {
            setHint(hintId, 'Kamera diblokir pada HTTP non-localhost. Gunakan HTTPS (ngrok) atau localhost.', '#ef4444');
            return;
        }
    }
    setHint(hintId, 'Browser tidak dapat mengakses kamera. Gunakan Chrome/Edge/Firefox terbaru.', '#ef4444');
}

function initCamera(videoId, hintId) {
    const video = document.getElementById(videoId);
    if (!video) return;

    _cameras[videoId] = false;
    setHint(hintId, 'Menghubungkan kamera...', '#3b82f6');

    video.setAttribute('playsinline', '');
    video.setAttribute('muted', '');
    video.muted = true;

    if (location.protocol === 'file:') { explainCameraBlocked(hintId); return; }

    const constraints = {
        video: { facingMode: { ideal: 'user' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false
    };

    getUserMediaCompat(constraints)
        .then(stream => {
            video.srcObject = stream;
            _cameras[videoId] = true;
            const onReady = () => {
                if (video.videoWidth > 0) setHint(hintId, 'Kamera aktif — posisikan wajah dalam bingkai.', '#10b981');
            };
            video.onloadedmetadata = () => { video.play().catch(() => {}); onReady(); };
            video.onresize = onReady;
        })
        .catch(err => {
            _cameras[videoId] = false;
            if (err && err.message === 'NO_GET_USER_MEDIA') { explainCameraBlocked(hintId); return; }
            let msg = 'Tidak bisa mengakses kamera. ';
            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError')
                msg += 'Izin kamera harus diaktifkan. Buka ikon gembok / pengaturan situs di bilah alamat browser, izinkan Kamera untuk situs ini, lalu muat ulang halaman.';
            else if (err.name === 'NotFoundError') msg += 'Tidak ada kamera terdeteksi.';
            else if (err.name === 'NotReadableError') msg += 'Kamera dipakai aplikasi lain.';
            else msg += err.message || String(err);
            setHint(hintId, msg, '#ef4444');
        });
}

function stopCamera(videoId) {
    const video = document.getElementById(videoId);
    if (video && video.srcObject) {
        video.srcObject.getTracks().forEach(t => t.stop());
        video.srcObject = null;
    }
    _cameras[videoId] = false;
}

function isCameraReady(videoId) { return _cameras[videoId] === true; }

/** Pesan standar jika kamera tidak siap (mis. izin ditolak). */
function alertCameraRequired() {
    alert('Izin kamera harus diaktifkan untuk absensi. Buka pengaturan situs di browser, izinkan akses kamera, lalu muat ulang halaman.');
}

function captureFrameFromVideo(video) {
    if (!video || (!video.srcObject && !video.src)) return null;
    const w = video.videoWidth, h = video.videoHeight;
    if (!w || !h) return null;
    const canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    canvas.getContext('2d').drawImage(video, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.92);
}

function waitForFrame(videoId, maxAttempts) {
    maxAttempts = maxAttempts || 30;
    return new Promise(resolve => {
        const video = document.getElementById(videoId);
        let attempts = 0;
        const tick = () => {
            const data = captureFrameFromVideo(video);
            if (data) { resolve(data); return; }
            if (++attempts >= maxAttempts) { resolve(null); return; }
            requestAnimationFrame(tick);
        };
        tick();
    });
}

function getImageDataUrl(videoId) {
    const video = document.getElementById(videoId);
    return (_cameras[videoId] && video) ? captureFrameFromVideo(video) : null;
}

async function getImageDataUrlAsync(videoId) {
    let data = getImageDataUrl(videoId);
    if (data) return data;
    if (!_cameras[videoId]) return null;
    return await waitForFrame(videoId);
}

/** Pesan untuk pengguna jika geolokasi gagal (absensi wajib lokasi). */
function geoErrorToMessage(err) {
    if (!err) return 'Lokasi wajib untuk absensi. Izinkan akses lokasi lalu coba lagi.';
    if (err.code === 1) return 'Izin lokasi ditolak. Buka pengaturan situs di browser, izinkan Lokasi, lalu muat ulang halaman.';
    if (err.code === 2) return 'Posisi tidak tersedia sementara. Periksa GPS/sinyal lalu coba lagi.';
    if (err.code === 3) return 'Permintaan lokasi habis waktu. Coba lagi.';
    if (err.message === 'NO_GEO') return 'Browser tidak mendukung geolokasi.';
    return 'Lokasi wajib untuk absensi. Aktifkan izin lokasi lalu coba lagi.';
}

/**
 * Lokasi wajib untuk absensi — gagal jika izin ditolak / GPS error.
 * @returns {Promise<{latitude: number, longitude: number}>}
 */
function getLocationRequired() {
    return new Promise(function (resolve, reject) {
        if (!navigator.geolocation) {
            reject(Object.assign(new Error('NO_GEO'), { code: 0 }));
            return;
        }
        navigator.geolocation.getCurrentPosition(
            function (p) {
                resolve({ latitude: p.coords.latitude, longitude: p.coords.longitude });
            },
            function (err) { reject(err); },
            { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
        );
    });
}
