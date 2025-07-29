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

## 🚀 Quick Start

### Installation

```bash
pip install -e .
```

### Running the server

1. Production ([Gunicorn](https://gunicorn.org/)):

```bash
gunicorn "autoboat_telemetry_server:create_app()"
```

2. Development (Flask):

```bash
flask run
```
