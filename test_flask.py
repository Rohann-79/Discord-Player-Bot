from flask import Flask

app = Flask(__name__)


@app.route('/')
def home():
    return "I'm alive!"  # Simple endpoint to keep the server active


if __name__ == "__main__":
    print("Flask server is starting...")
    app.run(host="0.0.0.0", port=3000)
