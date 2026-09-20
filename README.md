# Throttled Linked Template

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Home Assistant helper: a **group of template and combine sensors** recalculated **together**, **in order**, every X seconds — not on every source `state_changed`.

Each instance is an independent group. Later sensors in the same group can read earlier ones in the **same tick** with `states('sensor.xxx')`.

This integration is configured from the UI (config flow + options flow). No YAML and no automations are required.

<p align="center">
  <img src="icon.png" alt="Throttled Linked Template" width="128" height="128">
</p>

---

## Why this exists

Core template sensors re-evaluate when their sources change. That is the right default for a single sensor, and the wrong default when:

- several templates form a chain (`1 → 2 → 3 → 4`)
- you need the next template to see the value **just computed**, not the previous interval
- you want a stable cadence (every 5 s, 10 s, …) instead of a burst of updates

`throttled_linked_template` uses **one `DataUpdateCoordinator` per group**. On each tick it evaluates templates **in list order**. After each template it writes the state to an internal group store, then calls `async_write_ha_state`, **then** evaluates the next template. It does **not** subscribe to source `state_changed` events.

---

## Created entities

Each group appears as a service device. Each configured item becomes a `sensor.*` entity.

| Property | Source |
|----------|--------|
| Name | Sensor name from the UI |
| State | Jinja template **or** combine (sum / mean / min / max / median / last / range) |
| `unit_of_measurement` | Optional |
| `device_class` | Optional |
| `state_class` | Optional |
| `unique_id` | Generated automatically and kept when you rename or reorder |
| `linked_index` | 1-based evaluation order |
| `last_error` | Present only when the last render failed |

A template error sets **that** sensor to `unavailable` and the group continues with the next sensors.

On Home Assistant restart, the last numeric/native value is restored when Home Assistant still has it, until the first successful tick.

---

## Installation via HACS

1. Open HACS in Home Assistant
2. **Integrations** → ⋮ → **Custom repositories**
3. Add: `https://github.com/daxharry/hacs_throttled_linked_template`
4. Category: **Integration**
5. Download, then restart Home Assistant

This HACS integration is installed from the repository branch content, without a GitHub release archive. `hacs.json` therefore sets `zip_release: false`.

Requires Home Assistant **2024.12** or newer.

## Manual installation

1. Copy `custom_components/throttled_linked_template/` into `/config/custom_components/`
2. Restart Home Assistant

---

## Configuration

The integration appears under **Settings → Devices & services → Integrations** (not under Helpers).

1. **Add integration** and search for **Throttled Linked Template**
2. Set the **group name** and **interval** (seconds, minimum 1, default 5)
3. Add sensors in evaluation order. Each one is either:
   - **Template** — a Jinja template
   - **Combine** — several source entities, like Home Assistant's "Combine the state of several sensors" helper (`sum`, `mean`, `min`, `max`, `median`, `last`, `range`)
4. Add, edit, remove or reorder sensors, then create the group

You can add as many groups as you need. They stay independent.

### Options

Open the integration entry → **Configure**:

- Change the group name and interval
- Add / edit / remove / reorder sensors

The group is **not** recreated. Existing `unique_id`s are kept, so entity IDs and history stay attached when you only edit a template or rename a sensor. Removing a sensor deletes its entity. The group reloads after save.

---

## Chaining example

Group: `PV chain` — interval: `5`

1. **PV power W** *(combine, sum)*  
   Sources: `sensor.inverter_1_power`, `sensor.inverter_2_power`
2. **PV power kW** *(template)*
   ```jinja
   {{ states('sensor.pv_power_w') | float(0) / 1000 }}
   ```
3. **PV value** *(template)*
   ```jinja
   {{ states('sensor.pv_power_kw') | float(0) * states('input_number.price_kwh') | float(0) }}
   ```

On every tick, sensor 2 reads the value sensor 1 just wrote, and sensor 3 reads sensor 2 just wrote. Entity IDs follow the names you give (for example `sensor.pv_power_w`). Check **Developer tools → States** if a name was already taken.

The `this` variable is available (`this.state`, `this.entity_id`, `this.name`) and refers to the sensor currently being evaluated.

Same-tick values are also in `linked`:

```jinja
{{ linked['sensor.pv_power_w'] }}
{{ linked.pv_power_w }}
```

---

## Behaviour notes

- Recalculation is **only** on the interval (and at startup). Source sensors can change in between; this group will not notice until the next tick.
- Templates are standard Home Assistant Jinja. They are rendered with `Template.async_render` and are **not** tracked.
- Combine sensors skip unavailable / non-numeric sources. If none remain, that sensor is `unavailable` for the tick.
- A render result of `unknown` or `unavailable` makes that sensor unavailable for the tick.
- Several groups can run in parallel, each with its own coordinator and interval.

---

## Icon

- HACS and Home Assistant use `custom_components/throttled_linked_template/brand/icon.png` and `logo.png`.
- Root `icon.png` is used to display this page.
