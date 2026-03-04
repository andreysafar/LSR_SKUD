# ANPR Integration — Summary and Next Steps

## What Was Done

Integration of ANPR batch processing into LSR_SKUD is implemented in the branch **`feature/anpr-batch-processing`**. All changes are in `/home/safar/Project/LSR_SKUD`; the ANPR folder was not modified.

### Implemented

1. **Config** — `config/anpr_config.py`, ANPR settings in `config.py` (dataclasses + env).
2. **Database** — `db/anpr_schema.py`, `db/anpr_integration.py` (sessions, results, metrics).
3. **Batch processing** — `batch_processing/`: `ModernAnalysisWorker`, `ModernBatchProcessor`, DB integration, optional fallback to legacy.
4. **Web UI** — `pages/batch_processing.py`, navigation in `app.py` (Batch Processing, Analytics).
5. **Monitoring** — `monitoring/batch_metrics.py` (system/GPU/processing metrics).
6. **Analytics** — `analytics/batch_analytics.py` (timeline, performance, directories).
7. **Tests** — `tests/integration/test_anpr_integration.py`, `benchmarks/anpr_performance.py`, `pytest.ini`, `Makefile`.
8. **Deploy** — `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `deploy/production.yaml`, `deploy/deploy.sh`, `.env.example`.
9. **Docs** — `docs/architecture.md`, `docs/user_guide.md`, `deploy/README.md`, root `README.md`.

### What Was Not Started by This Task

- No Streamlit server was started.
- No `docker-compose up` was run.
- No batch daemon was started.
- Only file edits and git commits were performed.

Your existing Docker (Postgres, Redis, Grafana, etc.) was not touched.

---

## Important: Health Checks and Proxy/Monitoring

Previously, health checks caused issues with your proxy/monitoring. To avoid that:

### 1. Dockerfile

The image has a `HEALTHCHECK` that calls `curl ... /_stcore/health`. If that goes through a proxy and causes problems:

- **Option A:** Build without health check:
  ```dockerfile
  # In Dockerfile, comment out or remove the HEALTHCHECK block:
  # HEALTHCHECK --interval=30s ...
  ```

- **Option B:** Build with build-arg to disable:
  ```dockerfile
  ARG DISABLE_HEALTHCHECK=false
  RUN if [ "$DISABLE_HEALTHCHECK" != "true" ]; then ...
  ```
  Then: `docker build --build-arg DISABLE_HEALTHCHECK=true ...`

### 2. docker-compose.yml

The `lsr-skud` service has:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
  ...
```

- **Disable for local/proxy:** set `disable: true`:
  ```yaml
  healthcheck:
    disable: true
  ```

- Or remove the `healthcheck` section for this service.

### 3. Kubernetes (deploy/production.yaml)

There are `livenessProbe` and `readinessProbe` on the app (HTTP GET to `/_stcore/health`). If the cluster uses a proxy and these cause issues:

- Remove or comment out `livenessProbe` and `readinessProbe` for the app, or
- Point them to a different endpoint that does not go through the problematic proxy.

Recommendation: disable or relax health checks until you finish testing and fix proxy/monitoring; then re-enable and tune intervals/paths as needed.

---

## Your Next Steps (Testing)

### 1. Repo and branch

```bash
cd /home/safar/Project/LSR_SKUD
git status
git branch   # should see feature/anpr-batch-processing
git checkout feature/anpr-batch-processing   # if not already
```

### 2. Dependencies

```bash
# If using uv
uv sync --all-extras

# Or pip from pyproject.toml
pip install -e ".[test]"
```

### 3. Run tests (no servers, no health checks)

```bash
# Unit/integration (no GPU required for most)
make test
# or
pytest tests/ -v -m "not gpu"

# Optional: coverage
make test-coverage
```

### 4. Run app locally (when you’re ready)

```bash
# From LSR_SKUD root
uv run streamlit run app.py
# Or: python -m streamlit run app.py
```

Then open http://localhost:8501 and use **Batch Processing** and **Analytics** from the sidebar.

To stop: `Ctrl+C` in the terminal where Streamlit is running.

### 5. Docker (optional; adjust health check first)

Before `docker-compose up`:

- In `docker-compose.yml`, set `healthcheck: disable: true` for `lsr-skud` (see above).

Then:

```bash
cd /home/safar/Project/LSR_SKUD
docker-compose build
docker-compose up -d
```

To stop:

```bash
docker-compose down
```

### 6. Batch processing (CLI, when ready)

```bash
cd /home/safar/Project/LSR_SKUD
./batch_processing/manage_videos.sh start /path/to/video/dirs
./batch_processing/manage_videos.sh status
./batch_processing/manage_videos.sh stop
```

### 7. Merge to main (after testing)

```bash
cd /home/safar/Project/LSR_SKUD
git checkout main
git merge feature/anpr-batch-processing
git push origin main   # if remote exists
```

---

## Quick Reference: What to Stop

| What you started        | How to stop                          |
|-------------------------|--------------------------------------|
| Streamlit (local)       | `Ctrl+C` in its terminal             |
| docker-compose          | `docker-compose down`                |
| Batch daemon (manage_videos.sh) | `./batch_processing/manage_videos.sh stop` |

---

## Files to Adjust for Your Proxy/Monitoring

- **Dockerfile** — `HEALTHCHECK` (comment out or remove if needed).
- **docker-compose.yml** — `healthcheck` for service `lsr-skud` (disable or remove).
- **deploy/production.yaml** — `livenessProbe` and `readinessProbe` (remove or change).

After you’re back, you can continue from “Your Next Steps (Testing)” and, if you want, we can apply the health-check changes in the repo for you.