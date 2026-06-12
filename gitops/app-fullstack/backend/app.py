import os, time
from flask import Flask, jsonify
from flask_cors import CORS
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
CORS(app)
PrometheusMetrics(app)

START_TIME = time.time()
VERSION = os.getenv("VERSION", "v1")
ENV = os.getenv("ENV", "production")
request_count = 0

@app.get("/api/status")
def status():
    global request_count
    request_count += 1
    uptime = int(time.time() - START_TIME)
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)
    return jsonify({
        "status": "ok",
        "version": VERSION,
        "environment": ENV,
        "uptime": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
        "uptime_seconds": uptime,
        "requests_served": request_count
    })

@app.get("/api/ping")
def ping():
    return jsonify({"message": "pong", "timestamp": time.time()})

@app.get("/healthz")
def healthz():
    return "ok", 200
