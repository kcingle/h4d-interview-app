"""
scripts/check_demo_target.py — Run before every local app run during demo
work. Prints the host/database that .streamlit/secrets.toml (which the app
reads first) points at, and exits non-zero unless it is the demo database.

    venv\\Scripts\\python scripts\\check_demo_target.py C:\\Users\\katei\\h4d-secrets\\demo_database_url.txt
"""
import sys
import tomllib
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def ident(url):
    p = urllib.parse.urlparse(url)
    return p.hostname or "", p.path.lstrip("/")


demo_host, demo_db = ident(Path(sys.argv[1]).read_text(encoding="utf-8").strip())
app_host, app_db = ident(
    tomllib.loads((REPO / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))["DATABASE_URL"]
)
print(f"App will connect to: host={app_host}  database={app_db}")
if (app_host, app_db) != (demo_host, demo_db):
    sys.exit("STOP: that is NOT the demo database.")
print("Confirmed: demo database.")
