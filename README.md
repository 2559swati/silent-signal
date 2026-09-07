# SilentSignal AI

Connecting weak signals to uncover problems before anyone reports them.

## Current Development Phase

This project is currently in **Phase 0**.

Phase 0 sets up the foundational project structure, minimal frontend/backend applications, and testing environments. It does not include any ML models, anomaly detection, database tables, or business logic.

## Technology Stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, shadcn/ui, Lucide React
- **Backend:** Python, FastAPI, Pydantic, Uvicorn, pytest
- **Database:** PostgreSQL (via Docker)
- **Infrastructure:** Docker Compose

## How to Start the Project

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Start the services using Docker Compose:
   ```bash
   docker-compose up --build
   ```

## Verification

To verify the backend health endpoint, visit:
[http://localhost:8000/api/health](http://localhost:8000/api/health)

You should see:
```json
{"status": "ok"}
```

The frontend should be accessible at [http://localhost:5173](http://localhost:5173).

*Note: This is currently only the project foundation.*
