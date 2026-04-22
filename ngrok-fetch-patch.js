/**
 * Ngrok free tier shows a browser warning unless requests include this header.
 * Patches global fetch so all same-origin API calls send it automatically.
 */
(function () {
    if (typeof window.fetch !== 'function' || window.__payrollfaceNgrokFetchPatched) return;
    window.__payrollfaceNgrokFetchPatched = true;
    var orig = window.fetch.bind(window);
    var HEADER = 'ngrok-skip-browser-warning';
    var VALUE = '1';

    window.fetch = function (input, init) {
        var next = init ? Object.assign({}, init) : {};
        var h = new Headers(next.headers || undefined);
        if (!h.has(HEADER)) h.set(HEADER, VALUE);
        next.headers = h;
        return orig(input, next);
    };
})();
