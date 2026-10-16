"""Save this applet's HTTP exchanges for a later parse.

Browsing stays independent of parsing. Bodies stay in the gitignored runtime
root. Headers, cookies and media bodies are not stored.
"""

import json
import os
from pathlib import Path

MAX_BODY = 4 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_FILES = 8000
_ENCODINGS = {"identity", "gzip", "deflate", "br", "zstd"}
_MEDIA = ("image/", "audio/", "video/", "font/", "application/octet-stream")
# These observed hosts are images, telemetry, IM or WeChat infrastructure.
# They stay on the original connection. Shop and product APIs are still saved.
_PASSTHROUGH = {
    "lx0.meituan.com", "catfront.dianping.com", "ops.meituan.com",
    "portal-portm.meituan.com", "optimus-mtsi.meituan.com", "msp.meituan.com",
    "hreport.meituan.com", "wmdxlwss.meituan.com", "sharkwsbj.sankuai.com",
    "img.meituan.net", "s3.meituan.net",
}
_PASSTHROUGH_SUFFIXES = (
    ".qpic.cn", ".img-cn.meituan.net", ".neixin.cn", ".wxgateway.com",
    ".servicewechat.com", ".dreport.meituan.net",
)


def passthrough_sni(host):
    if type(host) is not str:
        return False
    host = host.lower().rstrip(".")
    if host in _PASSTHROUGH or any(host == suffix[1:] or host.endswith(suffix)
                                    for suffix in _PASSTHROUGH_SUFFIXES):
        return True
    label, _, rest = host.partition(".")
    return rest == "meituan.net" and len(label) > 1 and label[0] == "p" and label[1:].isdigit()


class FullCapture:
    def __init__(self, root):
        self.root = Path(root) / "captured-http"
        self.pending = {}
        self.saved = self.skipped_media = self.skipped_budget = 0
        self.bytes = 0

    def open_request(self, flow):
        path = flow.request.path.partition("?")[0].partition("#")[0][:512]
        host = getattr(flow.client_conn, "sni", None) or flow.request.host or ""
        self.pending[flow.id] = {
            "method": flow.request.method,
            "host": str(host).lower()[:253],
            "path": path,
            "request": bytearray(),
            "response": bytearray(),
            "status": None,
            "content_type": "",
            "encoding": "identity",
            "skip": False,
        }

    def request_stream(self, flow_id):
        def feed(chunk):
            row = self.pending.get(flow_id)
            if row is not None and chunk:
                self._take(row["request"], chunk)
            return chunk
        return feed

    def open_response(self, flow):
        row = self.pending.get(flow.id)
        if row is None:
            return False
        kind = flow.response.headers.get("content-type", "").partition(";")[0].strip().lower()
        encoding = flow.response.headers.get("content-encoding", "identity").split(",")[0].strip().lower()
        row["status"] = flow.response.status_code
        row["content_type"] = kind[:80]
        row["encoding"] = encoding if encoding in _ENCODINGS else "other"
        row["skip"] = kind.startswith(_MEDIA) or flow.response.status_code == 101
        return not row["skip"]

    def response_stream(self, flow_id):
        def feed(chunk):
            row = self.pending.get(flow_id)
            if row is not None and chunk and not row["skip"]:
                self._take(row["response"], chunk)
            return chunk
        return feed

    def finish(self, flow_id):
        row = self.pending.pop(flow_id, None)
        if row is None or row["skip"]:
            if row is not None and row["skip"]:
                self.skipped_media += 1
            return None
        size = len(row["request"]) + len(row["response"])
        if self.saved >= MAX_FILES or self.bytes + size > MAX_TOTAL:
            self.skipped_budget += 1
            return None
        self.root.mkdir(mode=0o700, exist_ok=True)
        name = f"{self.saved + 1:06d}"
        self._write(name + ".request", bytes(row["request"]))
        self._write(name + ".response", bytes(row["response"]))
        meta = {
            "schema_version": "p29-captured-http/v1",
            "method": row["method"],
            "host": row["host"],
            "path": row["path"],
            "status": row["status"],
            "content_type": row["content_type"],
            "content_encoding": row["encoding"],
            "request_bytes": len(row["request"]),
            "response_bytes": len(row["response"]),
        }
        self._write(name + ".json", json.dumps(meta, ensure_ascii=True, sort_keys=True).encode() + b"\n")
        self.saved += 1
        self.bytes += size
        self._write_status()
        return name

    def drop(self, flow_id):
        self.pending.pop(flow_id, None)

    def _take(self, buf, chunk):
        room = MAX_BODY - len(buf)
        if room > 0:
            buf.extend(chunk[:room])

    def _write(self, name, payload):
        fd = os.open(self.root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(payload)

    def _write_status(self):
        payload = json.dumps({
            "schema_version": "p29-captured-http-status/v1",
            "saved": self.saved,
            "skipped_media": self.skipped_media,
            "skipped_budget": self.skipped_budget,
            "bytes": self.bytes,
        }, sort_keys=True).encode() + b"\n"
        path = self.root / "status.json"
        temporary = self.root / "status.json.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
        os.replace(temporary, path)
