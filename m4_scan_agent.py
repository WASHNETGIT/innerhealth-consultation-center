"""Local AI worker for the M4. It makes outbound HTTPS requests to the cloud app.
Set CLOUD_API_URL and AI_AGENT_KEY before running. Ollama must be running on the M4.
"""
import json
import os
import time
import urllib.error
import urllib.request

CLOUD = os.environ["CLOUD_API_URL"].rstrip("/")
KEY = os.environ["AI_AGENT_KEY"]
OLLAMA = os.getenv("M4_OLLAMA_URL", "http://10.147.19.146:11434").rstrip("/")
MODEL = os.getenv("AI_MODEL", "llama3.2:3b")
WAIT = int(os.getenv("AI_POLL_SECONDS", "20"))


def request(url, body=None, headers=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def update(job_id, state, report=None):
    body = {"ai_scan_status": state}
    if report is not None:
        body["report"] = report
    request(f"{CLOUD}/api/agent/bookings/{job_id}", body,
            {"Content-Type": "application/json", "X-AI-Agent-Key": KEY}, timeout=15)


def analyze(scan_input):
    prompt = ("Summarize these supplied scan measurements without diagnosing disease or recommending treatment. "
              "Separate observations from uncertainty, flag missing or inconsistent measurements, and state that a qualified "
              "practitioner must review the result. Do not invent values.\n\n" + str(scan_input)[:40000])
    result = request(OLLAMA + "/api/chat", {"model": MODEL, "stream": False, "messages": [
        {"role": "system", "content": "You summarize structured full-body scan measurements for practitioner review. Never diagnose or prescribe."},
        {"role": "user", "content": prompt}],
        "options": {"temperature": 0.1}}, {"Content-Type": "application/json"}, timeout=180)
    return result.get("message", {}).get("content", "")


print(f"Inner Health scan agent active; cloud={CLOUD}; Ollama={OLLAMA}; model={MODEL}", flush=True)
while True:
    try:
        agent_headers={"Content-Type": "application/json", "X-AI-Agent-Key": KEY}
        request(CLOUD + "/api/agent/heartbeat", {"model": MODEL}, agent_headers, timeout=15)
        jobs = request(CLOUD + "/api/agent/queue", headers={"X-AI-Agent-Key": KEY}, timeout=15)
        for job in jobs:
            try:
                print(f"Processing {job['reference']}", flush=True)
                update(job["id"], "processing_local_ai")
                report = analyze(job["scan_input"])
                update(job["id"], "report_ready", report)
                print(f"Report ready for {job['reference']}", flush=True)
            except Exception as exc:
                print(f"Job {job.get('reference')} failed: {exc}", flush=True)
                try:
                    update(job["id"], "queued_in_cloud")
                except Exception:
                    pass
    except Exception as exc:
        print(f"Cloud queue unavailable: {exc}", flush=True)
    time.sleep(WAIT)
