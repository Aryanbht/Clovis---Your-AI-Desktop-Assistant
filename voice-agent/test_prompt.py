import brain
import requests

# Simulate the full prompt with history
system_prompt = brain._load_system_prompt()
context = "User: delete the folder myproject on d drive\nClovis: Sorry, I didn't get that.\nUser: delete the folder myproject on d drive"
full_prompt = f"{system_prompt}\n\nConversation so far:\n{context}\n\nUser: delete the folder myproject on d drive"

payload = {
    'model': 'qwen2.5:3b-instruct',
    'prompt': full_prompt,
    'stream': False,
}

resp = requests.post(brain.OLLAMA_URL, json=payload, timeout=60)
body = resp.json()
raw = body.get('response', '')
print('RAW OUTPUT:')
print(repr(raw))