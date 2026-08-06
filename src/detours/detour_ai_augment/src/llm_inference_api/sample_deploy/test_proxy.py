# test_proxy.py
#
# Usage:
#   pytest -q
#
# Assumptions:
# - Your module file is named proxy.py (same dir as this test),
#   importable as `import proxy as m`.
#
# Notes:
# - Network calls are fully mocked.
# - Tests cover helpers, tail JSON parsing, token extraction, SQLite schema/IO,
#   and DBWriter pricing + cost computation via a mocked provider.

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional
import threading
import socket
import http.client
from http.server import BaseHTTPRequestHandler

import pytest
from dotenv import load_dotenv

import proxy as m

load_dotenv()


# -------------------------
# Pure helper tests
# -------------------------

def test_utc_date_str_from_unix_ms_epoch():
    assert m.utc_date_str_from_unix_ms(0) == "1970-01-01"


def test_parse_pricing_slug_basic():
    assert m.parse_pricing_slug("openrouter/foo/bar") == ("openrouter", "foo/bar")
    assert m.parse_pricing_slug("OpenRouter/foo") == ("openrouter", "foo")


@pytest.mark.parametrize("bad", ["", "nope", "x/", "/y", " /y", "x/ "])
def test_parse_pricing_slug_invalid(bad):
    with pytest.raises(ValueError):
        m.parse_pricing_slug(bad)


def test_compute_cost_usd_happy_path():
    # prompt $2 / 1M tokens => 2e-6 per token
    # completion $3 / 1M => 3e-6 per token
    cost = m.compute_cost_usd(100, 200, 2e-6, 3e-6)
    assert cost == pytest.approx(100 * 2e-6 + 200 * 3e-6)


@pytest.mark.parametrize(
    "args",
    [
        (None, 1, 1.0, 1.0),
        (1, None, 1.0, 1.0),
        (1, 1, None, 1.0),
        (1, 1, 1.0, None),
    ],
)
def test_compute_cost_usd_missing_returns_none(args):
    assert m.compute_cost_usd(*args) is None


def test_fmt_tokens():
    assert m.fmt_tokens(None) == "—"
    assert m.fmt_tokens(0) == "0"
    assert m.fmt_tokens(999) == "999"
    assert m.fmt_tokens(1000) == "1.00K"
    assert m.fmt_tokens(10_000) == "10.0K"
    assert m.fmt_tokens(100_000) == "100K"
    assert m.fmt_tokens(1_000_000) == "1.00M"


def test_fmt_usd():
    assert m.fmt_usd(None) == "—"
    assert m.fmt_usd(0) == "$0.000000"
    assert m.fmt_usd(0.0001234) == "$0.000123"
    assert m.fmt_usd(1.23456) == "$1.2346"
    assert m.fmt_usd(1234.5) == "$1,234.50"


def test_fmt_ms():
    assert m.fmt_ms(None) == "—"
    assert m.fmt_ms(5) == "5ms"
    assert m.fmt_ms(999) == "999ms"
    assert m.fmt_ms(1000) == "1s"
    assert m.fmt_ms(61_000) == "1m 1s"


# -------------------------
# Tail JSON parsing tests
# -------------------------

def test_parse_last_json_object_non_stream():
    b = b'{"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}'
    obj = m.parse_last_json_object_from_tail(b)
    assert isinstance(obj, dict)
    assert obj["usage"]["total_tokens"] == 3


def test_parse_last_json_object_sse_with_done_and_noise():
    s = "\n".join(
        [
            "data: {\"x\": 1}",
            "data: notjson",
            "",
            "data: {\"usage\": {\"prompt_tokens\": 5, \"completion_tokens\": 7}}",
            "data: [DONE]",
        ]
    ).encode("utf-8")
    obj = m.parse_last_json_object_from_tail(s)
    assert obj == {"usage": {"prompt_tokens": 5, "completion_tokens": 7}}


def test_parse_last_json_object_jsonl_picks_last_object():
    s = "\n".join(
        [
            "{\"a\": 1}",
            "{\"a\": 2}",
            "garbage",
            "{\"a\": 3, \"timings\": {\"prompt_ms\": 10}}",
        ]
    ).encode("utf-8")
    obj = m.parse_last_json_object_from_tail(s)
    assert obj["a"] == 3
    assert obj["timings"]["prompt_ms"] == 10


def test_parse_last_json_object_returns_none_when_no_json():
    assert m.parse_last_json_object_from_tail(b"hello\nworld\n") is None


# -------------------------
# Token/timing extraction tests
# -------------------------

def test_extract_tokens_and_timings_from_usage_and_timings():
    obj = {
        "usage": {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33},
        "timings": {"prompt_ms": 12.5, "predicted_ms": 34.0},
    }
    in_tok, out_tok, total_tok, prompt_ms, predicted_ms, timings = m.extract_tokens_and_timings(obj)
    assert (in_tok, out_tok, total_tok) == (11, 22, 33)
    assert prompt_ms == pytest.approx(12.5)
    assert predicted_ms == pytest.approx(34.0)
    assert timings == obj["timings"]


def test_extract_tokens_and_timings_llama_server_fields():
    obj = {"tokens_evaluated": 10, "tokens_predicted": 20}
    in_tok, out_tok, total_tok, prompt_ms, predicted_ms, timings = m.extract_tokens_and_timings(obj)
    assert (in_tok, out_tok, total_tok) == (10, 20, 30)
    assert prompt_ms is None
    assert predicted_ms is None
    assert timings is None


def test_extract_tokens_and_timings_ignores_bools_and_strings():
    obj = {"usage": {"prompt_tokens": True, "completion_tokens": "12"}}
    in_tok, out_tok, total_tok, *_ = m.extract_tokens_and_timings(obj)
    assert in_tok is None
    assert out_tok is None
    assert total_tok is None


# -------------------------
# SQLite schema + DB ops
# -------------------------

def test_db_connect_creates_schema(tmp_path):
    db = tmp_path / "t.sqlite"
    conn = m.db_connect(str(db))
    # schema exists
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "requests" in tables
    assert "pricing_daily" in tables
    # new columns exist
    cols = {r[1] for r in conn.execute("PRAGMA table_info(requests)").fetchall()}
    assert "response_id" in cols
    assert "system_fingerprint" in cols
    conn.close()


# -------------------------
# DBWriter integration tests
# -------------------------

def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_dbwriter_inserts_request_without_pricing(tmp_path):
    db = tmp_path / "usage.sqlite"

    w = m.DBWriter(
        db_path=str(db),
        pricing_slug=None,                 # no pricing fetch
        openrouter_api_key=None,
        batch_n=1,
        batch_ms=10_000,
    )
    w.start()

    ev = m.LogEvent(
        ts_start_unix_ms=1,
        ts_end_unix_ms=2,
        model_alias="x",
        pricing_slug=None,
        method="POST",
        path="/completion",
        status=200,
        proc_ms=123,
        in_tokens=10,
        out_tokens=20,
        total_tokens=30,
        prompt_ms=1.5,
        predicted_ms=2.5,
        timings={"prompt_ms": 1.5, "predicted_ms": 2.5},
        response_id=None,
        system_fingerprint=None,
    )
    w.submit(ev)
    w.stop()
    w.join(timeout=5)

    conn = sqlite3.connect(str(db))
    assert _count_rows(conn, "requests") == 1
    row = conn.execute(
        "SELECT model_alias, path, in_tokens, out_tokens, total_tokens, cost_usd, timings_json, response_id, system_fingerprint "
        "FROM requests"
    ).fetchone()
    assert row[0] == "x"
    assert row[1] == "/completion"
    assert row[2:5] == (10, 20, 30)
    assert row[5] is None  # no pricing -> no cost
    assert json.loads(row[6]) == {"prompt_ms": 1.5, "predicted_ms": 2.5}
    assert row[7] is None
    assert row[8] is None
    conn.close()


@dataclass(frozen=True)
class _DummyQuote:
    provider: str
    provider_id: str
    currency: str
    prompt_usd_per_token: float
    completion_usd_per_token: float
    raw_json: dict


class _DummyProvider(m.PricingProvider):
    def __init__(self, quote: m.PriceQuote):
        self._quote = quote
        self.calls = 0

    def fetch_quote(self, provider_id: str) -> m.PriceQuote:
        self.calls += 1
        # keep provider_id consistent with call
        return m.PriceQuote(
            provider=self._quote.provider,
            provider_id=provider_id,
            currency=self._quote.currency,
            prompt_usd_per_token=self._quote.prompt_usd_per_token,
            completion_usd_per_token=self._quote.completion_usd_per_token,
            raw_json=self._quote.raw_json,
        )


def test_dbwriter_pricing_fetch_cached_and_cost_computed(tmp_path, monkeypatch):
    db = tmp_path / "usage.sqlite"

    # Make DBWriter think provider_for returns our dummy provider.
    quote = m.PriceQuote(
        provider="dummy",
        provider_id="anything",
        currency="USD",
        prompt_usd_per_token=2e-6,       # $2 / 1M
        completion_usd_per_token=3e-6,   # $3 / 1M
        raw_json={"ok": True},
    )
    dummy_provider = _DummyProvider(quote)

    def _provider_for(pricing_slug: str, openrouter_api_key: Optional[str]):
        provider, provider_id = m.parse_pricing_slug(pricing_slug)
        assert provider == "openrouter"  # just to ensure slug parsing path is used
        return dummy_provider, provider, provider_id

    monkeypatch.setattr(m, "provider_for", _provider_for)

    w = m.DBWriter(
        db_path=str(db),
        pricing_slug=None,  # disable startup prefetch; events still carry pricing_slug
        openrouter_api_key=None,
        batch_n=1,
        batch_ms=10_000,
    )
    w.start()

    # Two events same UTC date -> should fetch once, then reuse cached pricing (DB + in-mem cache)
    ev1 = m.LogEvent(
        ts_start_unix_ms=1,
        ts_end_unix_ms=1_700_000_000_000,  # deterministic-ish date in UTC
        model_alias="x",
        pricing_slug="openrouter/test-model",
        method="POST",
        path="/v1/chat/completions",
        status=200,
        proc_ms=10,
        in_tokens=100,
        out_tokens=200,
        total_tokens=300,
        prompt_ms=None,
        predicted_ms=None,
        timings=None,
        response_id=None,
        system_fingerprint=None,
    )
    ev2 = m.LogEvent(
        ts_start_unix_ms=2,
        ts_end_unix_ms=1_700_000_000_100,
        model_alias="x",
        pricing_slug="openrouter/test-model",
        method="POST",
        path="/completion",
        status=200,
        proc_ms=11,
        in_tokens=1,
        out_tokens=2,
        total_tokens=3,
        prompt_ms=None,
        predicted_ms=None,
        timings=None,
        response_id=None,
        system_fingerprint=None,
    )

    w.submit(ev1)
    w.submit(ev2)
    w.stop()
    w.join(timeout=5)

    # provider should have been called only once for that date
    assert dummy_provider.calls == 1

    conn = sqlite3.connect(str(db))
    assert _count_rows(conn, "requests") == 2
    assert _count_rows(conn, "pricing_daily") == 1

    costs = [r[0] for r in conn.execute("SELECT cost_usd FROM requests ORDER BY id").fetchall()]
    assert costs[0] == pytest.approx(100 * 2e-6 + 200 * 3e-6)
    assert costs[1] == pytest.approx(1 * 2e-6 + 2 * 3e-6)

    # pricing stored
    p = conn.execute(
        "SELECT prompt_usd_per_token, completion_usd_per_token FROM pricing_daily"
    ).fetchone()
    assert p[0] == pytest.approx(2e-6)
    assert p[1] == pytest.approx(3e-6)
    conn.close()


def test_dbwriter_handles_bad_event_without_crashing(tmp_path):
    # Ensures salvage path doesn’t explode if timings_json is not serializable, etc.
    db = tmp_path / "usage.sqlite"
    w = m.DBWriter(
        db_path=str(db),
        pricing_slug=None,
        openrouter_api_key=None,
        batch_n=1,
        batch_ms=10_000,
    )
    w.start()

    class _Weird:
        pass

    ev = m.LogEvent(
        ts_start_unix_ms=1,
        ts_end_unix_ms=2,
        model_alias="x",
        pricing_slug=None,
        method="GET",
        path="/",
        status=200,
        proc_ms=1,
        in_tokens=None,
        out_tokens=None,
        total_tokens=None,
        prompt_ms=None,
        predicted_ms=None,
        timings=_Weird(),  # not a dict -> should store NULL timings_json
        response_id=None,
        system_fingerprint=None,
    )
    w.submit(ev)
    w.stop()
    w.join(timeout=5)

    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT timings_json FROM requests").fetchone()
    assert row[0] is None
    conn.close()


def test_dbwriter_pricing_fallback_to_prior_date_when_fetch_fails(tmp_path, monkeypatch, capsys):
    db = tmp_path / "usage.sqlite"

    # Create schema + seed a prior-day cached price (Jan 3) for the same slug.
    conn = m.db_connect(str(db))
    slug = "openrouter/test-model"
    conn.execute(
        m.INSERT_PRICING_SQL,
        (
            slug,
            "openrouter",
            "test-model",
            "2026-01-03",
            "USD",
            2e-6,  # prompt_usd_per_token
            3e-6,  # completion_usd_per_token
            0,
            "{}",
        ),
    )
    conn.close()

    # Monkeypatch provider_for so any fetch attempt fails.
    class _FailProvider(m.PricingProvider):
        def fetch_quote(self, provider_id: str) -> m.PriceQuote:
            raise RuntimeError("network down")

    def _provider_for(pricing_slug: str, openrouter_api_key: Optional[str]):
        provider, provider_id = m.parse_pricing_slug(pricing_slug)
        return _FailProvider(), provider, provider_id

    monkeypatch.setattr(m, "provider_for", _provider_for)

    # Call _get_or_fetch_pricing for Jan 4: should fallback to Jan 3 row.
    w = m.DBWriter(
        db_path=str(db),
        pricing_slug=slug,
        openrouter_api_key=None,
        batch_n=1,
        batch_ms=10_000,
    )
    conn = sqlite3.connect(str(db), timeout=30, isolation_level=None)
    prices = w._get_or_fetch_pricing(conn, slug, "2026-01-04")
    conn.close()

    assert prices == pytest.approx((2e-6, 3e-6))

    out = capsys.readouterr().out
    assert "failed to fetch" in out
    assert "using cached 2026-01-03" in out


# -------------------------
# Optional: OpenRouterPricingProvider parsing (no real network)
# -------------------------

def test_openrouter_provider_fetch_quote_parses_pricing(monkeypatch):
    # Mock urllib.request.urlopen to return a fake models payload
    payload = {
        "data": [
            {"id": "a", "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
            {"id": "target", "canonical_slug": "target", "pricing": {"prompt": 0.000003, "completion": 0.000004}},
        ]
    }

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def read(self): return json.dumps(payload).encode("utf-8")

    def _urlopen(req, timeout=0):
        return _Resp()

    monkeypatch.setattr(m.urllib.request, "urlopen", _urlopen)

    prov = m.OpenRouterPricingProvider(api_key="k", timeout_s=1.0)
    q = prov.fetch_quote("target")
    assert q.provider == "openrouter"
    assert q.provider_id == "target"
    assert q.currency == "USD"
    assert q.prompt_usd_per_token == pytest.approx(0.000003)
    assert q.completion_usd_per_token == pytest.approx(0.000004)
    assert isinstance(q.raw_json, dict)


def test_openrouter_provider_prefers_paid_over_free_when_slug_matches(monkeypatch):
    payload = {
        "data": [
            # Free variant appears first (this is what was breaking you)
            {
                "id": "google/gemma-3-12b-it:free",
                "canonical_slug": "google/gemma-3-12b-it",
                "pricing": {"prompt": "0", "completion": "0"},
            },
            # Paid variant
            {
                "id": "google/gemma-3-12b-it",
                "canonical_slug": "google/gemma-3-12b-it",
                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
            },
        ]
    }

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def read(self): return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(m.urllib.request, "urlopen", lambda req, timeout=0: _Resp())

    prov = m.OpenRouterPricingProvider(api_key="k", timeout_s=1.0)

    # Call using canonical slug (this is your PRICING_SLUG provider_id)
    q = prov.fetch_quote("google/gemma-3-12b-it")

    # Should pick paid variant, not :free
    assert q.provider_id == "google/gemma-3-12b-it"
    assert q.prompt_usd_per_token == pytest.approx(0.000001)
    assert q.completion_usd_per_token == pytest.approx(0.000002)
    assert q.raw_json["id"] == "google/gemma-3-12b-it"


def test_openrouter_provider_exact_id_match_wins(monkeypatch):
    payload = {
        "data": [
            {
                "id": "x:free",
                "canonical_slug": "x",
                "pricing": {"prompt": "0", "completion": "0"},
            },
            {
                "id": "x",
                "canonical_slug": "x",
                "pricing": {"prompt": "0.000003", "completion": "0.000004"},
            },
        ]
    }

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def read(self): return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(m.urllib.request, "urlopen", lambda req, timeout=0: _Resp())

    prov = m.OpenRouterPricingProvider(api_key="k", timeout_s=1.0)

    q = prov.fetch_quote("x:free")
    assert q.provider_id == "x:free"
    assert q.prompt_usd_per_token == pytest.approx(0.0)
    assert q.completion_usd_per_token == pytest.approx(0.0)


# -------------------------
# Optional: LocalHostPricingProvider parsing
# -------------------------

def test_localhost_pricing_provider_parses_1m_rates():
    prov = m.LocalHostPricingProvider()
    q = prov.fetch_quote("0.04/0.06")
    assert q.provider == "localhost"
    assert q.currency == "USD"
    assert q.prompt_usd_per_token == pytest.approx(0.04 / 1_000_000.0)
    assert q.completion_usd_per_token == pytest.approx(0.06 / 1_000_000.0)

def test_provider_for_localhost():
    prov, provider, provider_id = m.provider_for("localhost/0.04/0.04", None)
    assert provider == "localhost"
    assert provider_id == "0.04/0.04"
    assert isinstance(prov, m.LocalHostPricingProvider)


# -------------------------
# Staging: slow / integration / real-network tests
# -------------------------

def _start_server(server):
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return t


def _stop_server(server):
    try:
        server.shutdown()
    except Exception:
        pass
    try:
        server.server_close()
    except Exception:
        pass


class _BackendHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "fake-backend/0.1"

    def log_message(self, fmt, *args):
        return

    def do_POST(self):
        # Non-streaming endpoint returns a single JSON object
        if self.path == "/completion":
            body = json.dumps({
                "id": "cmpl-1",
                "system_fingerprint": "fp-1",
                "tokens_evaluated": 10,
                "tokens_predicted": 20
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Streaming endpoint: chunked SSE ending with a final usage object
        if self.path == "/v1/chat/completions":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def send_chunk(b: bytes):
                self.wfile.write(f"{len(b):X}\r\n".encode("ascii"))
                self.wfile.write(b)
                self.wfile.write(b"\r\n")
                self.wfile.flush()

            send_chunk(b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n')
            send_chunk(b'data: {"id":"chatcmpl-1","system_fingerprint":"fp-2","usage":{"prompt_tokens":5,"completion_tokens":7,"total_tokens":12}}\n\n')
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            return

        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _start_backend():
    backend = m.ThreadingHTTPServer(("127.0.0.1", 0), _BackendHandler)  # port 0 => OS picks free port
    _start_server(backend)
    backend_port = backend.server_address[1]
    return backend, backend_port


def _start_proxy(db_path, backend_port: int):
    # Important: do NOT call m.serve() here (it installs signal handlers; fails in threads).
    cfg = m.ProxyConfig(
        proxy_host="127.0.0.1",
        proxy_port=0,  # unused here; we bind explicitly below
        backend_host="127.0.0.1",
        backend_port=backend_port,
        model_alias="m1",
        pricing_slug="localhost/0.04/0.04",
        inject_oai_stream_usage=False,
        db_path=str(db_path),
        openrouter_api_key=None,
    )

    writer = m.DBWriter(
        db_path=str(db_path),
        pricing_slug=None,  # disable startup prefetch to keep tests deterministic
        openrouter_api_key=None,
        batch_n=1,
        batch_ms=10_000,
    )
    writer.start()

    Handler = m.build_handler(cfg, writer)
    proxy = m.ThreadingHTTPServer(("127.0.0.1", 0), Handler)  # port 0 => OS picks free port
    _start_server(proxy)
    proxy_port = proxy.server_address[1]

    return cfg, writer, proxy, proxy_port


def _stop_proxy(writer: m.DBWriter, proxy):
    _stop_server(proxy)
    try:
        writer.stop()
    except Exception:
        pass
    writer.join(timeout=2)


@pytest.mark.staging
def test_proxy_end_to_end_non_stream_logs_and_persists(tmp_path):
    db = tmp_path / "usage.sqlite"

    backend, backend_port = _start_backend()
    cfg, writer, proxy, proxy_port = _start_proxy(db, backend_port)
    time.sleep(0.05)

    conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=5)
    conn.request("POST", "/completion", body=b"{}", headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()

    assert resp.status == 200
    resp_js = json.loads(body.decode("utf-8"))
    assert resp_js["tokens_evaluated"] == 10
    assert resp_js["tokens_predicted"] == 20
    assert resp_js["id"] == "cmpl-1"
    assert resp_js["system_fingerprint"] == "fp-1"

    time.sleep(0.15)  # allow DBWriter flush

    c = sqlite3.connect(str(db))
    row = c.execute(
        "SELECT in_tokens, out_tokens, total_tokens, cost_usd, path, response_id, system_fingerprint "
        "FROM requests ORDER BY id DESC LIMIT 1"
    ).fetchone()
    c.close()

    assert row[4] == "/completion"
    assert row[0] == 10
    assert row[1] == 20
    assert row[2] == 30
    assert row[3] is not None  # localhost pricing => cost computed
    assert row[5] == "cmpl-1"
    assert row[6] == "fp-1"

    _stop_proxy(writer, proxy)
    _stop_server(backend)


@pytest.mark.staging
def test_proxy_end_to_end_streaming_chunked_extracts_usage(tmp_path):
    db = tmp_path / "usage.sqlite"

    backend, backend_port = _start_backend()
    cfg, writer, proxy, proxy_port = _start_proxy(db, backend_port)
    time.sleep(0.05)

    conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=5)
    conn.request(
        "POST",
        "/v1/chat/completions",
        body=b'{"stream":true}',
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    data = resp.read()
    conn.close()

    assert resp.status == 200
    assert b"data:" in data  # got SSE back

    time.sleep(0.15)

    c = sqlite3.connect(str(db))
    row = c.execute(
        "SELECT in_tokens, out_tokens, total_tokens, path, response_id, system_fingerprint "
        "FROM requests ORDER BY id DESC LIMIT 1"
    ).fetchone()
    c.close()

    assert row[3] == "/v1/chat/completions"
    assert row[0] == 5
    assert row[1] == 7
    assert row[2] == 12
    assert row[4] == "chatcmpl-1"
    assert row[5] == "fp-2"

    _stop_proxy(writer, proxy)
    _stop_server(backend)


@pytest.mark.staging
def test_proxy_concurrency_many_requests(tmp_path):
    db = tmp_path / "usage.sqlite"

    backend, backend_port = _start_backend()
    cfg, writer, proxy, proxy_port = _start_proxy(db, backend_port)
    time.sleep(0.05)

    N = 50
    errs = []

    def worker():
        try:
            conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=5)
            conn.request("POST", "/completion", body=b"{}", headers={"Content-Type": "application/json"})
            r = conn.getresponse()
            _ = r.read()
            conn.close()
            if r.status != 200:
                errs.append(("status", r.status))
        except Exception as e:
            errs.append(("exc", repr(e)))

    threads = [threading.Thread(target=worker) for _ in range(N)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert not errs

    time.sleep(0.25)

    c = sqlite3.connect(str(db))
    cnt = c.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    c.close()

    assert cnt >= N

    _stop_proxy(writer, proxy)
    _stop_server(backend)


@pytest.mark.staging
def test_openrouter_real_fetch_quote_optional():
    """
    Optional “API drift” check. Requires OPENROUTER_API_KEY and a real model id.
    Run with: pytest -m staging
    """
    import os

    api_key = os.environ.get("OPENROUTER_API_KEY")
    model_id = os.environ.get("OPENROUTER_TEST_MODEL_ID")  # e.g. "openai/gpt-4o-mini"
    if not api_key or not model_id:
        pytest.skip("set OPENROUTER_API_KEY and OPENROUTER_TEST_MODEL_ID to run")

    prov = m.OpenRouterPricingProvider(api_key=api_key, timeout_s=10.0)
    q = prov.fetch_quote(model_id)
    assert q.currency == "USD"
    assert q.prompt_usd_per_token >= 0.0
    assert q.completion_usd_per_token >= 0.0


# -------------------------
# Chaos: failure-injection / resilience tests
# -------------------------

class _ChaosBackendHandler(BaseHTTPRequestHandler):
    """
    Sends partial streaming response then crashes connection.
    """

    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        return

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def send_chunk(b: bytes):
            self.wfile.write(f"{len(b):X}\r\n".encode("ascii"))
            self.wfile.write(b)
            self.wfile.write(b"\r\n")
            self.wfile.flush()

        # send partial stream
        send_chunk(b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n')

        # simulate backend crash mid-stream
        try:
            self.connection.shutdown(2)
        except Exception:
            pass
        self.connection.close()


def _start_chaos_backend():
    backend = m.ThreadingHTTPServer(("127.0.0.1", 0), _ChaosBackendHandler)
    t = threading.Thread(target=backend.serve_forever, daemon=True)
    t.start()
    return backend, backend.server_address[1]


@pytest.mark.chaos
@pytest.mark.parametrize("i", range(10))
def test_backend_disconnect_mid_stream_logged_safely(tmp_path, i):
    """
    Backend dies during streaming response.

    Expectations:
    - proxy does NOT hang
    - client connection ends
    - request still logged
    - DB remains valid
    """

    db = tmp_path / f"usage_{i}.sqlite"

    # start chaos backend
    backend, backend_port = _start_chaos_backend()

    # start proxy (same helper style as staging tests)
    cfg = m.ProxyConfig(
        proxy_host="127.0.0.1",
        proxy_port=0,
        backend_host="127.0.0.1",
        backend_port=backend_port,
        model_alias="chaos",
        pricing_slug="localhost/0.04/0.04",
        inject_oai_stream_usage=False,
        db_path=str(db),
        openrouter_api_key=None,
    )

    writer = m.DBWriter(
        db_path=str(db),
        pricing_slug=None,
        openrouter_api_key=None,
        batch_n=1,
        batch_ms=10_000,
    )
    writer.start()

    Handler = m.build_handler(cfg, writer)
    proxy = m.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    proxy_port = proxy.server_address[1]

    time.sleep(0.05)

    # client request (should terminate early, not hang)
    conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=5)
    conn.request(
        "POST",
        "/v1/chat/completions",
        body=b'{"stream":true}',
        headers={"Content-Type": "application/json"},
    )

    resp = conn.getresponse()

    # read whatever arrives; must not block forever
    try:
        _ = resp.read()
    except Exception:
        pass

    conn.close()

    # allow logging flush
    time.sleep(0.2)

    # verify DB is still healthy and request recorded
    c = sqlite3.connect(str(db))
    rows = c.execute("SELECT COUNT(*), path FROM requests").fetchone()
    c.close()

    assert rows[0] == 1
    assert rows[1] == "/v1/chat/completions"

    # cleanup
    proxy.shutdown()
    proxy.server_close()
    writer.stop()
    writer.join(timeout=2)

    backend.shutdown()
    backend.server_close()
