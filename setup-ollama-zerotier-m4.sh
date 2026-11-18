#!/bin/zsh
# Run this in Terminal on the Mac mini. Binds Ollama only to its ZeroTier IP.
set -eu
ZT_IP="10.147.19.146"

launchctl setenv OLLAMA_HOST "${ZT_IP}:11434"
# Restart Ollama.app so it reads the new launchd environment.
osascript -e 'tell application "Ollama" to quit' >/dev/null 2>&1 || true
sleep 2
open -a Ollama
sleep 4

printf '\nOllama model list from the M4:\n'
curl --fail --silent --show-error --max-time 5 "http://${ZT_IP}:11434/api/tags"
printf '\n\nIf you see JSON above, Ollama is listening on the ZeroTier address.\n'
