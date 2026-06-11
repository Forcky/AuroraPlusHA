# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## What this repo is

A Home Assistant custom integration (HACS-installable) that exposes Aurora Energy Tasmania (Aurora+) billing, usage, and Energy Dashboard data as HA sensors. The whole integration lives in `custom_components/aurora_energy/`. There is **no build system, no test suite, no linter config, and no Python package metadata** — it is pure HA integration code that runs inside HA's Python runtime.

## Validating changes

There is no automated test harness. The minimum verification loop is:

```bash
python3 -c "import ast; ast.parse(open('custom_components/aurora_energy/coordinator.py').read())"
```

Run that for every file you edit. For runtime testing, the integration must be loaded into a live Home Assistant instance — copy `custom_components/aurora_energy/` into HA's `config/custom_components/` and reload, then watch logs filtered by `custom_components.aurora_energy`.

If the MCP `home-assistant` server is configured in `.claude/settings.local.json` — prefer it (`ha_get_statistics`, `ha_get_logbook`, `ha_search_entities`) for inspecting live integration state instead of asking the user to fetch logs manually.

## Architecture

`__init__.py` → builds an `AuroraApiClient` and an `AuroraCoordinator`, performs first refresh, forwards to the `sensor` platform. Standard HA pattern.

### Three-layer split

- **`api.py`** — pure REST client. Handles the two-stage Azure B2C → Aurora token exchange, refresh-token rotation, and a `_get_with_retry` wrapper that auto-refreshes on 401. Token state is persisted back into the config entry via `_persist_tokens` so restarts don't require re-auth. Raises `AuthenticationError` (id_token rejected) and `TokenRefreshError` (refresh chain expired — triggers HA re-auth flow).
- **`coordinator.py`** — `DataUpdateCoordinator` that polls hourly. Fans out to multiple endpoints (`customers/current`, `usage/day`, `powerhour/upcoming-active`, `powerhour/all`, `usage/billing-period`, `payment/activepayment`). All non-primary fetches are wrapped in isolated `try/except` so a single failing endpoint doesn't break the whole update. Also performs **external statistics injection** (see below).
- **`sensor.py`** — declarative sensor list driven by `AuroraSensorEntityDescription` (extends HA's `SensorEntityDescription` with a `data_key` field). Plus one stateful `TariffPeriodSensor` that runs independently of the coordinator on UTC time-change listeners.

### Statistics injection — the most subtle part

The coordinator does two distinct things to feed HA's Energy Dashboard:

1. **Per-day backfill / append** (`_inject_statistics`) — idempotent per `(statistic_id, start_time)`. Marks each `date_key` in `_injected_dates` and persists to a `Store`, so each completed day is injected exactly once.
2. **Today's intraday data** (`_fetch_and_inject_today` / `_inject_today_statistics`) — re-injected on **every poll** using `index=0` (undocumented). Uses a *stable midnight base sum* (`_today_base_sums`, `_today_base_date`) captured once per Hobart-local day and persisted. **Do not** re-derive today's base from the recorder mid-day: the recorder will already contain today's partial rows from earlier polls and re-reading would inflate the cumulative sum on every restart. After backfill on first run, the base is seeded directly from the in-memory backfill totals (avoids a recorder commit race).

`StatisticData.sum` is a monotonically-increasing cumulative total; `StatisticData.state` is the per-period (hourly) value. All metadata in `_STAT_METADATA` uses `StatisticMeanType.NONE` + explicit `unit_class` (required for HA 2026.11 — the older `has_mean` bool was removed).

### API quirks that have already burned us

These are all documented in `API.md`; respect them when modifying coordinator logic:

- `GET /customers/current` returns a **list**, not an object — take `[0]`.
- `Premises` may include closed accounts (`IsActive: false`, `AccountStatus: "CLOST"`) with a stale `ServiceAgreementID` — always pick the active premise. The coordinator overwrites `client._service_agreement_id` from the active premise on every poll for this reason.
- `accessToken` from `/identity/LoginToken` is prefixed with `"bearer "` — strip before use.
- `Accept: application/json` and `User-Agent: python/auroraplus` headers are **required** on usage requests, otherwise records come back null.
- `NoDataFlag` is unreliable — use `_has_real_kwh_data()` to check actual record values instead of trusting the flag.
- `index=0` `StartDate` is a UTC timestamp representing midnight Hobart-local. Comparing the raw `YYYY-MM-DD` prefix to today's date silently fails during Hobart business hours (before 13:00–14:00 UTC). Always convert to `Australia/Hobart` first — see `_fetch_and_inject_today`.
- Power Hours datetimes are **naive Australia/Hobart** (no timezone suffix). Use `_parse_hobart_naive` to localize before converting to UTC.

### T93 tariff timezone — important

The `TariffPeriodSensor` and Aurora's T93 boundaries run on the **NEM clock = fixed AEST (UTC+10), no daylight saving**. The sensor uses `datetime.timezone(timedelta(hours=10))`, NOT `Australia/Hobart`. UTC time-change listeners fire at the fixed UTC hours that correspond to AEST boundaries (00, 06, 11, 14, 21). Do not "fix" this to use Hobart local time — the AEDT shift is intentional.

## Coordinator data shape

`coordinator.data` is a flat dict keyed by the `SENSOR_*` constants in `const.py`. Each entry in `SENSOR_DESCRIPTIONS` (sensor.py) maps a sensor to a `data_key` lookup in that dict. `AuroraSensor.native_value` converts booleans → `"active"`/`"inactive"` for ENUM sensors. Statistics use a separate `STAT_ID_*` namespace (`aurora_energy:<name>`) and don't appear in `coordinator.data`.

## Editing notes

- `manifest.json` `version` field must be bumped for HACS to surface an update.
- `iot_class` is `cloud_polling` and `dependencies: ["recorder"]` is required for `async_add_external_statistics` to work.
- The `Store` key (`{DOMAIN}_{entry.entry_id}_backfill`) holds `injected_dates`, `today_base_sums`, and `today_base_date`. Wiping it forces a fresh backfill — README documents this for users when new statistics are added.
- `strings.json` controls config-flow UI text; update it alongside any `config_flow.py` change that adds a new step or error key.

## Keeping docs in sync

`README.md` and `API.md` are the only user-facing docs. **Always update `README.md` in the same commit as any code change that affects user-visible behaviour.** Do not leave it as a follow-up — if a future commit message says "docs: update README" it means the previous commit shipped with stale docs.

**Update `README.md` whenever you:**
- Add, remove, or rename a sensor → update the sensor table and the "Disabled by default" table if applicable
- Add a new external statistic ID → update the Energy Dashboard statistics table
- Add a statistic that existing installs won't auto-backfill → add a "Note for existing installs" with the `.storage/aurora_energy_<entry_id>_backfill` wipe instructions
- Change data refresh cadence or polling behaviour → update the Data availability table and any relevant notes
- Change tariff handling, peak/off-peak schedule, or a Power Hours state value
- Change the auth flow or setup steps
- Bump the minimum HA version or hit a deprecation cutover → add a compatibility note
- Change any troubleshooting advice that is no longer accurate

**Update `API.md` when:**
- Discovering new fields, response shapes, or undocumented behaviour in the Aurora REST API
- Hitting a new API quirk → add it to the "Known quirks" table AND the relevant endpoint section
- Adding integration support for a new endpoint
- Confirming or invalidating a previously-noted assumption

**Skip docs updates only for:** pure internal refactors with no user-visible effect (e.g. renaming a private variable, extracting a helper function).

## Reference docs in repo

- `API.md` — exhaustive reverse-engineered REST API reference. Read it before adding a new endpoint integration.
- `README.md` — user-facing docs including sensor table, tariff schedule, and troubleshooting.
- `aurora_energy_dashboard.yaml` — example HA dashboard YAML using the integration's sensors and statistics.
