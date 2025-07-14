from flask import Flask, render_template, url_for, request, redirect
from flask_sqlalchemy import SQLAlchemy

# Import the different routes from their respective paths
from routes.waypoints import waypoints_page #/waypoints/...
from routes.boat_status import boat_status_page #/boat_status/...
from routes.autopilot_parameters import autopilot_parameters_page #/autopilot_parameters/...

# Instatiate Flask
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
db = SQLAlchemy(app)

# Build the different routes from their respective paths
app.register_blueprint(waypoints_page)
app.register_blueprint(boat_status_page)
app.register_blueprint(autopilot_parameters_page)

# Example route testing
@app.route('/', methods=['POST', 'GET'])
def index():
    return 'Hello World!'

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)

