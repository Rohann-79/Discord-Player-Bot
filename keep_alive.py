from flask import Flask

app = Flask(__name__)


@app.route('/')
def home():
    return "I'm alive!"  # Simple endpoint to keep the server active


def keep_alive():
    """This function runs the Flask server."""
    print("Starting Flask server...")
    app.run(host="0.0.0.0", port=3000, debug=True,
            use_reloader=False)  # Use reloader=False to avoid conflicts
