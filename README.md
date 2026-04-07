# Aurora Energy Tasmania (Aurora+) — Home Assistant Integration

A custom Home Assistant integration that pulls your Aurora Energy Tasmania billing and usage data into Home Assistant sensors and the Energy Dashboard.

## What it does

- Estimated balance, amount owed, unbilled amount
- Daily energy usage (kWh) and cost
- Solar feed-in (kWh exported and earnings)
- Historical statistics for the Energy Dashboard (backfills 9 days on first run)
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

### Disabled by default

The following sensors exist but are disabled by default. They are only relevant for accounts on T31/T41 flat-rate tariffs. Enable them via **Settings → Devices → Aurora Energy → entities** if needed.

| Sensor | Description |
|--------|-------------|
| T31 General Usage | T31 tariff consumption (kWh) |
| T31 General Cost | T31 tariff cost (AUD) |
| T41 Heating Usage | T41 tariff consumption (kWh) |
| T41 Heating Cost | T41 tariff cost (AUD) |

---

## Energy Dashboard

The integration injects hourly statistics into the HA recorder, which can be used directly in the **Energy Dashboard**.

On first run it will backfill up to 9 days of historical data. After that it injects each new day's records once they become available from Aurora.

To add to the Energy Dashboard:
1. Go to **Settings → Dashboards → Energy**
2. Under **Electricity grid**, add:
   - **Grid consumption:** `aurora_energy:total_kwh`
3. Under **Solar panels**, add:
   - **Energy production:** `aurora_energy:solar_feedin_kwh`
   - **Return to grid:** `aurora_energy:solar_feedin_kwh`

---

## Data availability

| Data type | Refresh interval | Notes |
|-----------|-----------------|-------|
| Billing data | Every hour | Balance, amount owed, etc. update immediately |
| Usage data | Every hour | Reflects the previous day; Aurora releases meter data around 8–9am AEST each morning |
| Energy Dashboard stats | Once per day | Injected automatically when daily data becomes available |

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

The integration automatically detects which tariffs are active on your account. T31/T41 sensors are disabled by default for T93 accounts.

---

## Troubleshooting

### "Invalid token" error during setup
The id_token expired before you submitted it. Grab a fresh token from the Aurora+ portal and submit it within 30 seconds of copying it.

### Sensors show "Unknown"
- **Estimated Balance** and **Usage Days Remaining** may be `null` for some account types — this is normal behaviour and not an error.
- **Usage sensors** only update once per day when Aurora releases meter data (typically 8–9am AEST). They will show `Unknown` or yesterday's value until then.

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
