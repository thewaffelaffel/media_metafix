"""Minimal JSON-over-HTTPS helpers (stdlib only)."""

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TIMEOUT = 30


def fetch(url, params=None, headers=None, body=None):
    """Raw response bytes. `body` (a dict) is POSTed as JSON."""
    if params:
        # Sorted, lowercase-keyed params (OpenSubtitles redirects
        # otherwise).
        url += "?" + urlencode(sorted(params.items()))
    headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers)
    with urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def fetch_json(url, params=None, headers=None, body=None):
    headers = dict(headers or {}, Accept="application/json")
    return json.loads(fetch(url, params, headers, body))
