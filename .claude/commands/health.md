Check if the local Shiftwise server is running and healthy.

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```
