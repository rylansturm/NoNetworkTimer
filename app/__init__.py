import sys
sys.path.insert(0, '/home/pi/TaktTimer/venv/Lib/site-packages')
from appJar import gui


def create_app():
    app = gui()
    return app
