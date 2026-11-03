import sys
import os

# Add root and backend to python path for Netlify Functions runtime
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
backend_dir = os.path.join(root_dir, "backend")

for path in [root_dir, backend_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from mangum import Mangum
    from app.api import app
    handler = Mangum(app, lifespan="off")
except Exception as e:
    import json
    def handler(event, context):
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"status": "degraded", "error": str(e)})
        }
