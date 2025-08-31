# Autoboat Telemetry Server

A lightweight Flask-based web server to collect, display, and manage telemetry data from the Virginia Tech Autoboat project.

## 📦 Project Structure

```txt
autoboat_telemetry_server/
├── __init__.py                   # App factory
├── routes
    ├── __init__.py               # Routes initialization
    ├── autopilot_parameters.py   # Autopilot parameters routes
    ├── boat_status.py            # Boat status routes
    ├── waypoints.py              # Waypoints management routes

instance/
    ├── config.py                 # Configuration file
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

## Server (Long term)

### Installation

```bash
git clone https://github.com/autoboat-vt/telemetry_server
cd telemetry_server
./server_files/install.sh
```
