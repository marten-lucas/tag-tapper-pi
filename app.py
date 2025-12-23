import logging
import sys
import atexit
import os

from netdiag_components.ui import NetDiagApp
from netdiag_components.config import load_config

# ---------- Logging ----------
logging.basicConfig(
    filename="error.log",
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

sys.stderr = open("error.log", "a")

# ---------- Cleanup ----------
def clear_terminal():
    os.system("clear")

atexit.register(clear_terminal)

# ---------- Main ----------
if __name__ == "__main__":
    config = load_config()
    app = NetDiagApp(config)
    app.run()
