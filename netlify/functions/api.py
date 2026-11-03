import sys
import os

# Add local function directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import json

try:
    from mangum import Mangum
    from app.api import app
    
    asgi_handler = Mangum(app, lifespan="off")

    def handler(event, context):
        # Normalize event path so FastAPI matches all routes cleanly
        prefix = "/.netlify/functions/api"
        for key in ["path", "rawPath"]:
            if key in event and event[key].startswith(prefix):
                normalized = event[key][len(prefix):]
                event[key] = normalized if normalized else "/"
        
        return asgi_handler(event, context)

except Exception as e:
    import traceback
    tb = traceback.format_exc()
    def handler(event, context):
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e), "traceback": tb})
        }
