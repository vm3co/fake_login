# TSB-016 isolated audits

These are explicit audit scripts, not automatically collected pytest tests.
Never mount this server into production or publish its port. `/audit/remote`
is deliberately unauthenticated and must only exist on an internal test network.

## Environment

- Use a clean candidate export for `/app`, not the dirty workspace.
- Build its frontend first. The candidate includes the separately validated
  `get_mtmpl_task_filters` route and the three baseline test corrections.
- Internal Docker network: `tsb016-e2e-net`, with no published ports.
- PostgreSQL container/host: `tsb016-e2e-postgres`, database `tsb_schema_test`,
  user `tsb_test`, password `tsb_test_only`, tmpfs PGDATA.
- Redis container/host: `tsb016-e2e-redis`, persistence disabled, dedicated data.
- API image: `fake_login-admin-app`; mount candidate adminapp read-only at
  `/app`, this directory at `/audit`, writable tmpfs `/app/Logger` and
  `/app/ai_logs`. Set `PYTHONPATH=/app:/audit`, `PYTHONDONTWRITEBYTECODE=1`,
  `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
  `REDIS_HOST` to the isolated values above.
- Test-only login environment: `ADMIN_EMAIL=audit@example.test`,
  `ADMIN_PASSWORD=audit-test-only`, `JWT_SECRET_KEY=isolated-audit-only`.
- Run `python -m uvicorn tsb016_server:app --host 0.0.0.0 --port 5186`.
  The server verifies dedicated host/database names before creating tables.
  It uses real JWT/authentication, SQL APIs, sync core and JobQueue; only the
  remote reader is controlled. It does not run production lifespan/schedulers.

## Order

Start with fresh isolated database and Redis containers. Wait for API startup
completion in its log, then run scripts in this order on the same network:

1. `tsb016_browser.py`: A update, missing backup, B import, C direct recreation,
   historical Excel, mobile view, same-org deletion preserving B/C.
2. `tsb016_access.py`: actual login roles, backup API authorization matrix,
   same-org UI reconstruction check and refresh.
3. `tsb016_jobs.py`: partial result and cancellation after one confirmed commit.
4. `tsb016_events.py`: actual trigger Redis BLPOP worker; late A/B events do not
   change C/history. Uses before/after comparisons and can be rerun.
5. `tsb016_timezones.py`: Chromium UTC/Taipei/New York date boundaries and
   mobile backup view.
6. `tsb016_mobile.py`: actual mobile search/import UI, real background jobs,
  cross-page backup selection, cancel/confirm check, export and delete.
  Run once after the preceding flows on fresh fixtures; it creates eleven
  mobile-task history versions through actual sync jobs.

Browser image includes Python Playwright, Chromium and openpyxl. Example:

```sh
docker run --rm --network tsb016-e2e-net \
  --mount type=bind,src="$AUDITS",dst=/audit,readonly \
  --mount type=bind,src="$CANDIDATE/adminapp",dst=/app,readonly \
  --entrypoint python fake_login-admin-app /audit/tsb016_timezones.py
```

The browser workflow writes screenshots to `/audit`; use a disposable writable
copy of the scripts for that workflow, not the source directory. Do not commit
screenshots or synthetic login tokens. Event audit instead mounts candidate
`triggerapp` at `/app`, sets the same isolated POSTGRES/REDIS environment,
`PYTHONPATH=/app`, and writable Logger tmpfs. It must run after the other flows
because it intentionally appends an event to current C. Do not reset production
schemas or flush Redis. Remove only these named test containers/network after
the audit.

## Limits

The reader is a fixture, not a real SE2 HTTP endpoint. SE2 parsing/strict read
failures and PostgreSQL concurrency/rollback are covered by separate pytest
tests. These scripts do not authorize deployment, run migrations on business
data, or test all mobile actions merely because the viewport changes midway.
Historical request races retain their separate 014 evidence. The events audit
now includes the actual trigger HTTP ASGI route before Redis/worker persistence.
Run pytest migration/schema regressions against a separate empty PostgreSQL
instance: their unqualified to_regclass assertions can otherwise see public
tables belonging to this E2E server. Record commands/results in the TSB-016 ticket.