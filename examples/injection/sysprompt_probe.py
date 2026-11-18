"""Shows which system prompt Claude Code sends, without sending it anywhere.

  python3 examples/injection/sysprompt_probe.py OUT.jsonl &
  ANTHROPIC_BASE_URL=http://127.0.0.1:8765 claude -p "say ok" <same flags as the runs>
  kill %1

A local server answers every request with an error and appends only the model and the system text to OUT.jsonl.
Headers, where the credentials travel, are never read or stored. No model is called.
"""

import http.server
import json
import sys

OUT = sys.argv[1]


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        system = body.get("system")
        text = system if isinstance(system, str) else "\n".join(
            b.get("text", "") for b in system or [] if isinstance(b, dict))
        with open(OUT, "a") as f:
            f.write(json.dumps({"model": body.get("model"), "system": text}) + "\n")
        self.send_response(500)
        self.end_headers()

    def log_message(self, *args):
        pass


http.server.HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
