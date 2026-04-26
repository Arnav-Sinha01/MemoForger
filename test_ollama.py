import requests
import json
import re

OLLAMA_BASE_URL = "http://localhost:11434"
model_id = "qwen3-vl:2b"

system_prompt = (
    "You are an expert academic tutor. "
    "Generate JSON flashcards in exactly this format: "
    "[{\"question\": \"...\", \"answer\": \"...\", \"difficulty\": \"easy|medium|hard\", \"tags\": [\"tag1\"]}]"
)

message = {
    "role": "user", 
    "content": "The mitochondria is the powerhouse of the cell. It produces ATP."
}

payload = {
    "model": model_id,
    "messages": [{"role": "system", "content": system_prompt}, message],
    "stream": False,
}

print("Pinging Ollama...")
try:
    resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=120)
    resp.raise_for_status()
    content = resp.json().get("message", {}).get("content", "")
    print("----- OLLAMA RESPONSE -----")
    print(content)
    print("---------------------------")
    match = re.search(r'\[\s*\{.*?\}\s*\]', content, re.DOTALL)
    if match:
        print("REGEX MATCH FOUND!")
        print(match.group(0))
    else:
        print("REGEX FAILED TO MATCH JSON ARRAY!")
except Exception as e:
    print("FAILED:", e)
