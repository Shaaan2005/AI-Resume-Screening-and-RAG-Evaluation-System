"""Entry point: `python app.py` starts the AI Resume Screening web app.

The application itself lives in the `webapp/` package (see webapp/__init__.py).
"""
import os

from webapp import create_app

app = create_app()


if __name__ == "__main__":
    # Never enable the Werkzeug debugger on a network-facing interface: it allows
    # arbitrary code execution. Opt in locally with FLASK_DEBUG=1.
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    app.run(debug=debug, host=host, port=5000, use_reloader=False)
