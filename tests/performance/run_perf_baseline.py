"""VibeConnect Performance Baseline, Stress, and Soak Harness.

A lightweight, repeatable performance testing harness consuming Python standard
library only (no external load packages required). Suitable for isolated staging
and local controlled verification.

Supports configurable target URL, concurrency, duration, and synthetic user credentials.
"""

import argparse
import base64
import hashlib
import json
import os
import statistics
import sys
import threading
import time
import urllib.parse
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

DEFAULT_LOCAL_TARGET = "http://127.0.0.1:8123"


class WorkerSession:
    """Encapsulates an isolated HTTP client session with cookie management."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.cj = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cj))
        self.csrf_token = None

    def clone(self) -> "WorkerSession":
        new_sess = WorkerSession(self.base_url)
        for cookie in self.cj:
            new_sess.cj.set_cookie(cookie)
        new_sess.csrf_token = self.csrf_token
        return new_sess

    def get_csrf(self) -> str:
        req = Request(f"{self.base_url}/api/v1/auth/csrf/")
        with self.opener.open(req, timeout=10.0) as resp:
            for cookie in self.cj:
                if "csrf" in cookie.name.lower():
                    self.csrf_token = cookie.value
        return self.csrf_token

    def login(self, email: str, password: str):
        if not self.csrf_token:
            self.get_csrf()
        data = json.dumps({"email": email, "password": password}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-CSRFToken": self.csrf_token,
            "Referer": f"{self.base_url}/login",
        }
        req = Request(f"{self.base_url}/api/v1/auth/login/", data=data, headers=headers)
        with self.opener.open(req, timeout=10.0) as resp:
            for cookie in self.cj:
                if "csrf" in cookie.name.lower():
                    self.csrf_token = cookie.value
            return resp.status, json.loads(resp.read().decode())

    def select_context(self, context_type: str, organization_id: str = None):
        payload = {"context_type": context_type}
        if organization_id:
            payload["organization_id"] = organization_id
        headers = {
            "Content-Type": "application/json",
            "X-CSRFToken": self.csrf_token,
            "Referer": f"{self.base_url}/select-context",
        }
        req = Request(f"{self.base_url}/api/v1/auth/context/", data=json.dumps(payload).encode("utf-8"), headers=headers)
        with self.opener.open(req, timeout=10.0) as resp:
            for cookie in self.cj:
                if "csrf" in cookie.name.lower():
                    self.csrf_token = cookie.value
            return resp.status, json.loads(resp.read().decode())

    def get_tenant_home(self):
        req = Request(f"{self.base_url}/api/v1/tenant/home/")
        with self.opener.open(req, timeout=10.0) as resp:
            return resp.status, json.loads(resp.read().decode())

    def get_products(self):
        req = Request(f"{self.base_url}/api/v1/products/")
        with self.opener.open(req, timeout=10.0) as resp:
            return resp.status, json.loads(resp.read().decode())

    def launch_sso(self, product_id: str, organization_id: str):
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

        payload = json.dumps({
            "product_id": product_id,
            "organization_id": organization_id,
            "state": "perf_test_state",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-CSRFToken": self.csrf_token,
            "Referer": f"{self.base_url}/tenant/home",
        }
        req = Request(f"{self.base_url}/api/v1/sso/launch/", data=payload, headers=headers)
        with self.opener.open(req, timeout=10.0) as resp:
            return resp.status, json.loads(resp.read().decode())


def execute_journey(base_url: str, journey_type: str, cached_ids: dict, session: WorkerSession, user_email: str, password: str):
    """Executes a single journey request and returns (latency_sec, status_code, is_error)."""
    t0 = time.perf_counter()
    status_code = 0
    is_error = False

    try:
        if journey_type == "health_liveness":
            req = Request(f"{base_url}/api/v1/health/")
            with session.opener.open(req, timeout=10.0) as resp:
                status_code = resp.status

        elif journey_type == "health_readiness":
            req = Request(f"{base_url}/api/v1/health/ready/")
            with session.opener.open(req, timeout=10.0) as resp:
                status_code = resp.status

        elif journey_type == "auth_lifecycle":
            fresh = WorkerSession(base_url)
            fresh.get_csrf()
            st, _ = fresh.login(user_email, password)
            status_code = st

        elif journey_type == "tenant_context_and_home":
            st, _ = session.get_tenant_home()
            status_code = st

        elif journey_type == "owner_catalog":
            st, _ = session.get_products()
            status_code = st

        elif journey_type == "sso_launch_pkce":
            st, _ = session.launch_sso(cached_ids["product_id"], cached_ids["org_id"])
            status_code = st

        else:
            raise ValueError(f"Unknown journey: {journey_type}")

        is_error = (status_code < 200 or status_code >= 400)

    except HTTPError as e:
        status_code = e.code
        is_error = True
    except (URLError, TimeoutError, Exception):
        status_code = 599
        is_error = True

    latency = time.perf_counter() - t0
    return latency, status_code, is_error


def run_benchmark(
    name: str,
    base_url: str,
    journey_type: str,
    concurrency: int,
    duration_sec: int,
    cached_ids: dict,
    user_email: str,
    password: str,
    session_template: WorkerSession = None,
    max_requests: int = None,
):
    """Runs a bounded load test with specified concurrency and duration."""
    latencies = []
    status_counts = {}
    error_count = 0
    total_requests = 0

    stop_event = threading.Event()
    start_time = time.perf_counter()
    deadline = start_time + duration_sec

    lock = threading.Lock()

    def worker():
        nonlocal total_requests, error_count
        sess = session_template.clone() if session_template else WorkerSession(base_url)
        while not stop_event.is_set():
            if time.perf_counter() >= deadline:
                break
            with lock:
                if max_requests and total_requests >= max_requests:
                    break

            lat, sc, err = execute_journey(base_url, journey_type, cached_ids, sess, user_email, password)
            with lock:
                latencies.append(lat)
                status_counts[sc] = status_counts.get(sc, 0) + 1
                if err:
                    error_count += 1
                total_requests += 1

                # Safety abort condition: error rate > 30% after 20 requests
                if total_requests > 20 and (error_count / total_requests) > 0.30:
                    stop_event.set()

    threads = []
    for _ in range(concurrency):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=duration_sec + 10.0)

    total_time = time.perf_counter() - start_time
    throughput = total_requests / total_time if total_time > 0 else 0

    if latencies:
        sorted_lats = sorted(latencies)
        p50 = statistics.median(sorted_lats) * 1000
        p95 = sorted_lats[min(int(len(sorted_lats) * 0.95), len(sorted_lats) - 1)] * 1000
        p99 = sorted_lats[min(int(len(sorted_lats) * 0.99), len(sorted_lats) - 1)] * 1000
        mean_lat = statistics.mean(sorted_lats) * 1000
        min_lat = min(sorted_lats) * 1000
        max_lat = max(sorted_lats) * 1000
    else:
        p50 = p95 = p99 = mean_lat = min_lat = max_lat = 0

    return {
        "benchmark_name": name,
        "journey": journey_type,
        "concurrency": concurrency,
        "duration_sec": round(total_time, 2),
        "total_requests": total_requests,
        "throughput_rps": round(throughput, 2),
        "success_count": total_requests - error_count,
        "error_count": error_count,
        "status_distribution": status_counts,
        "latency_ms": {
            "min": round(min_lat, 2),
            "mean": round(mean_lat, 2),
            "p50": round(p50, 2),
            "p95": round(p95, 2),
            "p99": round(p99, 2),
            "max": round(max_lat, 2),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="VibeConnect Performance Test Harness")
    parser.add_argument(
        "--target-url",
        default=os.environ.get("PERF_TARGET_URL", DEFAULT_LOCAL_TARGET),
        help=f"Target base URL (defaults to {DEFAULT_LOCAL_TARGET})",
    )
    parser.add_argument(
        "--allow-remote-target",
        action="store_true",
        help="Explicitly permit non-loopback URLs for isolated staging tests",
    )
    parser.add_argument("--user", default=os.environ.get("PERF_USER_EMAIL", "perf_member@vibeconnect.internal"), help="Synthetic test user email")
    parser.add_argument("--password", default=os.environ.get("PERF_USER_PASSWORD"), required=not os.environ.get("PERF_USER_PASSWORD"), help="Synthetic test user password")
    parser.add_argument("--output", default="perf_results.json", help="Path to write JSON results")
    parser.add_argument("--skip-soak", action="store_true", help="Skip the long/pilot soak phase")
    args = parser.parse_args()

    base_url = args.target_url.rstrip("/")

    # Remote target safety guard: prevent accidental execution against live or non-local endpoints
    parsed_target = urllib.parse.urlsplit(base_url)
    target_host = parsed_target.hostname or ""
    if target_host not in ("127.0.0.1", "localhost") and not args.allow_remote_target:
        print(
            f"SAFETY ABORT: Target '{base_url}' is not a local loopback address (127.0.0.1 / localhost).\n"
            "To test against an isolated staging environment, explicitly provide --allow-remote-target.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Pre-fetch context IDs
    init_sess = WorkerSession(base_url)
    init_sess.get_csrf()
    st, l_res = init_sess.login(args.user, args.password)
    if st != 200:
        print(f"Error logging in as {args.user}: HTTP {st}", file=sys.stderr)
        sys.exit(1)

    st, home_data = init_sess.get_tenant_home()
    if st != 200:
        print(f"Error fetching tenant home: HTTP {st}", file=sys.stderr)
        sys.exit(1)

    cached_ids = {
        "org_id": home_data["organization"]["id"],
        "product_id": home_data["products"][0]["id"],
    }
    init_sess.select_context("tenant", cached_ids["org_id"])
    print(f"Harness initialized against {base_url} with org={cached_ids['org_id']}")

    results = []

    # 1. Baseline
    print("\n--- RUNNING BASELINE (LOW CONCURRENCY) ---")
    res_live = run_benchmark("Baseline Liveness", base_url, "health_liveness", 2, 5, cached_ids, args.user, args.password)
    print(json.dumps(res_live, indent=2))
    results.append(res_live)

    res_ready = run_benchmark("Baseline Readiness (DB)", base_url, "health_readiness", 2, 5, cached_ids, args.user, args.password)
    print(json.dumps(res_ready, indent=2))
    results.append(res_ready)

    res_auth = run_benchmark("Baseline Auth Lifecycle (Bounded)", base_url, "auth_lifecycle", 2, 5, cached_ids, args.user, args.password, max_requests=4)
    print(json.dumps(res_auth, indent=2))
    results.append(res_auth)

    res_tenant = run_benchmark("Baseline Tenant Home", base_url, "tenant_context_and_home", 2, 8, cached_ids, args.user, args.password, session_template=init_sess)
    print(json.dumps(res_tenant, indent=2))
    results.append(res_tenant)

    res_sso = run_benchmark("Baseline SSO Launch (PKCE)", base_url, "sso_launch_pkce", 2, 8, cached_ids, args.user, args.password, session_template=init_sess)
    print(json.dumps(res_sso, indent=2))
    results.append(res_sso)

    # 2. Stress Ramp
    print("\n--- RUNNING STRESS RAMP ---")
    res_stress_5 = run_benchmark("Stress Ramp C=5 (Tenant Journey)", base_url, "tenant_context_and_home", 5, 10, cached_ids, args.user, args.password, session_template=init_sess)
    print(json.dumps(res_stress_5, indent=2))
    results.append(res_stress_5)

    res_stress_10 = run_benchmark("Stress Ramp C=10 (Tenant Journey)", base_url, "tenant_context_and_home", 10, 10, cached_ids, args.user, args.password, session_template=init_sess)
    print(json.dumps(res_stress_10, indent=2))
    results.append(res_stress_10)

    # 3. Soak Pilot
    if not args.skip_soak:
        print("\n--- RUNNING SOAK PILOT ---")
        res_soak = run_benchmark("Short Soak Pilot (Steady C=4)", base_url, "tenant_context_and_home", 4, 45, cached_ids, args.user, args.password, session_template=init_sess)
        print(json.dumps(res_soak, indent=2))
        results.append(res_soak)

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nAll tests completed. Output saved to {args.output}")


if __name__ == "__main__":
    main()
