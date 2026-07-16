from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class SpaRequestHandler(SimpleHTTPRequestHandler):
    def send_head(self):  # type: ignore[override]
        path = self.translate_path(self.path)
        if not Path(path).exists() and "api/" not in self.path:
            self.path = "/index.html"
        return super().send_head()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()

    directory = Path(args.directory).resolve()
    if not (directory / "index.html").exists():
        raise SystemExit(f"Missing frontend index.html: {directory / 'index.html'}")

    handler = lambda *handler_args, **handler_kwargs: SpaRequestHandler(  # noqa: E731
        *handler_args,
        directory=str(directory),
        **handler_kwargs,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {directory} at http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
