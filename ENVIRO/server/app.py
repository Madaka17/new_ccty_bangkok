import os
import threading

from flask import Flask, send_from_directory

from . import db as dbmod
from . import sources_usgs
from . import sources_emsc
from . import sources_geofon
from . import world_quakes
from . import world_faults
from . import quake_brief
from . import node_simulator
from .simulator import Simulator, run_forever
from .ws import register_ws, broadcast
from .routes import auth_routes, situation, warning, stations, analysis, compare, admin, world, nodes

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

_stop_event = threading.Event()


def create_app():
    dbmod.init_db()

    app = Flask(__name__, static_folder=None)
    simulator = Simulator(broadcast_fn=broadcast)
    app.config["SIMULATOR"] = simulator

    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(situation.bp)
    app.register_blueprint(warning.bp)
    app.register_blueprint(stations.bp)
    app.register_blueprint(analysis.bp)
    app.register_blueprint(compare.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(world.bp)
    app.register_blueprint(nodes.bp)

    register_ws(app, lambda: app.config["SIMULATOR"])

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/health")
    def health():
        return {"ok": True}

    sim_thread = threading.Thread(target=run_forever, args=(simulator, _stop_event), daemon=True)
    sim_thread.start()

    usgs_thread = threading.Thread(target=sources_usgs.run_forever, args=(_stop_event,), daemon=True)
    usgs_thread.start()

    emsc_thread = threading.Thread(target=sources_emsc.run_forever, args=(_stop_event,), daemon=True)
    emsc_thread.start()

    geofon_thread = threading.Thread(target=sources_geofon.run_forever, args=(_stop_event,), daemon=True)
    geofon_thread.start()

    world_quakes_thread = threading.Thread(target=world_quakes.run_forever, args=(_stop_event,), daemon=True)
    world_quakes_thread.start()

    # AI earthquake brief ("AI วิเคราะห์แผ่นดินไหว" tab), rewritten from world_quakes' data
    threading.Thread(target=quake_brief.run_forever, args=(_stop_event,), daemon=True).start()

    # The 7 simulated real-shaped nodes on the "สถานีตรวจวัด" page (see
    # node_simulator.py + db.SIMULATED_REAL_NODES) -- apply_fn is passed in
    # rather than imported by node_simulator.py itself, to avoid a
    # routes -> app -> routes import cycle.
    node_sim_thread = threading.Thread(
        target=node_simulator.run_forever, args=(_stop_event, nodes.apply_node_telemetry), daemon=True,
    )
    node_sim_thread.start()

    world_faults.ensure_built_async()

    return app
