        // ── Media detection ──
        (async function() {
            var detector = window.__CRUX_MEDIA_DETECTOR__;
            if (!detector) return;
            await new Promise(function(r) { setTimeout(r, 1500); });
            var candidates = detector.scanPage();
            if (candidates.length === 0) return;
            try {
                chrome.runtime.sendMessage({
                    type: 'MEDIA_DETECTED',
                    payload: {
                        pageUrl: window.location.href,
                        title: document.title,
                        candidates: candidates.map(function(c) {
                            return { url: c.url, kind: c.kind, confidence: c.confidence, title: c.title };
                        })
                    }
                });
            } catch(e) {}
        })();
    }

    chrome.storage.local.get({ currentTask: null }).then(function(data) {
        if (!data.currentTask) return;
        var adapter = activeAdapter();
        if (adapter && adapter.matchUrl(window.location.href)) {
            currentTask = data.currentTask;
            renderPanel();
        }
    });
}());
