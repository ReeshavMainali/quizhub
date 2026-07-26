from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    # host="0.0.0.0" so team laptops on the same WiFi could reach /display if you
    # ever want a second screen elsewhere on the network; the projector machine
    # itself can just use http://localhost:5000/display
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)
