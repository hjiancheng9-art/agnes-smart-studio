import time

import httpx

with open('_net_result.txt', 'w') as f:
    for label, url in [
        ("Bing", "https://www.bing.com"),
        ("DDG", "https://html.duckduckgo.com/html/?q=test"),
    ]:
        t0 = time.time()
        try:
            r = httpx.get(url, timeout=httpx.Timeout(10, connect=5), trust_env=False)
            f.write(f"{label}: OK HTTP{r.status_code} {len(r.text)}chars {time.time()-t0:.1f}s\n")
        except httpx.ConnectError:
            f.write(f"{label}: CONNECT_FAILED {time.time()-t0:.1f}s\n")
        except httpx.TimeoutException:
            f.write(f"{label}: TIMEOUT {time.time()-t0:.1f}s\n")
        except Exception as e:
            f.write(f"{label}: {type(e).__name__} {time.time()-t0:.1f}s\n")
