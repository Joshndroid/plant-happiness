# 🌱 Plant Happiness Integration

A HACS-compatible Home Assistant integration that aggregates your plant's sensor data into a single, richly-attributed entity — purpose-built to drive the [Plant Happiness Card](https://github.com/your-username/plant-happiness-card).

Instead of a simple OK/problem state, this integration computes a **happiness score (0–100)** and a **mood** (Thriving → Critical) from up to four sensors, with per-sensor status labels and colour codes that the card renders directly.

---

## Features

- UI config flow — add plants via Settings → Integrations, no YAML needed
- Tracks **soil moisture**, **ambient light**, **temperature**, and **humidity**
- Temperature and humidity are optional; scoring re-weights automatically
- Temperature auto-converts °F → °C from any HA sensor
- Exposes a single `sensor.<name>_happiness` entity per plant with state = mood and full attributes
- Edit sensor assignments at any time via the integration's options flow

---

## Installation via HACS

1. In HACS → Integrations → ⋮ → Custom repositories
2. Add: `https://github.com/Joshndroid/plant-happiness` — Category: **Integration**
3. Click **Plant Happiness** → Install
4. Restart Home Assistant
5. Settings → Integrations → Add Integration → search **Plant Happiness**

---

## Setup

After adding the integration you'll be asked for:

| Field | Required | Description |
|-------|----------|-------------|
| Plant Name | ✅ | Friendly name, e.g. `Monstera` |
| Soil Moisture Sensor | ✅ | Reports 0–100 % |
| Light Sensor | ✅ | Reports 0–100 % |
| Temperature Sensor | ☐ | Any HA temperature entity |
| Humidity Sensor | ☐ | Reports 0–100 % |

You can edit these at any time: Settings → Integrations → Plant Happiness → Configure.

---

## Entity attributes

The created sensor (`sensor.<name>_happiness`) exposes:

| Attribute | Example | Description |
|-----------|---------|-------------|
| `happiness_score` | `74` | Weighted score 0–100 |
| `moisture` | `52.3` | Current moisture % |
| `moisture_status` | `"Hydrated"` | Human-readable label |
| `moisture_color` | `"#58a6ff"` | Hex colour for card rendering |
| `light` | `61.0` | Current light % |
| `light_status` | `"Perfect"` | Human-readable label |
| `light_color` | `"#7dff9a"` | Hex colour |
| `temperature` | `21.5` | Current temp °C (if configured) |
| `temperature_status` | `"Perfect"` | Label |
| `temperature_color` | `"#7dff9a"` | Hex colour |
| `humidity` | `48.0` | Current humidity % (if configured) |
| `humidity_status` | `"Comfortable"` | Label |
| `humidity_color` | `"#7dff9a"` | Hex colour |
| `moisture_entity_id` | `sensor.soil` | Source entity ID |
| `light_entity_id` | `sensor.light` | Source entity ID |
| `temperature_entity_id` | `sensor.temp` | Source entity ID |
| `humidity_entity_id` | `sensor.humid` | Source entity ID |

---

## Mood states

| State | Happiness score | Meaning |
|-------|----------------|---------|
| `thriving` | ≥ 88 | All sensors optimal |
| `happy` | ≥ 70 | Sensors in good range |
| `okay` | ≥ 50 | Minor deviations |
| `struggling` | ≥ 30 | Sensors noticeably off |
| `need_water` | < 30 + moisture < 25 % | Critically dry |
| `dark` | < 30 + light < 15 % | Severely light-starved |
| `critical` | < 30 | Multiple sensors bad |

---

## Threshold reference

### Moisture
| Range | Status |
|-------|--------|
| 0–10 % | Critically Dry |
| 10–25 % | Very Thirsty |
| 25–40 % | Thirsty |
| 40–70 % | Hydrated |
| 70–85 % | Well Watered |
| 85–100 % | Overwatered |

### Light
| Range | Status |
|-------|--------|
| 0–8 % | No Light |
| 8–20 % | Too Dark |
| 20–35 % | Low Light |
| 35–70 % | Perfect |
| 70–85 % | Bright |
| 85–100 % | Very Bright |

### Temperature
| Range | Status |
|-------|--------|
| < 5 °C | Dangerously Cold |
| 5–12 °C | Too Cold |
| 12–18 °C | Cool |
| 18–27 °C | Perfect |
| 27–32 °C | Warm |
| 32–38 °C | Too Hot |
| > 38 °C | Dangerously Hot |

### Humidity
| Range | Status |
|-------|--------|
| 0–20 % | Very Dry Air |
| 20–35 % | Dry Air |
| 35–60 % | Comfortable |
| 60–75 % | Humid |
| 75–100 % | Very Humid |

---

## Related

- [Plant Happiness Card](https://github.com/Joshndroid/plant-happiness-card) — the Lovelace card that displays this integration's data
