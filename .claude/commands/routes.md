List all registered API routes in the app.

```bash
uv run python -c "
from main import app
for r in sorted(app.routes, key=lambda x: x.path):
    methods = list(getattr(r, 'methods', None) or [])
    if methods:
        print(methods, r.path)
"
```
