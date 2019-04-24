from app import create_app
from app.layout import layout
from app.functionality import function


class Timer:
    # prepare the gui
    @staticmethod
    def prepare(app):
        app = layout(app)  # passes the bare gui through the layout generator
        app = function(app)  # gives the gui the functionality (functionally the same as importing functionality.*)
        return app

    def start(self):
        app = create_app()
        app = self.prepare(app)
        app.go()


if __name__ == '__main__':
    App = Timer()
    App.start()
