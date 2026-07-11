import requests

base = 'http://127.0.0.1:8001'
print('HEALTH', requests.get(f'{base}/health').text)
resp = requests.post(f'{base}/analyze', json={'document_name': 'demo.txt', 'content': 'This document discusses automated decision making and privacy concerns.'})
print('ANALYZE', resp.status_code, resp.text)
print('HISTORY', requests.get(f'{base}/history').text)
