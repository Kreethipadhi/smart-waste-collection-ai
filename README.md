# EcoRoute — Agentic Smart Waste Collection

EcoRoute is an end-to-end local implementation of an Agentic AI waste-collection and recycling-optimization system. It ingests and validates smart-bin readings, forecasts fill levels, produces explained priorities, assigns compatible vehicles, creates capacity-constrained collection routes, records human approval, tracks route states, produces recycling insight, and generates a PDF report.

## What is included

- React/TypeScript dashboard with backend login, bin registration, sensor ingestion, route review, collection tracking, analytics, and PDF download.
- FastAPI orchestration API, SQLite development storage, PostgreSQL support through SQLAlchemy, Alembic migrations, auth/audit tables, Docker support, tests, and synthetic sample data.
- Eight independently implemented agents with a common workflow id and durable agent-event trace.
- Actual capacity-constrained nearest-neighbour route optimization; all routes enforce available fleet, remaining capacity, and compatible waste streams.

## Architecture

```text
IoT sensor events → Bin Monitoring/Validation → Forecast Agent → Priority Agent
        → Fleet Agent → Route Optimizer → Reviewer → Human approval
        → Collection state tracking → Recycling analytics → PDF report
```

Read the implementation diagram in [docs/architecture.md](docs/architecture.md). A SQLAlchemy Core repository supports SQLite locally and PostgreSQL through psycopg in production. Alembic migrations are applied explicitly; production startup never creates, seeds, or deletes schema/data.

## Run locally

### Backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
python -m app.create_admin
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Local development defaults to `sqlite:///./ecoroute.db` and seeds sample records only when the database has no bins. The development authentication secret is generated for the process if `AUTHENTICATION_SECRET` is blank; set a local value in `backend/.env` to keep sessions valid across restarts. Run migrations before creating the first administrator.

The initial Alembic revision creates schema only; it does not copy existing rows from `backend/ecoroute.db` to PostgreSQL. If existing local history is needed in production, plan and verify a separate SQLite-to-PostgreSQL data transfer against a disposable target before cutover. Do not point any import/reset script at production without a backup and explicit review.

### Frontend

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
npm run dev -- --host 127.0.0.1
```

With an empty `VITE_API_BASE_URL`, Vite's development proxy forwards `/api` to `http://127.0.0.1:8000`. The API docs are at `http://127.0.0.1:8000/docs`; process health is `/health`, and database readiness is `/ready`. Sign in using the administrator created by the CLI.

## API highlights

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | API health and registered agent count |
| `GET /ready` | Database and schema readiness |
| `POST /api/auth/login` | Exchange administrator credentials for a short-lived bearer token |
| `GET /api/auth/me` | Current authenticated account |
| `GET /api/bins` | Persistent smart-bin state |
| `POST /api/sensors/ingest` | Validate and record a sensor signal |
| `POST /api/orchestrate` | Execute the eight-agent workflow and return evidence |
| `POST /api/routes/{id}/approval` | Record a human approval/rejection decision |
| `POST /api/routes/{id}/start` | Move an approved route to In Progress |
| `POST /api/routes/{id}/complete` | Mark a completed route Verified |
| `GET /api/recycling/analytics` | Deterministic recycling KPIs |
| `POST /api/reports/current.pdf` | Download the structured operational report |

Operational APIs require `Authorization: Bearer <token>`; state-changing routes require the `admin` or `operator` role. No default administrator is created. Use `python -m app.create_admin` once after applying migrations; it reads the password interactively and stores only a salted scrypt hash. There is no user-management UI or password-reset flow yet.

## Decision rules

The system marks bins critical at 95% fill, high at the configured 85% threshold, and high when the forecast crosses 85% before the next collection cycle. It rejects sensor jumps greater than 45 percentage points for verification. The forecast agent calculates recent linear fill trends and labels the output as a prediction. The route engine groups streams, verifies capacity and compatibility, then uses a distance-based nearest-neighbour sequence for each feasible vehicle route.

## Operator Walkthrough

1. Apply migrations and create the first administrator using the backend commands above. Start the backend and frontend in separate terminals, then sign in. `/health` checks the process; `/ready` checks DB/schema readiness; `/docs` documents the API.
2. Open **Smart bins**. Enter a unique bin ID, location, waste type, latitude/longitude, capacity, initial fill, threshold, and optional sensor ID. Select **Register bin**. The value is persisted; duplicate IDs and invalid coordinate/capacity ranges are rejected.
3. Open **Sensor alerts**. Select the bin and enter a fill percentage, then select **Submit reading**. A change within the 45-point validation limit is saved and updates the bin. A sudden jump above 45 points is marked `verification_required`; the previous fill remains unchanged.
4. Select **Optimize routes**. The backend uses current fills and recent readings to calculate a two-day linear trend, priority, and routes. **Forecasting** and **Collection priority** show the result and explanation. The optimization event lists bins that were not assigned when no compatible available vehicle has enough capacity.
5. Review routes in **Route optimization** or **Collection tracking**. **Approve & dispatch** records the operator decision and changes the vehicle to active. **Mark collection complete** records estimated collected volume, sets the route bins to 0%, updates their collection time, and releases the vehicle.
6. Check **Recycling analytics** after a route is completed. Totals and rate are computed from recorded bin volumes; they are liters estimated from capacity and fill, not measured kilogram weights. **Reports** downloads the current PDF snapshot.
7. Open **AI operations center** to inspect agent event inputs, outputs, status, and explanation. Sensor/route actions can also be checked in `GET /api/events`, `GET /api/routes`, and `GET /api/bins`.

## Current Scope and Limitations

- Forecasting is a deterministic linear trend baseline, not a trained ML model; the repository does not yet include model training, train/test evaluation, MAE/RMSE, or confidence calibration.
- The map is a schematic coordinate plot, not a street-map/GIS integration. Route sequencing uses nearest-neighbour distance rather than a solver such as OR-Tools.
- Recycling uses estimated liters. Weight readings, contamination inspections, and detailed collection records such as actual driver/time/volume are not yet captured.
- Bin creation and sensor ingestion are available in the UI. Vehicle editing, route editing/rejection controls, image classification, live MQTT streaming, and hosted deployments are not implemented.
- Fleet capacity is checked when a route is planned. The demo fleet currently cannot dispatch every waste stream at once; unassigned bins are reported rather than mixed into an incompatible route.
- Authentication currently provisions only the first administrator through a secure CLI prompt; there is no user-management UI, account recovery, or rate limiting. Access tokens are held in frontend memory and are lost on refresh.
- Production PostgreSQL behavior is implemented but has not been exercised against PostgreSQL in this environment. The integration test is opt-in and skipped unless a dedicated test database is supplied.

## Test scenarios

1. 92% fill generates a high collection priority.
2. A 78% bin with a 94% prediction becomes a predictive candidate.
3. A 40% → 99% jump is held for sensor verification.
4. Multiple high-priority bins are placed in a route plan.
5. Over-capacity demands are not assigned.
6. Incompatible waste/vehicle pairs are not assigned.
7. The dashboard can introduce a new critical bin and request replanning.
8. Route approval records the human decision and activates tracking.

Scenario detail is in [docs/test-scenarios.md](docs/test-scenarios.md). From `backend/`, run `python -m pytest tests -q`. The PostgreSQL round-trip test runs only when both `RUN_POSTGRES_INTEGRATION_TESTS=1` and a dedicated `TEST_DATABASE_URL` are explicitly set; it never uses `DATABASE_URL`.

## Datasets and configuration

The CSV files under [data](data) are synthetic reference data and are not loaded into production automatically. Local development uses `backend/.env.example`; Vercel uses `frontend/.env.example`. No external AI API key is required because no LLM integration is implemented.

## Render Deployment

Create a Render Web Service with root directory `backend`, build command `pip install -r requirements.txt`, and start command `uvicorn main:app --host 0.0.0.0 --port $PORT`. Create a Render PostgreSQL database and set its internal connection string as backend `DATABASE_URL`. Also configure `APP_ENV=production`, `AUTHENTICATION_SECRET` (a randomly generated value with at least 32 characters), `FRONTEND_ORIGIN` (the actual Vercel origin), and `ECO_ROUTE_SEED_DATA=false` in Render. Do not add credentials to source control or frontend settings.

Before starting the web service on a new/updated schema, open a Render Shell and run `alembic upgrade head` from the `backend` root with the production environment variables present. This is an explicit one-off migration, not an application-startup action. Verify `/health` and `/ready`. `/health` does not expose DB details; `/ready` returns 503 if DB connectivity or migration revision is missing.

## Vercel Deployment

Create a Vercel project with root directory `frontend`, Vite preset, install command `npm ci`, build command `npm run build`, and output directory `dist`. Set `VITE_API_BASE_URL` to the actual deployed Render backend origin, without a trailing slash. Set the same exact frontend origin as Render's `FRONTEND_ORIGIN`. Vite variables are embedded at build time; redeploy after changing them. The current frontend uses component state rather than URL routes, so no SPA rewrite is needed.

No Render/Vercel resources or URLs are configured by this repository. Production connectivity remains unverified until the owner creates those services and tests the deployed login and API flow.

## Container Development

```powershell
docker compose up --build
```

Compose runs the development SQLite configuration on port 8000. It is not a production PostgreSQL deployment.
