"""Stands in for Edge handing a new app window to a copy of itself that's already running: starts the stand-in window
as a separate process, then exits at once, as the msedge.exe that PAC ACARS started does."""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
subprocess.Popen([sys.executable, os.path.join(here, "fake_window.py")] + sys.argv[1:], start_new_session=True,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
