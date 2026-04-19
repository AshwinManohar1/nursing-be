# Shiftwise — Backend

Backend API for **Shiftwise**, an AI-powered nurse shift roster management system built for hospitals. Handles roster generation via integer linear programming, AI-assisted roster modification, shift insights, ward management, and real-time occupancy tracking.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12+ |
| Framework | FastAPI |
| Package Manager | uv |
| Database | MongoDB Atlas (Motor async + Beanie ODM) |
| Auth | RS256 JWT (access + refresh tokens) |
| AI | OpenAI GPT-4o-mini |
| Roster Optimizer | PuLP (Integer Linear Programming) |
| Rate Limiting | SlowAPI |

---

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) installed
- MongoDB Atlas cluster (or local MongoDB)

### Setup

```bash
# Clone and install dependencies
git clone <repo-url>
cd shiftwise-be
uv sync

# Copy and fill environment variables
cp .env.example .env
```

### Generate JWT Keys

RS256 asymmetric keys are required before first run:

```bash
uv run python scripts/generate_jwt_keys.py
```

Copy the output values into your `.env` as `JWT_PRIVATE_KEY` and `JWT_PUBLIC_KEY`.

### Run

```bash
uv run uvicorn main:app --reload
```

API docs available at `http://localhost:8000/docs`

---

## Environment Variables

| Variable | Description |
|---|---|
| `MONGO_URI` | MongoDB connection string |
| `PORT` | Server port (default `8000`) |
| `OPENAI_API_KEY` | OpenAI API key for AI features |
| `JWT_PRIVATE_KEY` | RS256 private key (PEM, single-line with `\n`) |
| `JWT_PUBLIC_KEY` | RS256 public key (PEM, single-line with `\n`) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL (default `15`) |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token TTL (default `7`) |
| `SUPER_ADMIN_SECRET_KEY` | Secret for bootstrapping the first admin user |

---

## API Reference

All routes are prefixed with `/api/v1`.

### Auth

| Method | Endpoint | Description |
|---|---|---|
| POST | `/login` | Login with employee ID + password. Returns access + refresh tokens |
| POST | `/refresh` | Exchange refresh token for new access token |
| POST | `/logout` | Revoke current token (blocklisted by JTI) |

### Users

| Method | Endpoint | Access |
|---|---|---|
| GET | `/users` | SUPER_ADMIN |
| POST | `/users` | SUPER_ADMIN or `X-Secret-Key` header |
| GET | `/users/{user_id}` | SUPER_ADMIN |
| PUT | `/users/{user_id}` | SUPER_ADMIN |
| DELETE | `/users/{user_id}` | SUPER_ADMIN |

### Staff

| Method | Endpoint | Description |
|---|---|---|
| GET | `/staff` | List staff (filterable by hospital/ward) |
| POST | `/staff` | Create staff member |
| GET | `/staff/{staff_id}` | Get staff by ID |
| PUT | `/staff/{staff_id}` | Update staff |
| DELETE | `/staff/{staff_id}` | Delete staff |
| POST | `/staff/upload` | Bulk upload via CSV |

### Roster

| Method | Endpoint | Description |
|---|---|---|
| POST | `/rosters/generate` | Generate roster using ILP optimizer |
| GET | `/rosters` | List rosters with pagination |
| GET | `/rosters/{roster_id}` | Get full roster with shift assignments |
| PATCH | `/rosters/{roster_id}` | Apply patches (AI modifications) |
| DELETE | `/rosters/{roster_id}` | Delete roster |
| GET | `/rosters/preferences/{previous_roster_id}` | Compute preferences for next roster period |

### Wards & Hospitals

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/wards` | List / create wards |
| GET/PUT/DELETE | `/wards/{ward_id}` | Ward CRUD |
| GET | `/wards/hospital/{hospital_id}` | Wards by hospital |
| GET | `/wards/{ward_id}/ratio` | Bed-to-nurse ratio |
| GET/POST | `/hospitals` | List / create hospitals |
| GET/PUT/DELETE | `/hospitals/{hospital_id}` | Hospital CRUD |

### Shifts

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/shifts` | List / create shift definitions |
| GET/PUT/DELETE | `/shifts/{shift_id}` | Shift CRUD |

### AI Chat

| Method | Endpoint | Description |
|---|---|---|
| POST | `/chat` | Send a message to the AI copilot |

Request body:
```json
{
  "message": "Move nurse John to night shift on Dec 15",
  "roster_id": "<roster_id>"
}
```

### Ward Occupancy & Transfers

| Method | Endpoint | Description |
|---|---|---|
| POST | `/ward-occupancy/parse-email` | Parse HTML occupancy email and store |
| POST | `/ward-occupancy/create` | Manually create occupancy record |
| GET | `/ward-occupancy/list/all` | List all occupancy records |
| GET/PUT/DELETE | `/ward-occupancy/{occupancy_id}` | Occupancy CRUD |
| GET/POST | `/ward-transfers` | List / create ward transfers |
| PUT | `/ward-transfers/{transfer_id}/cancel` | Cancel a transfer |

### Dashboard

| Method | Endpoint | Description |
|---|---|---|
| GET | `/dashboard/ward-performance` | Ward KPIs and shift performance summary |

---

## Architecture

```
main.py
└── lifespan: connects MongoDB via db_manager (Beanie + Motor)
└── 11 routers registered under /api/v1

Request flow:
  Router → Middleware (auth decorator) → Service → MongoDB
```

### Auth Middleware

Auth is applied via decorators, not FastAPI dependencies:

```python
@require_roles(["ADMIN", "WARD_INCHARGE"])
async def my_route(request: Request, current_user: dict = None):
    ...
```

The JWT payload includes `user_id`, `role`, `org_id`, `staff_id`, `ward_id`, and `name` — so most routes avoid DB lookups for auth. Logout revokes tokens by storing the `jti` in the `RevokedToken` collection, checked on every request.

Roles: `SUPER_ADMIN` > `ADMIN` > `WARD_INCHARGE` > `STAFF`

### Roster Generation (ILP)

`POST /rosters/generate` triggers the `RosterOptimizer` in `api/services/generator_pulp.py`. It uses **PuLP integer linear programming** to assign shifts subject to:

- Minimum staffing per shift (M/E/N)
- Consecutive shift constraints
- Night shift recovery rules
- Seniority-based 2N vs 3N allocation (grades N5–N8)
- Staff leave and preference carry-overs

### AI Copilot

`POST /chat` routes through a 3-step pipeline:

```
Message → IntentClassifier → Agent → Response
```

1. **IntentClassifier** calls GPT-4o-mini to classify intent as `modification`, `insight`, or `other`
2. **ModificationAgent** handles roster changes via 4 tools:
   - `handle_absence_management` — sick/personal/emergency leave
   - `handle_shift_assignment` — direct shift changes
   - `handle_staff_swap` — swaps between two staff members
   - `handle_coverage_optimization` — fills understaffed shifts
3. **InsightAgent** analyzes roster structure and generates plain-language summaries of workload distribution, shift coverage gaps, and staffing imbalances

### Response Shape

All endpoints return:
```json
{
  "success": true,
  "message": "...",
  "data": {},
  "timestamp": "2024-01-01T00:00:00"
}
```

---

## Project Structure

```
shiftwise-be/
├── main.py                  # App entry point, router registration
├── api/
│   ├── config.py            # Env var loading
│   ├── db.py                # MongoDB + Beanie initialization
│   ├── agent/
│   │   ├── classifier.py    # Intent classification
│   │   ├── prompts.py       # Shared prompts + PuLP rules
│   │   ├── modification_agent/   # Roster modification tools
│   │   └── insight_agent/        # Roster analysis tools
│   ├── middleware/
│   │   ├── auth.py          # JWT auth decorators
│   │   └── error_handler.py # Global exception handlers
│   ├── models/              # Beanie ODM documents + Pydantic schemas
│   ├── router/              # FastAPI route handlers
│   ├── services/            # Business logic
│   ├── types/
│   │   └── responses.py     # ApiResponse wrapper
│   └── utils/
│       ├── jwt_auth.py      # RS256 token creation/verification
│       ├── cors.py          # CORS setup
│       ├── logger.py        # Structured logger
│       ├── openai_client.py # GPT wrapper
│       └── rate_limit.py    # SlowAPI limiter
├── scripts/
│   └── generate_jwt_keys.py # RSA key pair generator
├── .claude/
│   └── commands/            # Claude Code slash commands
├── vercel.json              # Vercel deployment config
└── pyproject.toml
```

---

## Deployment

Deployed on **Vercel** with zero configuration — uv and `pyproject.toml` are auto-detected.

```bash
vercel --prod
```

Set all environment variables under **Vercel → Project → Settings → Environment Variables** before deploying. Ensure MongoDB Atlas Network Access allows `0.0.0.0/0` for Vercel's dynamic IPs.

---

## Claude Code Slash Commands

| Command | Description |
|---|---|
| `/dev` | Start local dev server |
| `/health` | Check if local server is running |
| `/generate-keys` | Generate RS256 JWT key pair |
| `/deploy` | Deploy to Vercel production |
| `/routes` | List all registered API routes |
