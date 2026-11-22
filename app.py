
from flask import Flask
import database

def create_app():
    app = Flask(__name__)

    database.initialize_database()

    from api.devices import devices_bp
    app.register_blueprint(devices_bp, url_prefix="/api/v1")

    from api.templates import templates_bp
    app.register_blueprint(templates_bp, url_prefix="/api/v1")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5001, debug=True)
