import os

# Simulate Vercel environment
os.environ['VERCEL'] = '1'

import api.index
from fastapi.testclient import TestClient

client = TestClient(api.index.app)

# Test health endpoint
r_health = client.get('/health')
print('Health:', r_health.status_code, r_health.json())

# Test root path
r_root = client.get('/')
print('Root:', r_root.status_code)

# Test admin AI blog page (should be accessible via /admin/ai-blog)
r_admin = client.get('/admin/ai-blog')
print('Admin AI Blog:', r_admin.status_code)

# Test cron run endpoint
r_cron = client.get('/admin/ai-blog/cron-run')
print('Cron run:', r_cron.status_code, r_cron.json())
