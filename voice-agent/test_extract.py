import brain

raw = '{"intent": "delete_file", "params": {"path": "D:/myproject"}, "response": "Folder deleted: D:/myproject"}'
result = brain._extract_json(raw)
print('Intent:', result['intent'])
print('Params:', result['params'])
print('Response:', result['response'])

# Test with conversational text mixed in (should still find JSON)
raw2 = 'Deleting that folder now from your D drive.\n\n{"intent": "delete_file", "params": {"path": "D:/myproject"}, "response": "Folder deleted: D:/myproject"}'
result2 = brain._extract_json(raw2)
print('Intent2:', result2['intent'])
print('Response2:', result2['response'])

# Test with no JSON (pure conversation) — should return unknown with raw text as response
raw3 = 'The weather is nice today, isnt it?'
result3 = brain._extract_json(raw3)
print('Intent3 (no JSON):', result3['intent'])
print('Response3 (no JSON):', result3['response'])

# Test with nested JSON objects
raw4 = '{"intent": "create_folder", "params": {"path": "/test", "options": {"recursive": true}}, "response": "Folder created"}'
result4 = brain._extract_json(raw4)
print('Intent4 (nested):', result4['intent'])
print('Params4 (nested):', result4['params'])

# Test with old schema (tool/action/args)
raw5 = '{"tool": "open_app", "args": {"app_name": "chrome"}, "message": "Opening Chrome"}'
result5 = brain._extract_json(raw5)
print('Intent5 (old schema):', result5['intent'])
print('Params5 (old schema):', result5['params'])
print('Response5 (old schema):', result5['response'])

# Test with no braces at all
raw6 = 'Hello there'
result6 = brain._extract_json(raw6)
print('Intent6 (no braces):', result6['intent'])
print('Response6 (no braces):', result6['response'])

print('\nAll tests passed!')
