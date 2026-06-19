"""Local web server for the Prophet-6 visual patch generator (decisions.md D-020).

Stdlib only (http.server) — consistent with the project's no-extra-infrastructure rule
(same reasoning as the NumPy vector store, D-009).

Routes:
  GET  /            -> static panel UI (src/ui/static/)
  GET  /api/schema  -> sections + params + INIT patch (drives panel rendering)
  POST /api/patch   -> {"query": "..."} -> generated, validated patch JSON

Usage: python src/ui/server.py [port]   (default 8765; first request warms the
embedding model, so the first patch takes a few extra seconds)
"""
import json
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import trace_log  # noqa: E402  (observability: emit traces outside the generation lock)
from patch_schema import INIT_PATCH, SECTIONS  # noqa: E402

_generate_lock = threading.Lock()  # one LLM/embed call at a time keeps memory sane


def _init_sysex():
    """INIT edit-buffer dump so the Init button can reset the hardware too (D-030)."""
    try:
        sys.path.insert(0, str(HERE.parent / "patches"))
        from encode_sysex import encode_edit_buffer
        return encode_edit_buffer(INIT_PATCH, "INIT")
    except Exception:
        return None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE / "static"), **kwargs)

    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        from urllib.parse import urlsplit, parse_qs
        parts = urlsplit(self.path)
        path, q = parts.path, parse_qs(parts.query)
        if path == "/api/schema":
            self._send_json({"sections": SECTIONS, "init": INIT_PATCH,
                             "init_sysex": _init_sysex()})
        elif path.startswith("/api/"):
            self._api_get(path, q)
        else:
            super().do_GET()

    def _api_get(self, path: str, q: dict) -> None:
        """Read-only dashboard endpoints (file-backed, no pipeline state mutated)."""
        try:
            import trace_store
            if path == "/api/traces":
                limit = int((q.get("limit") or ["200"])[0])
                self._send_json({"traces": trace_store.iter_summaries(
                    limit=limit, filt=(q.get("filter") or [None])[0])})
            elif path == "/api/trace":
                rec = trace_store.get((q.get("id") or [""])[0])
                self._send_json(rec or {"error": "trace not found"}, 200 if rec else 404)
            elif path == "/api/overview":
                import eval_store
                self._send_json(eval_store.overview())
            elif path == "/api/eval/runs":
                import eval_store
                self._send_json({"runs": eval_store.list_runs((q.get("kind") or [None])[0])})
            elif path == "/api/eval/diff":
                import eval_store
                a, b = (q.get("a") or [""])[0], (q.get("b") or [""])[0]
                self._send_json(eval_store.diff(a, b))
            elif path == "/api/corpus":
                import corpus_store
                self._send_json(corpus_store.corpus_health())
            elif path == "/api/golden":
                import corpus_store
                self._send_json({"records": corpus_store.golden_records(),
                                 "gate": corpus_store.golden_gate()})
            else:
                self._send_json({"error": "unknown endpoint"}, 404)
        except Exception as e:
            self._send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        if self.path == "/api/patch":
            sink: dict = {}
            t0, query, result = time.time(), "", None
            try:
                query = json.loads(raw).get("query", "").strip()
                if not query:
                    self._send_json({"error": "empty query"}, 400)
                    return
                from generate_patch import generate_patch  # lazy heavy import
                with _generate_lock:
                    result = generate_patch(query, trace_sink=sink)
                self._send_json(result)  # respond first; trace is emitted below, off-lock
            except Exception as e:
                if result is None:  # generation itself failed (vs a send error after success)
                    ts = trace_log.now_ts()
                    sink = {"trace_id": trace_log.new_id(ts), "ts": ts, "ok": False,
                            "error": f"{type(e).__name__}: {e}", "query": query}
                try:
                    self._send_json({"error": f"{type(e).__name__}: {e}"}, 500)
                except Exception:
                    pass
            finally:
                if sink:  # emit AFTER responding and OUTSIDE _generate_lock
                    sink.setdefault("wall_ms", int((time.time() - t0) * 1000))
                    trace_log.emit(sink)
        elif self.path == "/api/decode":
            self._decode_capture(raw)
        elif self.path == "/api/golden/promote":
            try:
                import corpus_store
                self._send_json(corpus_store.promote(json.loads(raw).get("record") or {}))
            except Exception as e:
                self._send_json({"error": f"{type(e).__name__}: {e}"}, 400)
        else:
            self._send_json({"error": "unknown endpoint"}, 404)

    def _decode_capture(self, raw: bytes) -> None:
        """Decode a captured P6 sysex dump (D-031); save it for INIT grounding."""
        try:
            sx = bytes(int(b) & 0xFF for b in json.loads(raw).get("sysex", []))
            sys.path.insert(0, str(HERE.parent / "patches"))
            from decode_sysex import decode_message
            d = decode_message(sx)
            if not d:
                self._send_json({"error": "not a Prophet-6 program / edit-buffer sysex"}, 400)
                return
            out = {"name": d["name"], "bank": d["bank"], "program": d["program"],
                   "params": d["params"]}
            (HERE.parents[1] / "data" / "patches" / "captured_dump.json").write_text(
                json.dumps(out, indent=1), encoding="utf-8")
            self._send_json({**out, "ok": True, "bytes": len(sx)})
        except Exception as e:
            self._send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def log_message(self, fmt, *args):
        sys.stderr.write("[ui] %s\n" % (fmt % args))


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler))
    print(f"Prophet-6 patch panel: http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
