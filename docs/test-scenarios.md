# Acceptance Scenarios

| ID | Input / initial state | Expected and actual result | Agents involved | Automated status |
|---|---|---|---|---|
| TC-01 | BIN-001 at 92%, threshold 85% | High priority with threshold explanation | Monitoring, Forecast, Priority | Pass |
| TC-02 | BIN-006 at 78% with rising historical readings | Forecast crosses threshold; bin is high priority | Forecast, Priority | Pass |
| TC-03 | BIN-001 previous 92%, submitted 10% | 82-point jump requires verification; stored fill stays unchanged | Monitoring | Pass |
| TC-04 | Multiple priority bins across waste streams | Compatible stream routes are planned; no truck is double-booked | Priority, Fleet, Route, Reviewer | Pass |
| TC-05 | Estimated stream load exceeds available remaining capacity | No route is emitted for that stream; bins are listed as unassigned | Fleet, Route, Reviewer | Pass |
| TC-06 | Recyclable stream after the only compatible truck is assigned | BIN-003 remains unassigned; it is not added to a general/organic route | Fleet, Route | Pass |
| TC-07 | Register BIN-010 at 62%, submit 95%, run orchestration | Reading accepted; bin becomes critical and appears in a fresh route plan | Monitoring, Forecast, Priority, Route, Operations | Pass |
| TC-08 | Planned route approved, started, then completed | Route is verified; its bins become 0%; vehicle is released; volume enters recycling analytics | Operations, Reviewer, Tracking, Recycling | Pass |

These scenarios are covered by the backend test suite. From `backend/`, run `python -m pytest tests -q` after installing `requirements.txt`.

Deployment-safety regression coverage also verifies duplicate/out-of-order sensor readings, unauthorized API access, allowed CORS preflight, repeatable migrations, startup preservation of existing records, and PDF generation without route replanning. The PostgreSQL repository round-trip test is skipped by default. It requires both `RUN_POSTGRES_INTEGRATION_TESTS=1` and a dedicated, already-migrated `TEST_DATABASE_URL`; it never falls back to `DATABASE_URL` and does not drop tables.
