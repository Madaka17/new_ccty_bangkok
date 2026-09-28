"""Entrypoint: python3 main.py

Starts the Flask app (REST API + WebSocket at /ws), the in-process sensor-fleet
simulator, and the USGS live-feed poller, and serves the dashboard frontend
at http://localhost:5000/.
"""
import os
from server.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
