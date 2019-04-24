import sys
sys.path.insert(0, '/home/pi/TaktTimer/venv/Lib/site-packages')  # All dependencies are in virtual environment
from appJar import gui  # http://appjar.info  for documentation
#                       # this is the main library for creating the gui


def create_app():
    app = gui()
    return app
