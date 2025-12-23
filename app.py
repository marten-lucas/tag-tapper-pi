import logging
import sys
import atexit
import os

from tagtapperpi_comp.ui import NetDiagApp
from tagtapperpi_comp.config import load_config

# ---------- Logging ----------
# Prüfe ob wir auf DietPi laufen, sonst lokales error.log
ERROR_LOG = "/home/dietpi/error.log" if os.path.exists("/home/dietpi") else "error.log"

logging.basicConfig(
    filename=ERROR_LOG,
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

sys.stderr = open(ERROR_LOG, "a")

# ---------- Cleanup ----------
def clear_terminal():
    os.system("clear")

atexit.register(clear_terminal)

# ---------- Main ----------
if __name__ == "__main__":
    config = load_config()
    app = NetDiagApp(config)
    app.run()
