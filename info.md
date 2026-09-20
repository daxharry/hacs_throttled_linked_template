# Throttled Linked Template

<p align="center">
  <img src="icon.png" alt="Throttled Linked Template" width="128" height="128">
</p>

Helper UI for Home Assistant: a **group of template and combine sensors** recalculated **together**, **in order**, every X seconds — not on every source change.

Later sensors in the same group can read earlier ones in the **same tick** with `states('sensor.xxx')`. One `DataUpdateCoordinator` per group. Template errors make that sensor `unavailable` and the group continues.

Configured from **Settings → Devices & services**. Open the entry and click **Configure** to change the interval or the ordered sensor list without recreating the group.

Requires Home Assistant 2024.12+. No YAML, no automations, no extra Python dependencies.

This HACS integration is installed directly from the repository content, without a GitHub release.
