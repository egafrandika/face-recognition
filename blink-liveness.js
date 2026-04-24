/**
 * Liveness: satu kali kedip (EAR, face-api + landmark). Pustaka & model dari CDN (koneksi internet perlu).
 * Bobot: tag @0.22.2; fallback skrip/URL bila satu CDN lambat/terblok.
 */
(function (global) {
    const FACE_API_PRIMARY =
        'https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js';
    const FACE_API_FALLBACK = 'https://unpkg.com/face-api.js@0.22.2/dist/face-api.min.js';
    const WEIGHTS_URIS = [
        'https://cdn.jsdelivr.net/gh/justadudewhohacks/face-api.js@0.22.2/weights',
        'https://raw.githubusercontent.com/justadudewhohacks/face-api.js/0.22.2/weights',
    ];

    var modelsLoaded = false;
    var modelsLoading = null;
    var faceApiLoading = null;

    function setHint(hintId, text, color) {
        var el = hintId && document.getElementById(hintId);
        if (el) {
            el.textContent = text;
            if (color) el.style.color = color;
        }
    }

    function dist(p1, p2) {
        return Math.hypot(p1.x - p2.x, p1.y - p2.y);
    }

    function earFromSixPoints(eye) {
        if (!eye || eye.length < 6) return 0.35;
        return (dist(eye[1], eye[5]) + dist(eye[2], eye[4])) / (2 * dist(eye[0], eye[3]));
    }

    function loadScriptOnce(url) {
        return new Promise(function (resolve, reject) {
            var s = document.createElement('script');
            s.src = url;
            s.async = true;
            s.crossOrigin = 'anonymous';
            s.onload = function () { resolve(); };
            s.onerror = function () {
                if (s.parentNode) s.parentNode.removeChild(s);
                reject(new Error('Gagal memuat skrip: ' + url));
            };
            document.head.appendChild(s);
        });
    }

    function loadFaceApiScript() {
        if (typeof faceapi !== 'undefined') return Promise.resolve();
        if (faceApiLoading) return faceApiLoading;
        var p = (async function () {
            if (typeof faceapi !== 'undefined') return;
            try {
                await loadScriptOnce(FACE_API_PRIMARY);
            } catch (e1) {
                await loadScriptOnce(FACE_API_FALLBACK);
            }
            if (typeof faceapi === 'undefined') {
                throw new Error('Gagal memuat pustaka face-api.js (jaringan, firewall, atau ekstensi memblokir CDN).');
            }
        })();
        faceApiLoading = p;
        p.catch(function () {
            faceApiLoading = null;
        });
        return p;
    }

    function loadBlinkModelsInternal() {
        if (modelsLoaded) return Promise.resolve();
        if (modelsLoading) return modelsLoading;
        var p = (async function () {
            await loadFaceApiScript();
            if (typeof faceapi === 'undefined') throw new Error('face-api.js tidak tersedia');
            var lastErr = null;
            for (var i = 0; i < WEIGHTS_URIS.length; i++) {
                var base = WEIGHTS_URIS[i];
                try {
                    await faceapi.nets.tinyFaceDetector.loadFromUri(base);
                    await faceapi.nets.faceLandmark68TinyNet.loadFromUri(base);
                    modelsLoaded = true;
                    lastErr = null;
                    break;
                } catch (e) {
                    lastErr = e;
                }
            }
            if (!modelsLoaded) {
                var d =
                    lastErr && (lastErr.message || String(lastErr)) ? ' ' + (lastErr.message || String(lastErr)) : '';
                throw new Error('Gagal memuat model wajah (cek jaringan; coba matikan adblock/ekstensi uji coba). ' + d);
            }
        })();
        modelsLoading = p.catch(function (e) {
            modelsLoading = null;
            throw e;
        });
        return modelsLoading;
    }

    function loadBlinkModels() {
        return loadBlinkModelsInternal().catch(function (e) {
            modelsLoading = null;
            throw e;
        });
    }

    function waitForBlinkOnce(videoId, hintId, options) {
        options = options || {};
        var timeoutMs = options.timeoutMs != null ? options.timeoutMs : 45000;
        var CALIB_FRAMES = 22;
        var DROP_RATIO = 0.82;
        var RECOVER_RATIO = 0.84;
        var MIN_DROP_ABS = 0.028;

        return loadBlinkModelsInternal()
            .then(function () {
                var video = document.getElementById(videoId);
                if (!video) throw new Error('Elemen video tidak ditemukan');
                if (hintId) setHint(hintId, 'Memproses…', '#3b82f6');
                return new Promise(function (resolve, reject) {
                    var done = false;
                    var t0 = Date.now();
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
                        if (hintId) setHint(hintId, msg, '#ef4444');
                    }

                    function computeBaseline(arr) {
                        if (!arr.length) return 0.26;
                        var s = arr.slice().sort(function (a, b) { return a - b; });
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
                            failHint('Waktu habis. Coba lagi.');
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
                                        scoreThreshold: 0.38,
                                    })
                                )
                                .withFaceLandmarks(true);
                            if (!det) {
                                if (hintId) setHint(hintId, 'Arahkan wajah ke kamera.', '#f59e0b');
                                requestAnimationFrame(loop);
                                return;
                            }
                            var lm = det.landmarks;
                            var left = lm.getLeftEye();
                            var right = lm.getRightEye();
                            var earRaw = (earFromSixPoints(left) + earFromSixPoints(right)) / 2;

                            if (phase === 'calibrate') {
                                calibSamples.push(earRaw);
                                if (hintId && calibSamples.length === 1) {
                                    setHint(
                                        hintId,
                                        'Tetap fokus wajah ke kamera.',
                                        '#3b82f6'
                                    );
                                }
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
                                    if (hintId) {
                                        setHint(hintId, 'Kedip sekali.', '#3b82f6');
                                    }
                                }
                                requestAnimationFrame(loop);
                                return;
                            }

                            if (phase === 'wait_drop') {
                                if (earRaw < lowThreshold && baseline - earRaw >= MIN_DROP_ABS * 0.85) {
                                    phase = 'wait_open';
                                    seenLowAt = Date.now();
                                    if (hintId) setHint(hintId, 'Buka mata.', '#3b82f6');
                                } else if (hintId) {
                                    setHint(hintId, 'Kedip sekali.', '#3b82f6');
                                }
                                requestAnimationFrame(loop);
                                return;
                            }

                            if (phase === 'wait_open') {
                                if (earRaw >= recoverThreshold) {
                                    if (Date.now() - seenLowAt > 45) {
                                        if (hintId) setHint(hintId, 'Selesai.', '#10b981');
                                        finish(true);
                                        return;
                                    }
                                }
                                if (hintId) setHint(hintId, 'Buka mata.', '#3b82f6');
                            }
                        } catch (e) {
                            if (hintId) {
                                setHint(hintId, 'Gagal sementara — coba lagi.', '#ef4444');
                            }
                        }
                        requestAnimationFrame(loop);
                    }

                    requestAnimationFrame(loop);
                });
            })
            .catch(function (e) {
                if (hintId) {
                    var msg =
                        e && e.message
                            ? e.message
                            : 'Cek jaringan lalu coba lagi.';
                    setHint(hintId, msg, '#ef4444');
                }
                return Promise.reject(e);
            });
    }

    global.loadBlinkModels = loadBlinkModels;
    global.waitForBlinkOnce = waitForBlinkOnce;
})(typeof window !== 'undefined' ? window : global);
