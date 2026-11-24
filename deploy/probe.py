"""Health probes for the Python containers, run by ``deploy/healthcheck.sh``.

Standard library only, so it runs the same in both images and does not
depend on the app importing cleanly.

    probe.py http <url>
        Succeeds when the URL answers 2xx.

    probe.py deployment <prefect api url> <flow/deployment>
        Succeeds unless Prefect says the deployment is NOT_READY, which it
        does once the process serving it has stopped polling -- what a hung
        worker looks like. An unreachable Prefect also succeeds: the worker
        cannot be judged then, and restarting it would not bring Prefect back.
"""

import json
import sys
import urllib.error
import urllib.request

#: Below Docker's own healthcheck timeout, so a hung endpoint is counted as a
#: failure here rather than the probe being killed without a result.
TIMEOUT_SECONDS = 5


def http(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError):
        return False


def deployment(api_url: str, name: str) -> bool:
    url = f"{api_url.rstrip('/')}/deployments/name/{name}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            status = json.load(response).get("status")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return True
    return status != "NOT_READY"


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["http", url]:
            healthy = http(url)
        case ["deployment", api_url, name]:
            healthy = deployment(api_url, name)
        case _:
            sys.exit(__doc__)
    sys.exit(0 if healthy else 1)
