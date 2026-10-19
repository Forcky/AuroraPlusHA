# Aurora Energy Tasmania (Aurora+) — Home Assistant Integration

A custom Home Assistant integration that pulls your Aurora Energy Tasmania billing and usage data into Home Assistant sensors and the Energy Dashboard.

## What it does

- Estimated and actual balance, amount owed, unbilled amount, next bill date
- Daily energy usage (kWh) and cost
- Solar feed-in (kWh exported and earnings)
- Real-time T93 tariff period sensor (`peak` / `off_peak`), DST-correct
- Power Hours demand-response program sensors (status, timeslot, savings)
- Billing period totals (cumulative kWh and cost for the current billing cycle)
- Historical statistics for the Energy Dashboard (backfills up to 7 days on every HA restart to cover gaps; today's partial hourly data updated each poll)
- Polling aligned to the clock hour — sensors update within seconds of Aurora+ events rather than up to 59 minutes late
- [Notification blueprints](#notification-blueprints) for Power Hours and T93 peak/off-peak changes

---

## Prerequisites

- Home Assistant 2025.11 or later
- An Aurora Energy Tasmania account with Aurora+ access

---

## Installation

### Option 1 — HACS (Recommended)

1. In Home Assistant, open **HACS**
2. Click the three-dot menu (⋮) → **Custom repositories**
3. Add `https://github.com/Forcky/AuroraPlusHA` with category **Integration**
4. Click **Add**
5. Search for **Aurora Energy Tasmania** in HACS and click **Download**
6. Restart Home Assistant
7. Go to **Settings → Devices & Services → Add Integration**
8. Search for **Aurora Energy Tasmania**
9. Click the **Log in to Aurora+** link that appears, log in (tick **Keep me logged in**), then copy the full URL from your browser's address bar and paste it into Home Assistant

HACS will notify you of future updates so you can update with a single click.

---

### Option 2 — Manual installation

1. Copy the `aurora_energy` folder into your HA `config/custom_components/` directory:
   ```
   config/
   └── custom_components/
       └── aurora_energy/
           ├── __init__.py
           ├── api.py
           ├── config_flow.py
           ├── const.py
           ├── coordinator.py
           ├── manifest.json
           └── sensor.py
   ```
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration**
4. Search for **Aurora Energy Tasmania**
5. Click the **Log in to Aurora+** link, log in (tick **Keep me logged in**), copy the full URL from your browser's address bar, and paste it into Home Assistant

If setup succeeds, a device called **Aurora Energy** will appear with all sensors populated. Its serial number is the service agreement ID of your active Aurora+ premise.

---

## Sensors

| Sensor | Description | Unit |
|--------|-------------|------|
| Estimated Balance | Current account balance | AUD |
| Actual Balance | Account balance as at Aurora's last daily update (see **Balance Last Updated**). **Estimated Balance** is the figure the Aurora+ app shows as *Balance* | AUD |
| Amount Owed | Outstanding amount due | AUD |
| Unbilled Amount | Charges not yet on a bill | AUD |
| Average Daily Usage | Average daily spend | AUD |
| Bill Total Amount | Most recent bill total | AUD |
| Usage Days Remaining | Days remaining in billing period | d |
| Daily Total Usage | Previous day's consumption from the grid, all tariffs except solar export | kWh |
| Daily Total Cost | Previous day's net cost as Aurora reports it: energy plus the daily supply charge, minus the solar feed-in credit | AUD |
| Solar Feed-in | Previous day's solar export | kWh |
| Solar Feed-in Earnings | Previous day's solar feed-in credit | AUD |
| T93 Tariff Period | Current tariff period: `peak` or `off_peak` | — |
| Power Hour Status | Current Power Hours state (see below) | — |
| Power Hour Event | Name of the upcoming or active Power Hours event | — |
| Power Hour Start | Start of your accepted timeslot; before you book, start of the earliest offered slot | — |
| Power Hour End | End of your accepted timeslot; before you book, end of the latest offered slot | — |
| Power Hour Selection Deadline | Deadline to select a timeslot | — |
| Power Hour First Slot Start | Start of the earliest timeslot you can still book — book before this to get first pick | — |
| Power Hour Total Savings | Lifetime savings from Power Hours events | AUD |
| Billing Period Usage | kWh consumed from the grid in the current billing cycle, all tariffs except solar export | kWh |
| Billing Period Cost | Net cost of the current billing cycle as Aurora reports it, including supply charges and the solar credit | AUD |
| Billing Period Solar Feed-in | Total solar exported in current billing cycle | kWh |
| Billing Period Solar Earnings | Total solar feed-in credit in current billing cycle | AUD |
| Bill Due Date | Date the current bill is due | — |
| Next Bill Date | When Aurora+ next issues a bill | — |
| Overdue Amount | Amount currently overdue | AUD |
| Unpaid Bills | Count of unpaid bills | — |

**Power Hour Status values:**

| Value | Meaning |
|-------|---------|
| `no_event` | No upcoming Power Hours event |
| `selection_pending` | An event has been announced but you haven't selected a timeslot yet — act before the **Selection Deadline**. **Power Hour Start/End** show the overall bookable window (earliest offered slot start → latest offered slot end), and **Power Hour First Slot Start** shows the next slot you can still book |
| `confirmed` | You've accepted a timeslot — free electricity starts at **Power Hour Start** and ends at **Power Hour End** |
| `active` | Your Power Hours timeslot is currently running — electricity is free right now |

> **Dashboard tip:** to show "Power Hours available — book before X", combine **Power Hour First Slot Start** with **Power Hour Selection Deadline** while status is `selection_pending`. Individual slots close ~5 minutes before they start, so the first-slot sensor advances to the next bookable slot as earlier ones lapse (refreshed on the hourly poll).

> **Note:** Aurora often has several events open at once — a long-running offer announced weeks ago alongside this weekend's. The Power Hour sensors always describe the single most relevant event: one that is running right now, otherwise the soonest timeslot you have booked, otherwise the open offer whose next bookable slot comes first. Events whose offer has closed and whose booked slot has finished are ignored. (Before 1.0.11 the integration simply used the first event in Aurora's response, which is ordered by announcement date — a stale offer could mask an event you had already booked.)

> **Note:** The coordinator evaluates the start and end timestamps on every poll and sets the status to `active` directly — your dashboard can use a simple `condition: state` check rather than comparing timestamps in a template. Because polling is aligned to the clock hour, status transitions are reflected within ~5 seconds of the event start or end time.

### Disabled by default

The following sensors exist but are disabled by default. Enable them via **Settings → Devices → Aurora Energy → entities** if needed.

| Sensor | Description | Relevant for |
|--------|-------------|-------------|
| T31 General Usage | T31 tariff consumption (kWh) | T31 flat-rate accounts |
| T31 General Cost | T31 tariff cost (AUD) | T31 flat-rate accounts |
| T41 Heating Usage | T41 tariff consumption (kWh) | T41 controlled load accounts |
| T41 Heating Cost | T41 tariff cost (AUD) | T41 controlled load accounts |
| T93 Peak Usage | T93 peak tariff consumption (kWh) | T93 time-of-use accounts |
| T93 Peak Cost | T93 peak tariff cost (AUD) | T93 time-of-use accounts |
| T93 Off-Peak Usage | T93 off-peak tariff consumption (kWh) | T93 time-of-use accounts |
| T93 Off-Peak Cost | T93 off-peak tariff cost (AUD) | T93 time-of-use accounts |
| T93 Tariff Period End | When the current T93 tariff period ends (peak or off-peak boundary) | T93 accounts |
| Unread Notifications | Number of unread Aurora+ notifications | All accounts |
| Direct Debit | Whether a direct debit arrangement is active (`active`/`inactive`) | All accounts |
| Auto Payment | Whether auto-payment (card) is configured (`active`/`inactive`) | All accounts |
| Balance Last Updated | When Aurora+ last updated **Actual Balance** (diagnostic) | All accounts |

---

## Notification blueprints

Two automation blueprints turn the sensors above into notifications. Click a button to import one into Home Assistant (or go to **Settings → Automations & scenes → Blueprints → Import blueprint** and paste the file's URL), then create an automation from it.

### Power Hour notifications

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FForcky%2FAuroraPlusHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Faurora_energy%2Fpower_hour.yaml)

Notifies you when:

- Aurora+ offers a new Power Hour (**Power Hour Status** changes to `selection_pending`)
- the selection deadline is within your chosen lead time (default 1 day) and you still haven't booked a slot
- your Power Hour starts (`active`), and when it ends

You pick the **Power Hour Status** and **Power Hour Selection Deadline** sensors, the reminder lead time and the notification action. Messages include the event name, the offered slots, the earliest slot you can still book and the deadline, read from the other Power Hour sensors. Those are in a collapsed *Sensors used in messages* section, pre-filled with the integration's entity IDs; change them only if you renamed the entities. Status changes arrive with the hourly poll, so start and end notifications come within seconds of the hour. A status that drops to `unavailable` for a failed poll or a restart doesn't trigger anything.

### T93 tariff period notifications

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FForcky%2FAuroraPlusHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Faurora_energy%2Ftariff_period.yaml)

Notifies you when the **T93 Tariff Period** sensor switches between `peak` and `off_peak` (both by default, or just one). If you enable the **T93 Tariff Period End** sensor (disabled by default), the message also says when the new period ends, for example *Off-peak pricing has started and runs until 08:00 tomorrow.* Times are local, so during daylight saving they are an hour later than the AEST schedule in [Tariff notes](#t93-peakoff-peak-schedule).

### Notification action

Both blueprints default to a notification in Home Assistant itself. Each new notification replaces the previous one from the same blueprint. To send them to your phone instead, replace the action with, for example:

```yaml
- action: notify.mobile_app_your_phone
  data:
    title: "{{ title }}"
    message: "{{ message }}"
```

The blueprints also provide `notification_type` (Power Hour: `offer`, `reminder`, `start` or `end`) and `period` (tariff: `peak` or `off_peak`) if you want to handle them differently.

---

## Energy Dashboard

The integration injects hourly statistics into the HA recorder, which can be used directly in the **Energy Dashboard**.

On every HA startup it checks the last 7 days and injects any that are missing from the recorder — this means gaps caused by downtime or broken authentication are automatically recovered after a restart. Each new completed day's records are injected once Aurora has delivered every hour of it (typically 8–9am AEST the next morning). If Aurora delivers a day late, by up to about two days, it is picked up on the next hourly poll without a restart. Anything later than that is recovered by the next restart. The integration also attempts to fetch today's in-progress hourly data on every poll — if the API returns it, the current day's bars will update hourly throughout the day.

**Daylight saving (Oct–Apr):** Aurora delivers meter data in fixed AEST days, so during AEDT the 00:00–01:00 hour of each local day arrives a day before the rest. From 1.0.13 the previous day is only recorded once all of its hours are in, so between midnight and the morning delivery the Energy Dashboard shows yesterday's first hour only. This fills in on its own. Versions 1.0.12 and earlier recorded the day at that point and never revisited it ([#17](https://github.com/Forcky/AuroraPlusHA/issues/17)).

To add to the Energy Dashboard:
1. Go to **Settings → Dashboards → Energy**
2. Under **Electricity grid**, add:
   - **Grid consumption:** `aurora_energy:total_kwh`
3. Under **Solar panels**, add:
   - **Energy production:** `aurora_energy:solar_feedin_kwh`
   - **Return to grid:** `aurora_energy:solar_feedin_kwh`

The following additional statistics are available for use in custom dashboard cards:

| Statistic ID | Description |
|-------------|-------------|
| `aurora_energy:total_kwh` | Total daily consumption |
| `aurora_energy:solar_feedin_kwh` | Solar feed-in (exported) |
| `aurora_energy:t93peak_kwh` | T93 peak consumption |
| `aurora_energy:t93offpeak_kwh` | T93 off-peak consumption |
| `aurora_energy:t31_kwh` | T31 general consumption |
| `aurora_energy:t41_kwh` | T41 heating consumption |
| `aurora_energy:total_dollars` | Total energy cost (excludes daily supply charge) |
| `aurora_energy:t31_dollars` | T31 general tariff cost |
| `aurora_energy:t41_dollars` | T41 heating tariff cost |
| `aurora_energy:t93peak_dollars` | T93 peak tariff cost |
| `aurora_energy:t93offpeak_dollars` | T93 off-peak tariff cost |
| `aurora_energy:solar_feedin_dollars` | Solar feed-in earnings |

Aurora's API only exposes dollar values at the day level, so per-hour cost statistics are produced by distributing each tariff's day total across hours weighted by that hour's share of the day's kWh for the same tariff.

> **Note for existing installs:** The per-tariff `*_dollars` statistics (`t31_dollars`, `t41_dollars`, `t93peak_dollars`, `t93offpeak_dollars`) and the corrected `total_dollars` / `solar_feedin_dollars` distribution were introduced in recent updates. Existing installs will not automatically backfill or correct these because the backfill guard sees previously injected dates as already processed. To trigger a fresh backfill, delete `.storage/aurora_energy_<entry_id>_backfill` from your HA config directory and restart Home Assistant.

> **HA 2026.11 compatibility:** This integration uses the updated `StatisticMeanType` API required by Home Assistant Core 2026.11. Update to the latest version of this integration before upgrading to HA 2026.11 or later.

---

## Data availability

| Data type | Refresh interval | Notes |
|-----------|-----------------|-------|
| Billing data | Every clock hour | Balance, amount owed, etc. — polled 5 seconds past each hour |
| Usage data | Every clock hour | Reflects the previous day; Aurora releases meter data around 8–9am AEST each morning |
| Energy Dashboard stats (historical) | Once per day | Hourly records injected once every hour of the day has been delivered (days delivered up to ~2 days late are picked up automatically); up to 7-day backfill on every HA restart |
| Energy Dashboard stats (today) | Every clock hour | Today's partial hourly data re-injected each poll if the API returns it |
| Billing period totals | Every clock hour | Running kWh/cost totals for the current billing cycle |
| Power Hours (upcoming) | Every clock hour | Active event, timeslot, and selection deadline — status reflects transitions within ~5 seconds |
| Power Hours (total savings) | Once per day | Recalculated from full event history once daily |

---

## Re-authentication

On first login the integration exchanges your credentials for a longer-lived token pair. The refresh token is rotated on every successful refresh, so under normal operation you will not need to re-authenticate.

> **Fixed in 1.0.10:** earlier versions sent the refresh token under the wrong JSON key. The request still succeeded — but only on the strength of a session cookie that carries a fixed ~30-day expiry which token rotation does not extend. The result was a forced re-authentication roughly once a month regardless of how healthy the integration otherwise looked. The request now matches what the official Aurora+ mobile app sends. **Re-authenticate once after upgrading** to seed a fresh token chain.

If your session fully expires (HA will show a notification), click through the re-authentication flow — the same login link approach as initial setup. Once re-authentication succeeds the new tokens are immediately saved and the integration reloads.

Only one thing counts as an expired session: Aurora rejecting the refresh token (HTTP 401/403). From 1.0.17, any other problem while refreshing leaves your saved login untouched, including a network drop, a timeout, or Aurora being down or showing a maintenance page. The Aurora sensors go unavailable and the integration tries again at the next hourly poll. If it happens while Home Assistant is starting, the integration shows as retrying setup, and Home Assistant keeps retrying on its own. Either way it recovers without you doing anything once Aurora is reachable again.

You must re-authenticate with the **same Aurora+ account** the integration was originally set up with — logging in with a different account is rejected (this prevents another account's data being mixed into your existing sensors and Energy Dashboard statistics). To switch accounts, remove the integration and add it again.

The account is matched on your Aurora+ `CustomerID`. If you move premises or re-contract, your `ServiceAgreementID` changes but your `CustomerID` does not, so re-authentication still succeeds and the new `ServiceAgreementID` is saved automatically. (Versions 1.0.7–1.0.8 matched on `ServiceAgreementID` and could reject the correct account — see [Troubleshooting](#troubleshooting).)

After re-authenticating, restart Home Assistant to trigger the automatic backfill and recover any Energy Dashboard data that was missed while authentication was broken.

---

## Tariff notes

This integration supports multiple Aurora tariff structures:

| Tariff | Description |
|--------|-------------|
| **T93** (T93PEAK / T93OFFPEAK) | Time of Use — the most common residential tariff in Tasmania |
| **T31** | Flat rate general power |
| **T41** | Flat rate controlled load (heating) |
| **T140** | Solar feed-in / export (detected automatically) |

The integration automatically detects which tariffs are active on your account. T31/T41 and T93 breakdown sensors are disabled by default — enable only what's relevant to your account.

### T93 peak/off-peak schedule

Aurora's T93 tariff boundaries are set by the **NEM (National Electricity Market) clock, which runs on AEST (UTC+10) year-round** and does not observe daylight saving time.

| Period | AEST time (year-round) | AEDT local time (Oct–Apr) | Days |
|--------|------------------------|---------------------------|------|
| Peak | 7:00 am – 10:00 am | 8:00 am – 11:00 am | Monday – Friday |
| Peak | 4:00 pm – 9:00 pm | 5:00 pm – 10:00 pm | Monday – Friday |
| Off-peak | 10:00 am – 4:00 pm | 11:00 am – 5:00 pm | Monday – Friday |
| Off-peak | 9:00 pm – 7:00 am | 10:00 pm – 8:00 am | Monday – Friday |
| Off-peak | All day | All day | Saturday & Sunday |

The sensor always computes against fixed AEST (UTC+10) regardless of local Hobart time. State transitions fire at the exact UTC times: `21:00` (7am peak start), `00:00` (10am off-peak), `06:00` (4pm peak start), `11:00` (9pm off-peak), `14:00` (midnight weekday boundary).

> **Note:** Public holidays are currently treated as weekdays.

---

## Troubleshooting

### "Invalid redirect URL" error during setup
Make sure you copied the complete URL from your browser's address bar after the Aurora+ login redirect — it should start with `https://my.auroraenergy.com.au/login/redirect?code=`. Don't copy just part of the URL.

### "Authentication failed" error during setup
The login was rejected by Aurora+. Try again with a fresh login link (reload the setup step) and ensure you ticked **Keep me logged in** when logging in.

### Re-authentication is required roughly once a month

Fixed in 1.0.10. Upgrade, then re-authenticate once to seed a fresh token chain. See [Re-authentication](#re-authentication) for the detail.

### Asked to re-authenticate after an internet outage or Aurora maintenance

Fixed in 1.0.17. Earlier versions treated almost any failed token refresh as an expired login: a network drop, a timeout, or an error page from Aurora during an outage. Home Assistant then asked you to re-authenticate even though your login was still valid. If it happened while Home Assistant was starting, the integration failed to load and stayed down until you re-authenticated. If Aurora answered a refresh with no new token, an earlier version could also save an empty access token. The integration then failed every poll without ever asking you to log in again.

From 1.0.17 only a rejected refresh token (HTTP 401/403) asks you to log in again, and a failed refresh never changes your saved login. Anything else is retried at the next hourly poll; see [Re-authentication](#re-authentication). If 1.0.17 asks you to re-authenticate, your session really has expired.

If an earlier version saved an empty access token, 1.0.17 repairs it on the first poll after updating: it gets a new access token with your saved refresh token, without asking you to log in. If that refresh token has also expired, Home Assistant asks you to re-authenticate instead of failing silently.

### Re-authentication prompt reappears immediately after submitting a new token
Ensure you are running the latest version of this integration. Earlier versions had a bug where the new tokens were not saved after re-auth, causing the integration to immediately fail again with the old expired credentials on reload.

### "The Aurora+ customer account you logged in with does not match…" during re-auth
Re-auth refuses tokens belonging to a different Aurora+ account so that another account's data can't be mixed into your existing entities and statistics.

If you *are* logging in with the correct account, upgrade to **1.0.9 or later**. Versions 1.0.7–1.0.8 compared the `ServiceAgreementID`, which is tied to a premise/contract rather than to you — it changes when you move premises or re-contract, and the integration itself already switches to the active premise's SA ID on every poll. That caused false rejections on the correct account. From 1.0.9 the check uses the `CustomerID` instead, and a changed `ServiceAgreementID` is simply written back to the config entry.

If you cannot upgrade immediately, stop Home Assistant, edit `.storage/core.config_entries`, find the `aurora_energy` entry and set its `"unique_id"` to `null`, then start HA and re-authenticate.

### Energy Dashboard is missing data after a period of downtime or broken authentication
The integration backfills up to 7 days of missing data automatically on every HA restart. After resolving the underlying issue (e.g. re-authenticating), **restart Home Assistant** to trigger the backfill. Data older than 7 days cannot be recovered as the Aurora+ API does not expose it.

### Energy Dashboard hours look shifted by an hour or two after a restart
In 1.0.14 and earlier, the startup backfill and the regular poll requested data from Aurora at the same time. Aurora's API sometimes answers overlapping requests with each hour's value taken from 1–2 hours earlier. A day recorded during a restart could therefore be shifted (e.g. midnight showing the previous evening's usage) or a little short. From 1.0.15 requests are sent one at a time. Update and **restart Home Assistant**; the restart re-injects the last 7 days correctly.

### Energy Dashboard shows only the 00:00–01:00 hour for days since daylight saving began
This was a bug in 1.0.12 and earlier ([#17](https://github.com/Forcky/AuroraPlusHA/issues/17)): once AEDT started, each day was recorded before Aurora had delivered most of it, and the cumulative total could step backwards at midnight. Update to 1.0.13 or later and **restart Home Assistant**. The restart re-injects the last 7 days with the complete data and corrects the running totals, so you don't need to edit `.storage`.

### Sensors show "Unknown"
- **Estimated Balance** and **Usage Days Remaining** may be `null` for some account types — this is normal behaviour and not an error.
- **Actual Balance**, **Next Bill Date** and **Balance Last Updated** show `Unknown` if Aurora+ doesn't send that field for your account.
- **Usage sensors** only update once per day when Aurora releases meter data (typically 8–9am AEST). They will show `Unknown` or yesterday's value until then.
- **T93 Peak Usage** reports **0 kWh** for weekend days — there is no peak window on Saturday or Sunday, so zero is the correct value. **T93 Peak Cost** still shows `Unknown` on those days because Aurora omits the dollar figure entirely from its response.

### Power Hour sensors show "Unknown"
Power Hour sensors show `Unknown` when no Power Hours event is currently active or upcoming — this is normal. The **Power Hour Status** sensor will show `no_event` once the coordinator has fetched successfully at least once. If it remains `Unknown` after the first hourly refresh, check **Settings → System → Logs** and filter by `aurora_energy` for warnings.

### Daily Total Usage or Billing Period Usage dropped after updating to 1.0.17 (solar accounts)

Fixed in 1.0.17. Aurora's own kWh total also counts the energy you exported to the grid. Earlier versions showed that total, so on a solar account **Daily Total Usage** and **Billing Period Usage** were too high by your solar export. They now add up the consumption tariffs only, so they drop by the export amount. Values recorded before the update are not rewritten, and each sensor's own history may show one downward step at the update. The Energy Dashboard is not affected: it uses `aurora_energy:total_kwh`, which has never included export.

### Daily Total Usage shows 0.000 kWh
- This is expected before ~8–9am AEST — Aurora has not yet released that day's data.
- If it persists past midday, check **Settings → System → Logs** and filter by `aurora_energy`.

### Recorder warns "state is not strictly increasing"
Fixed in 1.0.11. The usage and cost sensors report a **period total** — the previous day's figure, or the current billing cycle's — not a running meter, so the value drops back down whenever the period rolls over. They were previously declared as `total_increasing`, which made Home Assistant log `state class total_increasing, but its state is not strictly increasing` at the day rollover whenever the new day started less than 10% below the previous one. They are now `total` sensors anchored to a `last_reset` of the period start, which is how Home Assistant expects a resetting total to be modelled. The Energy Dashboard is unaffected either way — it is fed by the integration's own long-term statistics, not these entities.

### No logs from the integration
Ensure the following is in your `configuration.yaml` and that you have performed a full HA restart (not just a reload):
```yaml
logger:
  default: warning
  logs:
    custom_components.aurora_energy: debug
```

---

## Credits

Authentication flow and API endpoint discovery based on community research from [LeighCurran/AuroraPlusHA](https://github.com/LeighCurran/AuroraPlusHA) and [shtrom/AuroraPlusHA](https://github.com/shtrom/AuroraPlusHA).
