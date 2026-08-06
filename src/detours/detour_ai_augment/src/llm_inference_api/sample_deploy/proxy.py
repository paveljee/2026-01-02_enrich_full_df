#!/usr/bin/env python3
"""
llama_proxy_sqlite.py

Reverse proxy for llama-server that:
- Forwards all HTTP requests to a backend llama-server.
- Logs per-request tokens/timings EXACTLY as returned by llama-server:
  - /completion: tokens_evaluated / tokens_predicted (+ timings if present)
  - /v1/chat/completions: usage.prompt_tokens / usage.completion_tokens (+ timings if present)
  - stream + non-stream: parses last JSON object from body or SSE tail
- Computes and stores:
  - proc_ms (wall time measured by proxy)
  - prompt_ms / predicted_ms (verbatim from server timings when present)
- Stores everything in SQLite (WAL), with batched INSERTs to minimize I/O.
- Daily pricing cache keyed by (pricing_slug, date_utc). Currently supports:
  - pricing_slug="openrouter/<model_id>"
  Uses OpenRouter /api/v1/models to fetch pricing.prompt & pricing.completion.
- Includes "summary" command.

Env vars (or CLI flags) used by `serve`:
  DB_PATH, PROXY_HOST, PROXY_PORT, BACKEND_HOST, BACKEND_PORT, MODEL_ALIAS,
  PRICING_SLUG, OPENROUTER_API_KEY, INJECT_OAI_STREAM_USAGE,
  SQLITE_BATCH_N, SQLITE_BATCH_MS
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import http.client
import json
import os
import queue
import re
import signal
import sqlite3
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple
import socketserver

# -------------------------
# Pure helpers (pytest-friendly)
# -------------------------

def utc_date_str_from_unix_ms(unix_ms: int) -> str:
    dt = _dt.datetime.fromtimestamp(unix_ms / 1000.0, tz=_dt.timezone.utc)
    return dt.date().isoformat()


def parse_pricing_slug(pricing_slug: str) -> Tuple[str, str]:
    if not pricing_slug or "/" not in pricing_slug:
        raise ValueError(f"Invalid pricing_slug: {pricing_slug!r}")
    provider, rest = pricing_slug.split("/", 1)
    provider = provider.strip()
    rest = rest.strip()
    if not provider or not rest:
        raise ValueError(f"Invalid pricing_slug: {pricing_slug!r}")
    return provider.lower(), rest


def compute_cost_usd(
    in_tokens: Optional[int],
    out_tokens: Optional[int],
    prompt_usd_per_token: Optional[float],
    completion_usd_per_token: Optional[float],
) -> Optional[float]:
    if in_tokens is None or out_tokens is None:
        return None
    if prompt_usd_per_token is None or completion_usd_per_token is None:
        return None
    return (in_tokens * prompt_usd_per_token) + (out_tokens * completion_usd_per_token)


def fmt_tokens(n: Optional[float]) -> str:
    if n is None:
        return "—"
    n = float(n)
    if n < 1000:
        return f"{int(n):d}"
    units = [("K", 1e3), ("M", 1e6), ("B", 1e9), ("T", 1e12), ("P", 1e15)]
    for suf, u in reversed(units):
        if n >= u:
            v = n / u
            if v < 10:
                return f"{v:.2f}{suf}"
            if v < 100:
                return f"{v:.1f}{suf}"
            return f"{v:.0f}{suf}"
    return f"{int(n):d}"


def fmt_usd(x: Optional[float]) -> str:
    if x is None:
        return "—"
    if x >= 1000:
        return f"${x:,.2f}"
    if x >= 1:
        return f"${x:.4f}"
    return f"${x:.6f}"


def fmt_ms(ms: Optional[float]) -> str:
    if ms is None:
        return "—"
    ms = float(ms)
    if ms < 1000:
        return f"{ms:.0f}ms"
    s = ms / 1000.0
    w = int(s // 604800); s -= w * 604800
    d = int(s // 86400);  s -= d * 86400
    h = int(s // 3600);   s -= h * 3600
    m = int(s // 60);     s -= m * 60
    sec = int(round(s))
    parts = []
    if w: parts.append(f"{w}w")
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if sec or not parts: parts.append(f"{sec}s")
    return " ".join(parts)


_JSON_LINE_RE = re.compile(r"^\s*\{.*\}\s*$")


def parse_last_json_object_from_tail(tail_bytes: bytes) -> Optional[dict]:
    txt = tail_bytes.decode("utf-8", "replace")

    # non-stream JSON
    try:
        obj = json.loads(txt)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # SSE / JSONL tail scan
    last_obj = None
    for raw_line in txt.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
            if not line or line == "[DONE]":
                continue
        if not _JSON_LINE_RE.match(line):
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                last_obj = obj
        except Exception:
            continue
    return last_obj


def extract_tokens_and_timings(obj: dict) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[float], Optional[float], Optional[dict]]:
    in_tok = out_tok = total_tok = None
    prompt_ms = predicted_ms = None
    timings = obj.get("timings") if isinstance(obj.get("timings"), dict) else None

    usage = obj.get("usage")
    if isinstance(usage, dict):
        in_tok = usage.get("prompt_tokens")
        out_tok = usage.get("completion_tokens")
        total_tok = usage.get("total_tokens")

    if in_tok is None and "tokens_evaluated" in obj:
        in_tok = obj.get("tokens_evaluated")
    if out_tok is None and "tokens_predicted" in obj:
        out_tok = obj.get("tokens_predicted")
    if total_tok is None and isinstance(in_tok, (int, float)) and isinstance(out_tok, (int, float)):
        total_tok = int(in_tok) + int(out_tok)

    if timings:
        prompt_ms = timings.get("prompt_ms")
        predicted_ms = timings.get("predicted_ms")

    def _to_int(x) -> Optional[int]:
        if x is None or isinstance(x, bool):
            return None
        if isinstance(x, (int, float)):
            return int(x)
        return None

    return _to_int(in_tok), _to_int(out_tok), _to_int(total_tok), (float(prompt_ms) if prompt_ms is not None else None), (float(predicted_ms) if predicted_ms is not None else None), timings


# -------------------------
# Pricing providers
# -------------------------

@dataclasses.dataclass(frozen=True)
class PriceQuote:
    provider: str
    provider_id: str
    currency: str
    prompt_usd_per_token: float
    completion_usd_per_token: float
    raw_json: dict


class PricingProvider:
    def fetch_quote(self, provider_id: str) -> PriceQuote:
        raise NotImplementedError


class OpenRouterPricingProvider(PricingProvider):
    MODELS_URL = "https://openrouter.ai/api/v1/models"

    def __init__(self, api_key: Optional[str] = None, timeout_s: float = 10.0):
        self.api_key = api_key
        self.timeout_s = timeout_s

    def fetch_quote(self, provider_id: str) -> PriceQuote:
        req = urllib.request.Request(self.MODELS_URL, method="GET")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            js = json.loads(resp.read().decode("utf-8"))

        models = js.get("data") or []

        # 1) Prefer exact id match
        target = next((m for m in models if isinstance(m, dict) and m.get("id") == provider_id), None)

        # 2) If provider_id is a canonical_slug, choose the best candidate (prefer non-:free, then non-zero pricing)
        if target is None:
            cands = [m for m in models if isinstance(m, dict) and m.get("canonical_slug") == provider_id]
            if not cands:
                raise KeyError(f"OpenRouter model not found: {provider_id}")

            def _rank(m: dict):
                mid = (m.get("id") or "")
                pr = (m.get("pricing") or {})
                p = float(pr.get("prompt") or 0.0)
                c = float(pr.get("completion") or 0.0)
                is_free_id = mid.endswith(":free")
                is_zero_price = (p == 0.0 and c == 0.0)
                return (is_free_id, is_zero_price)  # False sorts before True

            target = sorted(cands, key=_rank)[0]

        if target is None:
            raise KeyError(f"OpenRouter model not found: {provider_id}")

        pricing = target.get("pricing") or {}
        prompt = float(pricing.get("prompt") or 0.0)
        completion = float(pricing.get("completion") or 0.0)

        return PriceQuote(
            provider="openrouter",
            provider_id=(target.get("id") or provider_id),
            currency="USD",
            prompt_usd_per_token=prompt,
            completion_usd_per_token=completion,
            raw_json=target,
        )


class LocalHostPricingProvider(PricingProvider):
    # provider_id format: "<in_usd_per_1m>/<out_usd_per_1m>"
    def fetch_quote(self, provider_id: str) -> PriceQuote:
        a, b = provider_id.split("/", 1)
        in_per_1m = float(a)
        out_per_1m = float(b)

        return PriceQuote(
            provider="localhost",
            provider_id=provider_id,
            currency="USD",
            prompt_usd_per_token=in_per_1m / 1_000_000.0,
            completion_usd_per_token=out_per_1m / 1_000_000.0,
            raw_json={"prompt_usd_per_1m": in_per_1m, "completion_usd_per_1m": out_per_1m},
        )


def provider_for(pricing_slug: str, openrouter_api_key: Optional[str]) -> Tuple[PricingProvider, str, str]:
    provider, provider_id = parse_pricing_slug(pricing_slug)

    if provider == "openrouter":
        return OpenRouterPricingProvider(api_key=openrouter_api_key), provider, provider_id

    if provider == "localhost":
        # pricing_slug example: "localhost/0.04/0.04" (USD per 1M tokens)
        return LocalHostPricingProvider(), provider, provider_id

    raise ValueError(f"Unsupported pricing provider prefix: {provider!r}")


# -------------------------
# SQLite schema + DB ops
# -------------------------

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;

CREATE TABLE IF NOT EXISTS pricing_daily (
  pricing_slug TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  date_utc TEXT NOT NULL,
  currency TEXT NOT NULL,
  prompt_usd_per_token REAL NOT NULL,
  completion_usd_per_token REAL NOT NULL,
  fetched_at_unix_ms INTEGER NOT NULL,
  raw_json TEXT NOT NULL,
  PRIMARY KEY (pricing_slug, date_utc)
);

CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_start_unix_ms INTEGER NOT NULL,
  ts_end_unix_ms INTEGER NOT NULL,
  date_utc TEXT NOT NULL,

  model_alias TEXT NOT NULL,
  pricing_slug TEXT,

  method TEXT NOT NULL,
  path TEXT NOT NULL,
  status INTEGER NOT NULL,

  in_tokens INTEGER,
  out_tokens INTEGER,
  total_tokens INTEGER,

  proc_ms INTEGER NOT NULL,
  prompt_ms REAL,
  predicted_ms REAL,

  prompt_usd_per_token REAL,
  completion_usd_per_token REAL,
  cost_usd REAL,

  timings_json TEXT,
  response_id TEXT,
  system_fingerprint TEXT
);

CREATE INDEX IF NOT EXISTS idx_requests_date ON requests(date_utc);
CREATE INDEX IF NOT EXISTS idx_requests_model_date ON requests(model_alias, date_utc);
CREATE INDEX IF NOT EXISTS idx_requests_path_date ON requests(path, date_utc);
"""

INSERT_REQUEST_SQL = (
    "INSERT INTO requests ("
    "ts_start_unix_ms, ts_end_unix_ms, date_utc, model_alias, pricing_slug, "
    "method, path, status, "
    "in_tokens, out_tokens, total_tokens, "
    "proc_ms, prompt_ms, predicted_ms, "
    "prompt_usd_per_token, completion_usd_per_token, cost_usd, timings_json, "
    "response_id, system_fingerprint"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

INSERT_PRICING_SQL = (
    "INSERT OR IGNORE INTO pricing_daily "
    "(pricing_slug, provider, provider_id, date_utc, currency, prompt_usd_per_token, completion_usd_per_token, fetched_at_unix_ms, raw_json) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

SELECT_PRICING_SQL = (
    "SELECT provider, provider_id, currency, prompt_usd_per_token, completion_usd_per_token "
    "FROM pricing_daily WHERE pricing_slug=? AND date_utc=?"
)


SELECT_PRICING_FALLBACK_SQL = (
    "SELECT provider, provider_id, currency, prompt_usd_per_token, completion_usd_per_token, date_utc "
    "FROM pricing_daily WHERE pricing_slug=? AND date_utc<=? "
    "ORDER BY date_utc DESC LIMIT 1"
)


def db_connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)  # autocommit; we manage BEGIN/COMMIT
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.executescript(SCHEMA_SQL)
    return conn


# -------------------------
# DB Writer (batched commits)
# -------------------------

@dataclasses.dataclass
class LogEvent:
    ts_start_unix_ms: int
    ts_end_unix_ms: int
    model_alias: str
    pricing_slug: Optional[str]
    method: str
    path: str
    status: int
    proc_ms: int
    in_tokens: Optional[int]
    out_tokens: Optional[int]
    total_tokens: Optional[int]
    prompt_ms: Optional[float]
    predicted_ms: Optional[float]
    timings: Optional[dict]
    response_id: Optional[str]
    system_fingerprint: Optional[str]


class DBWriter(threading.Thread):
    def __init__(
        self,
        db_path: str,
        pricing_slug: Optional[str],
        openrouter_api_key: Optional[str],
        batch_n: int,
        batch_ms: int,
    ):
        super().__init__(daemon=True)
        self.db_path = db_path
        self.pricing_slug = pricing_slug
        self.openrouter_api_key = openrouter_api_key
        self.batch_n = max(1, batch_n)
        self.batch_s = max(0.01, batch_ms / 1000.0)

        self.q: "queue.Queue[Optional[LogEvent]]" = queue.Queue()
        self._stop_event = threading.Event()

        # in-memory cache: (pricing_slug, date_utc) -> (prompt_usd_per_token, completion_usd_per_token)
        self._price_cache: Dict[Tuple[str, str], Tuple[float, float]] = {}

    def stop(self) -> None:
        self._stop_event.set()
        self.q.put(None)

    def submit(self, ev: LogEvent) -> None:
        self.q.put(ev)

    def _get_or_fetch_pricing(
        self,
        conn: sqlite3.Connection,
        pricing_slug: str,
        date_utc: str,
    ) -> Optional[Tuple[float, float]]:
        key = (pricing_slug, date_utc)
        if key in self._price_cache:
            return self._price_cache[key]

        # 1) exact match for that date
        row = conn.execute(SELECT_PRICING_SQL, (pricing_slug, date_utc)).fetchone()
        if row:
            _provider, _provider_id, _currency, p, c = row
            self._price_cache[key] = (float(p), float(c))
            return self._price_cache[key]

        # 2) try to fetch fresh quote
        try:
            provider_obj, _pname, provider_id = provider_for(pricing_slug, self.openrouter_api_key)
            quote = provider_obj.fetch_quote(provider_id)
        except Exception as e:
            # 3) fallback to most recent cached date <= requested date
            try:
                fb = conn.execute(SELECT_PRICING_FALLBACK_SQL, (pricing_slug, date_utc)).fetchone()
            except Exception:
                fb = None

            if fb:
                _provider, _provider_id, _currency, p, c, fb_date = fb
                try:
                    self._log(f"failed to fetch {pricing_slug} for {date_utc} ({e}); using cached {fb_date}")
                except Exception:
                    pass
                self._price_cache[key] = (float(p), float(c))
                return self._price_cache[key]

            try:
                self._log(f"failed to fetch {pricing_slug} for {date_utc} ({e}); no cached fallback available")
            except Exception:
                pass
            return None

        # IMPORTANT: cache immediately to avoid refetching for same (slug,date) in-process
        self._price_cache[key] = (float(quote.prompt_usd_per_token), float(quote.completion_usd_per_token))

        # 4) best-effort persist the quote for this date
        try:
            conn.execute("BEGIN;")
            conn.execute(
                INSERT_PRICING_SQL,
                (
                    pricing_slug,
                    quote.provider,
                    quote.provider_id,
                    date_utc,
                    quote.currency,
                    float(quote.prompt_usd_per_token),
                    float(quote.completion_usd_per_token),
                    int(time.time() * 1000),
                    json.dumps(quote.raw_json, separators=(",", ":")),
                ),
            )
            conn.execute("COMMIT;")
        except Exception:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass

        return self._price_cache[key]

    def _log(self, msg: str) -> None:
        ts = _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds")
        print(f"[pricing {ts}Z] {msg}", flush=True)

    def run(self) -> None:
        conn = db_connect(self.db_path)

        batch: list[tuple] = []
        last_commit = time.time()

        def flush() -> None:
            nonlocal last_commit, batch
            if not batch:
                return
            try:
                conn.execute("BEGIN;")
                conn.executemany(INSERT_REQUEST_SQL, batch)
                conn.execute("COMMIT;")
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                # salvage: try inserting one-by-one (still batched-ish)
                for row in batch:
                    try:
                        conn.execute("BEGIN;")
                        conn.execute(INSERT_REQUEST_SQL, row)
                        conn.execute("COMMIT;")
                    except Exception:
                        try:
                            conn.execute("ROLLBACK;")
                        except Exception:
                            pass
            batch = []
            last_commit = time.time()

        # best-effort prefetch today's pricing (no-op if missing slug)
        if self.pricing_slug:
            today = _dt.datetime.now(tz=_dt.timezone.utc).date().isoformat()
            self._get_or_fetch_pricing(conn, self.pricing_slug, today)

        while True:
            item = self.q.get()
            if item is None:
                break

            date_utc = utc_date_str_from_unix_ms(item.ts_end_unix_ms)

            prompt_price = completion_price = None
            if item.pricing_slug:
                # If we might need network fetch, flush first so we don't hold pending writes.
                key = (item.pricing_slug, date_utc)
                if key not in self._price_cache:
                    flush()
                prices = self._get_or_fetch_pricing(conn, item.pricing_slug, date_utc)
                if prices:
                    prompt_price, completion_price = prices

            cost = compute_cost_usd(item.in_tokens, item.out_tokens, prompt_price, completion_price)

            timings_json = json.dumps(item.timings, separators=(",", ":")) if isinstance(item.timings, dict) else None

            batch.append(
                (
                    item.ts_start_unix_ms,
                    item.ts_end_unix_ms,
                    date_utc,
                    item.model_alias,
                    item.pricing_slug,
                    item.method,
                    item.path,
                    item.status,
                    item.in_tokens,
                    item.out_tokens,
                    item.total_tokens,
                    item.proc_ms,
                    item.prompt_ms,
                    item.predicted_ms,
                    prompt_price,
                    completion_price,
                    cost,
                    timings_json,
                    item.response_id,
                    item.system_fingerprint,
                )
            )

            now = time.time()
            if len(batch) >= self.batch_n or (now - last_commit) >= self.batch_s:
                flush()

        flush()
        conn.close()


# -------------------------
# Reverse proxy server
# -------------------------

class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class ProxyConfig:
    def __init__(
        self,
        proxy_host: str,
        proxy_port: int,
        backend_host: str,
        backend_port: int,
        model_alias: str,
        pricing_slug: str,
        inject_oai_stream_usage: bool,
        db_path: str,
        openrouter_api_key: Optional[str],
        tail_max_bytes: int = 16 * 1024 * 1024,
    ):
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.backend_host = backend_host
        self.backend_port = backend_port
        self.model_alias = model_alias
        self.pricing_slug = pricing_slug
        self.inject_oai_stream_usage = inject_oai_stream_usage
        self.db_path = db_path
        self.openrouter_api_key = openrouter_api_key
        self.tail_max_bytes = tail_max_bytes


def build_handler(cfg: ProxyConfig, writer: DBWriter):
    HOP_BY_HOP = {
        "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
        "te", "trailers", "transfer-encoding", "upgrade"
    }

    class ProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "llama-proxy-sqlite/1.1"

        def log_message(self, fmt, *args):
            return

        def _read_body(self) -> bytes:
            cl = self.headers.get("Content-Length")
            if cl is None:
                return b""
            try:
                n = int(cl)
            except Exception:
                return b""
            return self.rfile.read(n) if n > 0 else b""

        def _forward(self):
            ts0 = int(time.time() * 1000)
            t0 = time.time()
            req_body = self._read_body()

            # outbound headers: drop hop-by-hop + content-length (we may mutate body)
            out_headers: Dict[str, str] = {}
            for k, v in self.headers.items():
                lk = k.lower()
                if lk in HOP_BY_HOP:
                    continue
                if lk == "content-length":
                    continue
                # avoid gzip to keep tail parse simple
                if lk == "accept-encoding":
                    continue
                out_headers[k] = v
            out_headers["Host"] = f"{cfg.backend_host}:{cfg.backend_port}"

            # Inject stream_options.include_usage for OpenAI streaming chat
            if cfg.inject_oai_stream_usage and self.command in ("POST", "PUT", "PATCH"):
                ctype = (self.headers.get("Content-Type") or "").lower()
                if "application/json" in ctype and self.path.startswith("/v1/chat/completions"):
                    try:
                        payload = json.loads(req_body.decode("utf-8", "strict") or "{}")
                        if isinstance(payload, dict) and payload.get("stream") is True:
                            so = payload.get("stream_options")
                            if not isinstance(so, dict):
                                so = {}
                            if so.get("include_usage") is not True:
                                so["include_usage"] = True
                                payload["stream_options"] = so
                                req_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                    except Exception:
                        pass

            try:
                conn = http.client.HTTPConnection(cfg.backend_host, cfg.backend_port, timeout=600)
                conn.request(self.command, self.path, body=req_body, headers=out_headers)
                resp = conn.getresponse()
            except Exception as e:
                msg = f"upstream error: {e}\n".encode("utf-8", "replace")
                self.send_response(502)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
                return

            status = resp.status
            reason = resp.reason
            headers = resp.getheaders()
            hdr_l = {k.lower(): v for k, v in headers}
            upstream_chunked = "chunked" in (hdr_l.get("transfer-encoding", "").lower())
            upstream_len = hdr_l.get("content-length")
            content_type = hdr_l.get("content-type", "")

            send_chunked = upstream_chunked or (upstream_len is None)

            self.send_response(status, reason)
            for k, v in headers:
                lk = k.lower()
                if lk in HOP_BY_HOP:
                    continue
                if send_chunked and lk == "content-length":
                    continue
                self.send_header(k, v)

            if send_chunked:
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Connection", "close")
                self.close_connection = True

            self.end_headers()

            tail = bytearray()

            def write_chunk(b: bytes):
                if not b:
                    return
                self.wfile.write(f"{len(b):X}\r\n".encode("ascii"))
                self.wfile.write(b)
                self.wfile.write(b"\r\n")

            read_err = None
            try:
                while True:
                    try:
                        chunk = resp.read(64 * 1024)
                    except Exception as e:
                        # upstream died mid-stream (ConnectionResetError, IncompleteRead, etc.)
                        read_err = e
                        break

                    if not chunk:
                        break

                    try:
                        if send_chunked:
                            write_chunk(chunk)
                        else:
                            self.wfile.write(chunk)
                        try:
                            self.wfile.flush()
                        except Exception:
                            pass
                    except Exception:
                        # client went away; stop streaming but still log
                        break

                    tail += chunk
                    if len(tail) > cfg.tail_max_bytes:
                        tail = tail[-cfg.tail_max_bytes:]

                if send_chunked:
                    # best-effort terminate chunked response
                    try:
                        self.wfile.write(b"0\r\n\r\n")
                        try:
                            self.wfile.flush()
                        except Exception:
                            pass
                    except Exception:
                        pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            if read_err is not None:
                try:
                    print(f"[upstream read error] {type(read_err).__name__}: {read_err}", flush=True)
                except Exception:
                    pass

            ts1 = int(time.time() * 1000)
            proc_ms = int(round((time.time() - t0) * 1000))

            parsed = None
            try:
                if (
                    self.path.startswith("/completion")
                    or self.path.startswith("/v1/chat/completions")
                    or ("application/json" in content_type)
                    or ("text/event-stream" in content_type)
                ):
                    parsed = parse_last_json_object_from_tail(bytes(tail))
            except Exception:
                parsed = None

            in_tok = out_tok = total_tok = None
            prompt_ms = predicted_ms = None
            timings = None
            response_id = None
            system_fingerprint = None
            if isinstance(parsed, dict):
                in_tok, out_tok, total_tok, prompt_ms, predicted_ms, timings = extract_tokens_and_timings(parsed)
                response_id = parsed.get("id") if isinstance(parsed.get("id"), str) else None
                system_fingerprint = (
                    parsed.get("system_fingerprint")
                    if isinstance(parsed.get("system_fingerprint"), str)
                    else None
                )

            writer.submit(
                LogEvent(
                    ts_start_unix_ms=ts0,
                    ts_end_unix_ms=ts1,
                    model_alias=cfg.model_alias,
                    pricing_slug=cfg.pricing_slug,
                    method=self.command,
                    path=self.path,
                    status=status,
                    proc_ms=proc_ms,
                    in_tokens=in_tok,
                    out_tokens=out_tok,
                    total_tokens=total_tok,
                    prompt_ms=prompt_ms,
                    predicted_ms=predicted_ms,
                    timings=timings,
                    response_id=response_id,
                    system_fingerprint=system_fingerprint,
                )
            )

        def do_GET(self): self._forward()
        def do_POST(self): self._forward()
        def do_PUT(self): self._forward()
        def do_DELETE(self): self._forward()
        def do_PATCH(self): self._forward()
        def do_OPTIONS(self): self._forward()
        def do_HEAD(self): self._forward()

    return ProxyHandler


def serve(cfg: ProxyConfig, batch_n: int, batch_ms: int) -> int:
    os.makedirs(os.path.dirname(cfg.db_path), exist_ok=True)

    writer = DBWriter(
        db_path=cfg.db_path,
        pricing_slug=cfg.pricing_slug,
        openrouter_api_key=cfg.openrouter_api_key,
        batch_n=batch_n,
        batch_ms=batch_ms,
    )
    writer.start()

    Handler = build_handler(cfg, writer)
    httpd = ThreadingHTTPServer((cfg.proxy_host, cfg.proxy_port), Handler)

    def _stop(*_):
        try:
            httpd.shutdown()
        except Exception:
            pass

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        httpd.serve_forever()
    finally:
        writer.stop()
        writer.join(timeout=5)

    return 0


# -------------------------
# Summary command
# -------------------------

def summary(db_path: str) -> int:
    conn = sqlite3.connect(db_path, timeout=30)
    row = conn.execute(
        "SELECT COUNT(*), "
        "SUM(in_tokens), SUM(out_tokens), "
        "SUM(prompt_ms), SUM(predicted_ms), SUM(proc_ms), "
        "SUM(cost_usd) "
        "FROM requests"
    ).fetchone()
    conn.close()

    calls = row[0] or 0
    in_tok = row[1]
    out_tok = row[2]
    prompt_ms = row[3]
    predicted_ms = row[4]
    proc_ms = row[5]
    cost_usd = row[6]

    total_tok = None
    if in_tok is not None and out_tok is not None:
        total_tok = int(in_tok) + int(out_tok)

    print(f"DB:    {db_path}")
    print(f"Calls: {calls:,d}")
    print("")
    print("Tokens")
    print(f"  In:    {fmt_tokens(in_tok)} ({in_tok if in_tok is not None else '—'})")
    print(f"  Out:   {fmt_tokens(out_tok)} ({out_tok if out_tok is not None else '—'})")
    print(f"  Total: {fmt_tokens(total_tok)} ({total_tok if total_tok is not None else '—'})")
    print("")
    print("Time")
    print(f"  proc_ms:      {fmt_ms(proc_ms)} ({int(proc_ms) if proc_ms is not None else '—'}ms)")
    print(f"  prompt_ms:    {fmt_ms(prompt_ms)} ({prompt_ms if prompt_ms is not None else '—'}ms)")
    print(f"  predicted_ms: {fmt_ms(predicted_ms)} ({predicted_ms if predicted_ms is not None else '—'}ms)")
    print("")
    print("Cost")
    print(f"  total: {fmt_usd(cost_usd)}")
    return 0


# -------------------------
# CLI
# -------------------------

def env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp_serve = sub.add_parser("serve")
    sp_serve.add_argument("--db", default=os.environ.get("DB_PATH") or os.path.expanduser("~/.local/state/llama-server/usage.sqlite"))
    sp_serve.add_argument("--proxy-host", default=os.environ.get("PROXY_HOST", "0.0.0.0"))
    sp_serve.add_argument("--proxy-port", type=int, default=int(os.environ.get("PROXY_PORT", "8000")))
    sp_serve.add_argument("--backend-host", default=os.environ.get("BACKEND_HOST", "127.0.0.1"))
    sp_serve.add_argument("--backend-port", type=int, default=int(os.environ.get("BACKEND_PORT", "8001")))
    sp_serve.add_argument("--model-alias", default=os.environ.get("MODEL_ALIAS", "unknown"))
    sp_serve.add_argument("--pricing-slug", default=os.environ.get("PRICING_SLUG"))
    sp_serve.add_argument("--inject-oai-stream-usage", type=int, default=1 if env_bool("INJECT_OAI_STREAM_USAGE", True) else 0)
    sp_serve.add_argument("--batch-n", type=int, default=int(os.environ.get("SQLITE_BATCH_N", "100")))
    sp_serve.add_argument("--batch-ms", type=int, default=int(os.environ.get("SQLITE_BATCH_MS", "250")))

    sp_summary = sub.add_parser("summary")
    sp_summary.add_argument("--db", default=os.environ.get("DB_PATH") or os.path.expanduser("~/.local/state/llama-server/usage.sqlite"))

    args = ap.parse_args()

    if args.cmd == "summary":
        return summary(args.db)

    pricing_slug = (args.pricing_slug or "").strip()
    if not pricing_slug:
        raise SystemExit("PRICING_SLUG is required (e.g. openrouter/openai/gpt-4)")

    cfg = ProxyConfig(
        proxy_host=args.proxy_host,
        proxy_port=args.proxy_port,
        backend_host=args.backend_host,
        backend_port=args.backend_port,
        model_alias=args.model_alias,
        pricing_slug=pricing_slug,
        inject_oai_stream_usage=bool(args.inject_oai_stream_usage),
        db_path=args.db,
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
    )
    return serve(cfg, batch_n=args.batch_n, batch_ms=args.batch_ms)


if __name__ == "__main__":
    raise SystemExit(main())
