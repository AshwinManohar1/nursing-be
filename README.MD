# Shiftwise — Backend

Backend API for **Shiftwise**, built with FastAPI, uv, and MongoDB.

## Tech Stack

- **Runtime**: Python 3.12+
- **Framework**: FastAPI
- **Package Manager**: uv
- **Database**: MongoDB (via Motor async driver)

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) installed
- MongoDB instance (local or Atlas)

### Setup

```bash
# Clone the repo
git clone <repo-url>
cd shiftwise-be

# Create virtual environment and install dependencies
uv sync

# Copy environment variables
cp .env.example .env
# Edit .env with your MongoDB URI and other config
```

### Run

```bash
uv run uvicorn main:app --reload
```

## Environment Variables

| Variable | Description |
|---|---|
| `MONGODB_URI` | MongoDB connection string |
| `DATABASE_NAME` | MongoDB database name |

## Project Structure

```
shiftwise-be/
├── app/
│   ├── main.py          # FastAPI app entrypoint
│   ├── api/             # Route handlers
│   ├── models/          # Pydantic models
│   ├── db/              # Database connection
│   └── core/            # Config, settings
├── pyproject.toml
└── .env.example
```
