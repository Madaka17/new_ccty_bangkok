import json
import queue
import threading
import time

from flask_sock import Sock
from simple_websocket import ConnectionClosed

sock = Sock()
_clients = []
_lock = threading.Lock()


def broadcast(message: dict):
    data = json.dumps(message, ensure_ascii=False)
    with _lock:
        targets = list(_clients)
    for q in targets:
        q.put(data)


def register_ws(app, get_simulator):
    sock.init_app(app)

    @sock.route("/ws")
    def ws_endpoint(ws):
        q = queue.Queue()
        with _lock:
            _clients.append(q)
        last_tick = 0.0
        try:
            while True:
                try:
                    msg = q.get(timeout=0.2)
                    ws.send(msg)
                except queue.Empty:
                    pass
                now = time.time()
                if now - last_tick >= 0.25:
                    snap = get_simulator().snapshot()
                    ws.send(json.dumps({"type": "tick", "data": snap}, ensure_ascii=False))
                    last_tick = now
        except ConnectionClosed:
            pass
        finally:
            with _lock:
                if q in _clients:
                    _clients.remove(q)
