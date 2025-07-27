# Autoboat Telemetry Server

A lightweight Flask-based web server to collect, display, and manage telemetry data from the Virginia Tech Autoboat project.

## 📦 Project Structure

```txt
autoboat_telemetry_server/
├── init.py                   # App factory
├── _autopilot_parameters.py  # Blueprint: autopilot params
├── _boat_status.py           # Blueprint: boat status
├── _waypoints.py             # Blueprint: waypoints
```

## How to run

From inside the folder you cloned from Github, run the following:

```bash
pip install .
```

```bash
gunicorn "autoboat_telemetry_server:create_app()"
```
