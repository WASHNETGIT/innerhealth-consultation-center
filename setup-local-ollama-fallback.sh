#!/usr/bin/env bash
# Start a private loopback Ollama and download a small fallback model.
set -eu
OLLAMA_LOCAL_URL="http://127.0.0.1:11434"
MODEL="llama3.2:3b"

if ! curl --connect-timeout 1 --max-time 2 --silent --fail "$OLLAMA_LOCAL_URL/api/tags" >/dev/null 2>&1; then
  nohup env OLLAMA_HOST="$OLLAMA_LOCAL_URL" ollama serve >/tmp/inner-health-ollama.log 2>&1 &
  for attempt in $(seq 1 30); do
    if curl --connect-timeout 1 --max-time 2 --silent --fail "$OLLAMA_LOCAL_URL/api/tags" >/dev/null 2>&1; then break; fi
    sleep 1
  done
fi

if ! curl --connect-timeout 1 --max-time 2 --silent --fail "$OLLAMA_LOCAL_URL/api/tags" >/dev/null 2>&1; then
  echo "Could not start local Ollama. Check /tmp/inner-health-ollama.log" >&2
  exit 1
fi

OLLAMA_HOST="$OLLAMA_LOCAL_URL" ollama pull "$MODEL"
printf '\nLocal fallback is ready at %s using %s\n' "$OLLAMA_LOCAL_URL" "$MODEL"
printf 'Check it with: curl %s/api/tags\n' "$OLLAMA_LOCAL_URL"
