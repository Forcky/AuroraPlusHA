# Aurora Energy Tasmania (Aurora+) — Home Assistant Integration

A custom Home Assistant integration that pulls your Aurora Energy Tasmania billing and usage data into Home Assistant sensors and the Energy Dashboard.

## What it does

- Estimated balance, amount owed, unbilled amount
- Daily energy usage (kWh) and cost
- Solar feed-in (kWh exported and earnings)
- Real-time T93 tariff period sensor (`peak` / `off_peak`), DST-correct
- Power Hours demand-response program sensors (status, timeslot, savings)
- Billing period totals (cumulative kWh and cost for the current billing cycle)
- Historical statistics for the Energy Dashboard (backfills 7 days on first run; today's partial hourly data updated each poll)
- Automatic hourly refresh

---

## Prerequisites

- Home Assistant 2025.11 or later
- An Aurora Energy Tasmania account with Aurora+ access
- A web browser with DevTools (to extract your id_token)

---

## Getting your id_token

The integration authenticates using a short-lived Azure B2C id_token from the Aurora+ web portal. You need to capture this from your browser's network traffic.

1. Open the [Aurora+ web portal](https://my.auroraenergy.com.au) in your browser
2. Press **F12** to open DevTools and go to the **Network** tab
3. Log in to Aurora+ — **make sure to tick "Keep me logged in"**
4. In the Network tab, filter by `LoginToken`
5. Click the `LoginToken` request → **Request Payload**
6. Copy the value of the `token` field — it is a long string starting with `eyJ...`

> **Important:** The id_token expires within a few minutes of login. Have the Home Assistant setup screen ready and submit the token immediately after copying it.

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
9. Paste your id_token into the field and click **Submit**

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
5. Paste your id_token into the field and click **Submit**

If setup succeeds, a device called **Aurora Energy** will appear with all sensors populated.

---

## Sensors

| Sensor | Description | Unit |
|--------|-------------|------|
| Estimated Balance | Current account balance | AUD |
| Amount Owed | Outstanding amount due | AUD |
| Unbilled Amount | Charges not yet on a bill | AUD |
| Average Daily Usage | Average daily spend | AUD |
| Bill Total Amount | Most recent bill total | AUD |
| Usage Days Remaining | Days remaining in billing period | d |
| Daily Total Usage | Previous day's consumption | kWh |
| Daily Total Cost | Previous day's energy cost | AUD |
| Solar Feed-in | Previous day's solar export | kWh |
| Solar Feed-in Earnings | Previous day's solar feed-in credit | AUD |
| T93 Tariff Period | Current tariff period: `peak` or `off_peak` | — |
| Power Hour Status | Current Power Hours state (see below) | — |
| Power Hour Event | Name of the upcoming or active Power Hours event | — |
| Power Hour Start | Start of your accepted free-power timeslot | — |
| Power Hour End | End of your accepted free-power timeslot | — |
| Power Hour Selection Deadline | Deadline to select a timeslot | — |
| Power Hour Total Savings | Lifetime savings from Power Hours events | AUD |
| Billing Period Usage | Total kWh consumed in current billing cycle | kWh |
| Billing Period Cost | Total cost in current billing cycle | AUD |
| Billing Period Solar Feed-in | Total solar exported in current billing cycle | kWh |
| Billing Period Solar Earnings | Total solar feed-in credit in current billing cycle | AUD |
| Bill Due Date | Date the current bill is due | — |
| Overdue Amount | Amount currently overdue | AUD |
| Unpaid Bills | Count of unpaid bills | — |

**Power Hour Status values:**

| Value | Meaning |
|-------|---------|
| `no_event` | No upcoming Power Hours event |
| `selection_pending` | An event has been announced but you haven't selected a timeslot yet — act before the **Selection Deadline** |
| `confirmed` | You've accepted a timeslot — free electricity starts at **Power Hour Start** and ends at **Power Hour End** |
| `active` | Your Power Hours timeslot is currently running — electricity is free right now |

> **Note:** The coordinator evaluates the start and end timestamps on every poll and sets the status to `active` directly — your dashboard can use a simple `condition: state` check rather than comparing timestamps in a template.

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
| Tariff Period End | When the current tariff contract period ends | T93 accounts |
| Unread Notifications | Number of unread Aurora+ notifications | All accounts |
| Direct Debit | Whether a direct debit arrangement is active (`active`/`inactive`) | All accounts |
| Auto Payment | Whether auto-payment (card) is configured (`active`/`inactive`) | All accounts |

---

## Energy Dashboard

The integration injects hourly statistics into the HA recorder, which can be used directly in the **Energy Dashboard**.

On first run it will backfill up to 7 days of historical hourly data. After that it injects each new completed day's records once they become available from Aurora (typically 8–9am AEST). The integration also attempts to fetch today's in-progress hourly data on every poll — if the API returns it, the current day's bars will update hourly throughout the day.

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
| `aurora_energy:total_dollars` | Total energy cost |
| `aurora_energy:solar_feedin_dollars` | Solar feed-in earnings |

---

## Data availability

| Data type | Refresh interval | Notes |
|-----------|-----------------|-------|
| Billing data | Every hour | Balance, amount owed, etc. update immediately |
| Usage data | Every hour | Reflects the previous day; Aurora releases meter data around 8–9am AEST each morning |
| Energy Dashboard stats (historical) | Once per day | Hourly records injected once per completed day; 7-day backfill on first run |
| Energy Dashboard stats (today) | Every hour | Today's partial hourly data re-injected each poll if the API returns it |
| Billing period totals | Every hour | Running kWh/cost totals for the current billing cycle |
| Power Hours (upcoming) | Every hour | Active event, timeslot, and selection deadline |
| Power Hours (total savings) | Once per day | Recalculated from full event history once daily |

---

## Re-authentication

The id_token is exchanged for a longer-lived access and refresh token pair on first login. Under normal operation you will not need to re-authenticate.

If your session fully expires (HA will show a notification), repeat the id_token steps above and enter the new token when prompted.

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

### "Invalid token" error during setup
The id_token expired before you submitted it. Grab a fresh token from the Aurora+ portal and submit it within 30 seconds of copying it.

### Sensors show "Unknown"
- **Estimated Balance** and **Usage Days Remaining** may be `null` for some account types — this is normal behaviour and not an error.
- **Usage sensors** only update once per day when Aurora releases meter data (typically 8–9am AEST). They will show `Unknown` or yesterday's value until then.

### Power Hour sensors show "Unknown"
Power Hour sensors show `Unknown` when no Power Hours event is currently active or upcoming — this is normal. The **Power Hour Status** sensor will show `no_event` once the coordinator has fetched successfully at least once. If it remains `Unknown` after the first hourly refresh, check **Settings → System → Logs** and filter by `aurora_energy` for warnings.

### Daily Total Usage shows 0.000 kWh
- This is expected before ~8–9am AEST — Aurora has not yet released that day's data.
- If it persists past midday, check **Settings → System → Logs** and filter by `aurora_energy`.

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
