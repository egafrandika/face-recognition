/**
 * Verifikasi liveness: satu kali kedip (EAR dari landmark mata).
 * Memuat face-api.js dari CDN jika belum ada; model TinyFaceDetector + landmark68 tiny.
 */
(function (global) {
    const WEIGHTS_BASE = 'https://cdn.jsdelivr.net/gh/justadudewhohacks/face-api.js@master/weights';
    const FACE_API_CDN = 'https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js';

    let modelsLoaded = false;
    let modelsLoading = null;
    let faceApiLoading = null;

    function setHint(hintId, text, color) {
        const el = hintId && document.getElementById(hintId);
        if (el) {
            el.textContent = text;
            if (color) el.style.color = color;
        }
    }

    function dist(p1, p2) {
        return Math.hypot(p1.x - p2.x, p1.y - p2.y);
    }

    /** EAR untuk 6 titik mata (urutan face-api / dlib). */
    function earFromSixPoints(eye) {
        if (!eye || eye.length < 6) return 0.35;
        return (dist(eye[1], eye[5]) + dist(eye[2], eye[4])) / (2 * dist(eye[0], eye[3]));
    }

    function loadFaceApiScript() {
        if (typeof faceapi !== 'undefined') return Promise.resolve();
        if (faceApiLoading) return faceApiLoading;
        faceApiLoading = new Promise(function (resolve, reject) {
            var s = document.createElement('script');
            s.src = FACE_API_CDN;
            s.async = true;
            s.onload = function () { resolve(); };
            s.onerror = function () { reject(new Error('Gagal memuat pustaka face-api.js')); };
            document.head.appendChild(s);
        });
        return faceApiLoading;
    }

    function loadBlinkModelsInternal() {
        if (modelsLoaded) return Promise.resolve();
        if (modelsLoading) return modelsLoading;
        var p = (async function () {
            await loadFaceApiScript();
            if (typeof faceapi === 'undefined') throw new Error('face-api.js tidak tersedia');
            await faceapi.nets.tinyFaceDetector.loadFromUri(WEIGHTS_BASE);
            await faceapi.nets.faceLandmark68TinyNet.loadFromUri(WEIGHTS_BASE);
            modelsLoaded = true;
        })();
        modelsLoading = p.catch(function (e) {
            modelsLoading = null;
            throw e;
        });
        return modelsLoading;
    }

    /**
     * Pra-muat model (opsional, untuk mengurangi jeda saat pertama kali kedip).
     */
    function loadBlinkModels() {
        return loadBlinkModelsInternal().catch(function (e) {
            modelsLoading = null;
            throw e;
        });
    }

    /**
     * Menunggu satu siklus kedip (turun signifikan dari baseline, lalu kembali).
     * Menggunakan kalibrasi singkat + ambang relatif — nilai EAR absolut berbeda tiap orang/kamera.
     * @param {string} videoId
     * @param {string|null} hintId
     * @param {{ timeoutMs?: number }} [options]
     * @returns {Promise<void>}
     */
    function waitForBlinkOnce(videoId, hintId, options) {
        options = options || {};
        var timeoutMs = options.timeoutMs != null ? options.timeoutMs : 45000;
        /** Jumlah sampel untuk baseline mata terbuka */
        var CALIB_FRAMES = 22;
        /** Turun cukup jauh dari baseline = indikasi mata menutup */
        var DROP_RATIO = 0.82;
        /** Setelah turun, naik kembali (tidak harus 100% baseline — cukup “buka lagi”) */
        var RECOVER_RATIO = 0.84;
        /** Minimal penurunan absolut (mengurangi false positive) */
        var MIN_DROP_ABS = 0.028;
        /** Deteksi menggunakan EAR mentah agar kedip cepat tidak terhapus oleh smoothing */

        return loadBlinkModelsInternal()
            .then(function () {
                var video = document.getElementById(videoId);
                if (!video) throw new Error('Elemen video tidak ditemukan');
                setHint(hintId, 'Memuat model verifikasi kedip…', '#3b82f6');
                return new Promise(function (resolve, reject) {
                    var done = false;
                    var t0 = Date.now();
                    /** 'calibrate' | 'wait_drop' | 'wait_open' */
                    var phase = 'calibrate';
                    var calibSamples = [];
                    var baseline = 0.26;
                    var seenLowAt = 0;
                    var lowThreshold = 0.14;
                    var recoverThreshold = 0.22;

                    function finish(ok, err) {
                        if (done) return;
                        done = true;
                        if (ok) resolve();
                        else reject(err || new Error('blink_failed'));
                    }

                    function failHint(msg) {
                        setHint(hintId, msg, '#ef4444');
                    }

                    function computeBaseline(arr) {
                        if (!arr.length) return 0.26;
                        var s = arr.slice().sort(function (a, b) {
                            return a - b;
                        });
                        var from = Math.floor(s.length * 0.2);
                        var to = Math.ceil(s.length * 0.8);
                        var slice = s.slice(from, to);
                        if (!slice.length) slice = s;
                        var sum = 0;
                        for (var i = 0; i < slice.length; i++) sum += slice[i];
                        return sum / slice.length;
                    }

                    async function loop() {
                        if (done) return;
                        if (Date.now() - t0 > timeoutMs) {
                            failHint('Waktu habis. Kedipkan mata sekali, lalu coba lagi.');
                            finish(false, new Error('timeout'));
                            return;
                        }
                        if (!video.videoWidth || video.readyState < 2) {
                            requestAnimationFrame(loop);
                            return;
                        }
                        try {
                            var det = await faceapi
                                .detectSingleFace(
                                    video,
                                    new faceapi.TinyFaceDetectorOptions({
                                        inputSize: 416,
                                        scoreThreshold: 0.38
                                    })
                                )
                                .withFaceLandmarks(true);
                            if (!det) {
                                setHint(
                                    hintId,
                                    'Wajah tidak terdeteksi — hadapkan wajah ke kamera, lalu kedip sekali.',
                                    '#f59e0b'
                                );
                                requestAnimationFrame(loop);
                                return;
                            }
                            var lm = det.landmarks;
                            var left = lm.getLeftEye();
                            var right = lm.getRightEye();
                            var earRaw = (earFromSixPoints(left) + earFromSixPoints(right)) / 2;

                            if (phase === 'calibrate') {
                                calibSamples.push(earRaw);
                                setHint(
                                    hintId,
                                    'Tahan mata terbuka, jangan kedip dulu (' +
                                        calibSamples.length +
                                        '/' +
                                        CALIB_FRAMES +
                                        ')…',
                                    '#3b82f6'
                                );
                                if (calibSamples.length >= CALIB_FRAMES) {
                                    baseline = computeBaseline(calibSamples);
                                    if (baseline < 0.12) baseline = 0.14;
                                    if (baseline > 0.45) baseline = 0.42;
                                    lowThreshold = Math.max(0.09, baseline * DROP_RATIO);
                                    if (baseline - lowThreshold < MIN_DROP_ABS) {
                                        lowThreshold = baseline - MIN_DROP_ABS;
                                    }
                                    recoverThreshold = Math.max(
                                        lowThreshold + 0.012,
                                        Math.min(baseline * 0.96, baseline * RECOVER_RATIO)
                                    );
                                    phase = 'wait_drop';
                                    setHint(
                                        hintId,
                                        'Kedipkan mata sekali (tutup lalu buka).',
                                        '#3b82f6'
                                    );
                                }
                                requestAnimationFrame(loop);
                                return;
                            }

                            if (phase === 'wait_drop') {
                                if (earRaw < lowThreshold && baseline - earRaw >= MIN_DROP_ABS * 0.85) {
                                    phase = 'wait_open';
                                    seenLowAt = Date.now();
                                    setHint(hintId, 'Bagus — buka mata lagi.', '#3b82f6');
                                } else {
                                    setHint(
                                        hintId,
                                        'Kedipkan mata sekali (tutup lalu buka).',
                                        '#3b82f6'
                                    );
                                }
                                requestAnimationFrame(loop);
                                return;
                            }

                            if (phase === 'wait_open') {
                                if (earRaw >= recoverThreshold) {
                                    if (Date.now() - seenLowAt > 45) {
                                        setHint(hintId, 'Verifikasi kedip berhasil.', '#10b981');
                                        finish(true);
                                        return;
                                    }
                                }
                                setHint(hintId, 'Buka mata sepenuhnya…', '#3b82f6');
                            }
                        } catch (e) {
                            console.warn('[blink-liveness]', e);
                            setHint(
                                hintId,
                                'Verifikasi sementara gagal. Pastikan pencahayaan cukup dan coba lagi.',
                                '#ef4444'
                            );
                        }
                        requestAnimationFrame(loop);
                    }

                    requestAnimationFrame(loop);
                });
            })
            .catch(function (e) {
                var msg =
                    e && e.message
                        ? e.message
                        : 'Tidak dapat memuat verifikasi kedip. Periksa koneksi internet.';
                setHint(hintId, msg, '#ef4444');
                return Promise.reject(e);
            });
    }

    global.loadBlinkModels = loadBlinkModels;
    global.waitForBlinkOnce = waitForBlinkOnce;
})(typeof window !== 'undefined' ? window : global);
