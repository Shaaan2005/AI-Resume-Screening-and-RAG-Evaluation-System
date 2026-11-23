"""Entry point: `python app.py` starts the AI Resume Screening web app.

The application itself lives in the `webapp/` package (see webapp/__init__.py).
"""
import os

from webapp import create_app

app = create_app()


def warm_up():
    """Loads the index and the department model now, so the first search isn't slow (~5 s)."""
    from chroma_search import get_collection, get_cross_encoder
    from model_loader import model
    try:
        get_collection()
        get_cross_encoder()
        model.encode("warm up")
    except Exception as e:  # never stop the server from starting
        app.logger.warning(f"Warm-up skipped: {e}")


warm_up()  # also runs under gunicorn, which imports app:app


if __name__ == "__main__":
    # Never enable the Werkzeug debugger on a network-facing interface: it allows
    # arbitrary code execution. Opt in locally with FLASK_DEBUG=1.
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    app.run(debug=debug, host=host, port=5000, use_reloader=False)
