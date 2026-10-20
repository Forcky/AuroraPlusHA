# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## What this repo is

A Home Assistant custom integration (HACS-installable) that exposes Aurora Energy Tasmania (Aurora+) billing, usage, and Energy Dashboard data as HA sensors. The whole integration lives in `custom_components/aurora_energy/`. There is **no build system, no test suite, no linter config, and no Python package metadata** — it is pure HA integration code that runs inside HA's Python runtime.

## Validating changes

CI runs the HACS action and hassfest on every push and PR (`.github/workflows/validate.yml`), plus daily — the schedule exists because several HACS checks are repository-level (topics, description, licence, brands) and no commit would otherwise re-evaluate them. Both must stay green; they gate inclusion in the HACS default store. Note hassfest's two easily-tripped rules: `manifest.json` keys must be ordered `domain`, `name`, then alphabetical, and **no translation string may contain a literal URL** — pass URLs through `description_placeholders` instead (see `redirect_url` in `config_flow.py`).

There is no automated test harness. The minimum local verification loop is:

```bash
python3 -c "import ast; ast.parse(open('custom_components/aurora_energy/coordinator.py').read())"
```

Run that for every file you edit. For runtime testing, the integration must be loaded into a live Home Assistant instance — copy `custom_components/aurora_energy/` into HA's `config/custom_components/` and reload, then watch logs filtered by `custom_components.aurora_energy`.

If the MCP `home-assistant` server is configured in `.claude/settings.local.json` — prefer it (`ha_get_statistics`, `ha_get_logbook`, `ha_search_entities`) for inspecting live integration state instead of asking the user to fetch logs manually.

## Architecture

`__init__.py` → builds an `AuroraApiClient` and an `AuroraCoordinator`, performs first refresh, forwards to the `sensor` platform. Standard HA pattern.

### Three-layer split

- **`api.py`** — pure REST client. Handles the two-stage Azure B2C → Aurora token exchange, refresh-token rotation, and a `_get_with_retry` wrapper that auto-refreshes on 401. Every GET is serialised through `_request_lock`, because Aurora returns hour-shifted `/usage/day` values for overlapping requests. **Never** parallelise API calls (e.g. `asyncio.gather` over indexes), even though HA's startup runs the poll and the reconcile concurrently. Token state is persisted back into the config entry via `_persist_tokens` so restarts don't require re-auth. Raises `AuthenticationError` (id_token rejected), `TokenRefreshError` and `AuroraApiError`. `TokenRefreshError` means the refresh endpoint answered 401/403, or that no token is stored at all; it is the **only** thing that may trigger HA's re-auth flow. With no access token held, `_get_with_retry` first calls `_ensure_access_token` under `_request_lock`. That refreshes if a refresh token or cookie is stored, otherwise logs in with a non-empty id_token, otherwise raises `TokenRefreshError`. Runtime clients have no id_token (none is stored since 1.0.1), so **never post an empty id_token** to LoginToken. Any other refresh failure raises `AuroraApiError`: a network error, timeout, 5xx, non-JSON body (maintenance page) or a 200 with no access token. The coordinator turns that into `UpdateFailed`, which is retried at the next poll (`ConfigEntryNotReady` on first refresh). A failed refresh or login must never change or persist token state, and never persist a `None` access token.
- **`coordinator.py`** — `DataUpdateCoordinator` that polls hourly. Fans out to multiple endpoints (`customers/current`, `usage/day`, `powerhour/upcoming-active`, `powerhour/all`, `usage/billing-period`, `payment/activepayment`). All non-primary fetches are wrapped in isolated `try/except` so a single failing endpoint doesn't break the whole update. Also performs **external statistics injection** (see below).
- **`sensor.py`** — declarative sensor list driven by `AuroraSensorEntityDescription` (extends HA's `SensorEntityDescription` with a `data_key` field). Plus one stateful `TariffPeriodSensor` that runs independently of the coordinator on UTC time-change listeners.

### Statistics injection — the most subtle part

The coordinator does two distinct things to feed HA's Energy Dashboard:

1. **Per-day backfill / append** (`_inject_statistics`) — idempotent per `(statistic_id, start_time)`. Marks each `date_key` in `_injected_dates` and persists to a `Store`, so each completed day is injected exactly once. A day counts as completed only when `_is_day_complete()` holds: every Hour record has non-null `KilowattHourUsage`. `_has_real_kwh_data()` alone is not enough, because during AEDT a day's first hour arrives a day before the rest (#17). Every injection starts from `_get_sums_before(day_start)`, never from the recorder's last row: that last row may be today's partial or future rows. Each poll goes through `_inject_recent_days`. It injects yesterday (index=-1), and fetches index=-2 only when that day's local date is missing from `injected_dates`, i.e. Aurora delivered it late. Once index=-2 is injected, yesterday is re-injected on top of it so the sums stay continuous; `mark_injected=False` is used if yesterday isn't complete yet. That check is skipped until the startup reconcile has finished, since the reconcile covers index=-2 itself.
2. **Today's intraday data** (`_fetch_and_inject_today` / `_inject_today_statistics`) — re-injected on **every poll** using `index=0` (undocumented). Uses a *stable midnight base sum* (`_today_base_sums`, `_today_base_date`) captured once per Hobart-local day and persisted. The base is the recorder's sum *before* today's midnight (`_get_sums_before`). **Never** use the last row overall: it already holds today's partial rows from earlier polls and would inflate the base. When yesterday is injected (by the poll or by the startup reconcile), `_seed_today_base_if_yesterday` overwrites the base with the in-memory closing sums. That avoids a recorder commit race, since during AEDT yesterday's completion and today's first hour arrive in the same delivery. Today is skipped until the startup reconcile has finished. The reconcile then rewrites today straight away, so a repaired history doesn't leave today on a stale base until the next hourly poll.

**Generated per-tariff statistics.** Both paths write the named statistics in `_STAT_METADATA` (total, T31, T41, T93PEAK, T93OFFPEAK, T140 solar) for every hour, whatever the account's tariffs; they must stay byte-for-byte unchanged. Any other key in the hourly `KilowattHourUsage` (not `Total`, and not `Other`, the dollars-only supply charge) gets `aurora_energy:<slugified key>_kwh` / `_dollars`, built by `_tariff_metadata` and resolved by `_extra_stat_ids`. A key whose IDs fail `valid_statistic_id` or clash with another statistic is skipped with one warning per run. A generated statistic gets rows only on days its key appears in that day's Hour records (0 for the hours it is absent), so a tariff that leaves the account stops getting rows instead of writing zeros forever. The rules that keep its sums continuous:

- Every chain (`_inject_recent_days`, `_reconcile_history`) passes the generated IDs of all its days to `_get_sums_before`, and the chain's in-memory sums carry them. The seeded base therefore includes a tariff that only appeared in an earlier day of the chain.
- Today's base may lack a generated ID: the tariff is new since the base was taken, it was absent yesterday (e.g. a weekday-only tariff on a Monday), or the base was saved by a version before 1.1.0. `_inject_today_statistics` then fills only those IDs from `_closing_sums_before(midnight)` and persists the base. **Never** fill them with 0, and never with a bare recorder read. `_closing_sums_before` takes the later of two rows: the last row this run queued for the statistic (`_queued_rows`, recorded by `_submit_statistics` for past days only) and the last row the recorder has committed before midnight. Any row the recorder might not have committed yet was queued by this run, so it is in `_queued_rows`. Anything else was committed by an earlier run, so that read cannot race.
- The named statistics keep their existing paths, including `setdefault(0.0)` for a named ID missing from the base. The generated-ID code adds no awaits when an account has no other tariffs.

`StatisticData.sum` is a monotonically-increasing cumulative total; `StatisticData.state` is the per-period (hourly) value. All metadata in `_STAT_METADATA`, and the generated metadata, uses `StatisticMeanType.NONE` + explicit `unit_class` (required for HA 2026.11 — the older `has_mean` bool was removed).

### API quirks that have already burned us

These are all documented in `API.md`; respect them when modifying coordinator logic:

- `GET /customers/current` returns a **list**, not an object — take `[0]`.
- `Premises` may include closed accounts (`IsActive: false`, `AccountStatus: "CLOST"`) with a stale `ServiceAgreementID` — always pick the active premise. The coordinator overwrites `client._service_agreement_id` from the active premise on every poll for this reason.
- `accessToken` from `/identity/LoginToken` is prefixed with `"bearer "` — strip before use.
- `Accept: application/json` and `User-Agent: python/auroraplus` headers are **required** on usage requests, otherwise records come back null.
- `NoDataFlag` is unreliable — use `_has_real_kwh_data()` to check actual record values instead of trusting the flag.
- `index=0` `StartDate` is a UTC timestamp representing midnight Hobart-local. Comparing the raw `YYYY-MM-DD` prefix to today's date silently fails during Hobart business hours (before 13:00–14:00 UTC). Always convert to `Australia/Hobart` first with `_hobart_date(date_key, self._tz)` — see `_fetch_and_inject_today`.
- Meter data is delivered per **AEST/NEM day**, but `/usage/day` records cover the **local** day. Undelivered hours carry `KilowattHourUsage: null`. During AEDT the local day's first hour lands a day early, and `SummaryTotals` (also AEST-day) is out by one hour from the Hour records. So never use it to test completeness (#17).
- `SummaryTotals.KilowattHourUsage.Total` **includes T140 solar export** at the day level, so it is not consumption. Use `_consumption_kwh()`, which sums every tariff except T140 and `Total` and returns None when there are none. Never fall back to `Total`. The dollar `Total` is the net cost (supply charge in, solar credit out) and is used as-is.
- Power Hours datetimes are **naive Australia/Hobart** (no timezone suffix). Use `_parse_hobart_naive` to localize before converting to UTC.

### T93 tariff timezone — important

The `TariffPeriodSensor` and Aurora's T93 boundaries run on the **NEM clock = fixed AEST (UTC+10), no daylight saving**. The sensor uses `datetime.timezone(timedelta(hours=10))`, NOT `Australia/Hobart`. UTC time-change listeners fire at the fixed UTC hours that correspond to AEST boundaries (00, 06, 11, 14, 21). Do not "fix" this to use Hobart local time — the AEDT shift is intentional.

## Coordinator data shape

`coordinator.data` is a flat dict keyed by the `SENSOR_*` constants in `const.py`. Each entry in `SENSOR_DESCRIPTIONS` (sensor.py) maps a sensor to a `data_key` lookup in that dict. `AuroraSensor.native_value` converts booleans → `"active"`/`"inactive"` for ENUM sensors. Statistics use a separate `STAT_ID_*` namespace (`aurora_energy:<name>`), plus the generated `aurora_energy:<tariff>_kwh` / `_dollars` IDs, and don't appear in `coordinator.data`.

## Editing notes

- **Every user-visible change ships as a version.** Bump `manifest.json` `version` in the same commit, then publish a matching GitHub release once the change is pushed: `gh release create vX.Y.Z --target main --title "vX.Y.Z — <summary>" -F <notes>`. HACS reads *releases*, not commits — a bumped manifest with no tagged release means no HACS user ever receives the change. Tags are `vX.Y.Z`, release titles are `vX.Y.Z — <short summary>`, and notes follow the established shape: `## Fixed` / `## Upgrading` (say "nothing to do" when there is nothing to do) / `## Changes` (per-file) / a `compare/` link to the previous tag.
- Never leave `main` with a manifest version that has no corresponding release. Check with `gh release list` before finishing.
- **Never construct `zoneinfo.ZoneInfo` in coordinator or sensor code.** The first construction reads tzdata from disk, which blocks the event loop; HA logs a blocking-call warning, and the HACS default-store review rejected the integration for it. `async_setup_entry` resolves Australia/Hobart once with `await dt_util.async_get_time_zone(TZ_HOBART)` and passes it to the coordinator as `self._tz`; use that. A fixed offset such as the T93 sensor's `datetime.timezone(timedelta(hours=10))` reads nothing from disk and is fine.
- `iot_class` is `cloud_polling` and `dependencies: ["recorder"]` is required for `async_add_external_statistics` to work.
- The `Store` key (`{DOMAIN}_{entry.entry_id}_backfill`) holds `injected_dates` (saved sorted, for readability only), `today_base_sums` (named and generated statistic IDs), and `today_base_date`. Wiping it forces a fresh backfill — README documents this for users when new statistics are added. Note that every restart already re-injects the last 7 days regardless of `injected_dates`.
- `strings.json` controls config-flow UI text; update it alongside any `config_flow.py` change that adds a new step or error key.
- `blueprints/automation/aurora_energy/` holds the notification blueprints that the README's import buttons fetch from `main`. They hard-code the Power Hour Status values, the T93 period states and the default `sensor.aurora_energy_*` entity IDs, so change them in the same commit as any rename or state-value change. An automation triggered by one coordinator sensor starts before the other sensors from that update have been written. That is why the Power Hour blueprint delays 1 s before building its message and holds its reminder trigger `for` 5 s, and why the tariff blueprint waits for the period-end sensor.

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
