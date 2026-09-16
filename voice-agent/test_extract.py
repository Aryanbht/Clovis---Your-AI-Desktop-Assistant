import chat

raw = 'Deleting that folder now from your D drive.\n\n{"intent": "delete_file", "params": {"path": "D:/myproject"}, "response": "Folder deleted: D:/myproject"}'
conv, task = chat._extract_json_and_text(raw)
print('Conversational:', conv)
print('Task:', task)

# Test with the other format
raw2 = 'Deleting that folder now from your D drive.{"intent": "delete_file", "params": {"path": "D:/myproject"}, "response": "Folder deleted: D:/myproject"}'
conv2, task2 = chat._extract_json_and_text(raw2)
print('Conversational2:', conv2)
print('Task2:', task2)