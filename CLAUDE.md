# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run dev server
uv run uvicorn main:app --reload

# Generate RS256 JWT keys (required before first run)
uv run python scripts/generate_jwt_keys.py

# Add a dependency
uv add <package>
```

No test suite or linter is configured yet.

## Environment Setup

Copy `.env.example` to `.env` and fill in:
- `MONGO_URI` – MongoDB connection string
- `OPEN_API_KEY` / `OPENAI_API_KEY` – OpenAI key (both checked, either works)
- `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` – RS256 PEM keys (use generate script above)
- `SUPER_ADMIN_SECRET_KEY` – Used to bootstrap first user via `X-Secret-Key` header
- `PORT` – Server port (default 8000)

## Architecture

### Request Flow

```
main.py → api/router/ → api/services/ → MongoDB (Beanie ODM)
```

All routes are registered under `/api/v1`. The `main.py` lifespan handler connects MongoDB via `db_manager` (Beanie + Motor async). Routers are thin — they validate input, call one service method, and return an `ApiResponse`.

### Auth Middleware (`api/middleware/auth.py`)

Auth is decorator-based, not FastAPI dependency injection:

```python
@require_roles(["ADMIN", "WARD_INCHARGE"])
async def my_route(request: Request, current_user: dict = None):
    ...
```

The decorator extracts `current_user` from the Bearer token (RS256 verified). The token payload already contains `user_id`, `role`, `org_id`, `staff_id`, `ward_id`, `name` — so most endpoints skip a DB user lookup. Token revocation is checked against the `RevokedToken` collection via `jti`. For super-admin bootstrapping, `@require_super_admin_or_secret()` also accepts an `X-Secret-Key` header.

### Response Shape

All endpoints return `ApiResponse` from `api/types/responses.py`:
```python
{"success": bool, "message": str, "data": Any, "timestamp": str}
```
Use `ApiResponse.ok(message, data)` or `ApiResponse.fail(message)`.

### Database Models (`api/models/`)

All models inherit from Beanie `Document`. `DatabaseManager` in `api/db.py` initializes all 14 models at startup. The database name is hardcoded as `schedule_manager` in `db.py`.

Key relationships:
- `Staff.hospital_id` → `Hospital`
- `User.staff_id` → `Staff` (org membership derived from staff)
- `Roster` contains summary; `RosterDetails` contains the full shift assignment matrix
- `RevokedToken` stores `jti` values for logout/token invalidation

### Roster Generation (`api/services/generator_pulp.py`)

The `RosterOptimizer` class uses **PuLP integer linear programming** to assign shifts. It runs a pre-analysis phase to determine 2N vs 3N staffing allocation based on seniority grades (N5 > N6 > N7), then solves the ILP. Called from `roster_service.py`.

### AI Chat Agent (`api/agent/`)

`IntentClassifier.classify(message)` calls OpenAI gpt-4o-mini and returns `{intent, confidence, reasoning}`. `ChatService` routes the intent to either:
- `ModificationAgent` – handles absence management, shift assignment, staff swap, coverage optimization (4 tools)
- `InsightAgent` – generates analytical insights

The `openai_client` is initialized at module load time with `OPEN_API_KEY or "placeholder"` so the app starts even without a key configured.
