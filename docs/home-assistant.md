# Home Assistant integration

Once the ESP32 is adopted (see the main [README](../README.md)), the cabinet
appears as a single ESPHome device with the entities listed below. This page
covers what they mean and how the state read-back behaves.

## Entities

| Entity | Type | Purpose |
|--------|------|---------|
| Outer lamp | `switch` | Per-lamp on/off of the perimeter lamp. |
| Inner lamp | `switch` | Per-lamp on/off of the mirror lamp. |
| Brightness | `number` | 1–100 %, applied to both lamps. |
| Color temperature | `number` | 2000–6500 K, applied to both lamps. |
| BLE re-read interval | `number` | How often the actual state is re-read (0 = only on connect). |
| Cabinet connected | `binary_sensor` | Whether the ESP32 holds a BLE link. |
| Read state now | `button` | Force an immediate re-read of the actual state. |
| Actual brightness / color temperature / lamp mask | `sensor` | Diagnostic: the raw values read back from the cabinet. |

## How control and read-back work

- The **Outer lamp** / **Inner lamp** switches give per-lamp on/off. Brightness
  and color temperature always apply to **both** lamps at once (a hardware
  limitation) and only have a visible effect while at least one lamp is on.
- **Nothing is written on connect.** The bridge reads the cabinet's real state
  (on/off per lamp, brightness, color temperature) and mirrors it into the
  switches and sliders, so Home Assistant shows what the cabinet is actually
  doing — including changes made with the cabinet's own buttons.
- **Writes happen only on change.** Operating a switch or slider sends the new
  state to the cabinet; a read never triggers a write, so there is no feedback
  loop.

## Behaviour notes

- **Read-back, not push.** The controller does not push updates, so an external
  change (cabinet buttons) appears in Home Assistant only at the next re-read.
  Set **BLE re-read interval** to trade freshness against BLE traffic (0 = only
  on connect; default 30 s). The **Read state now** button forces an immediate
  refresh.
- **One BLE connection.** The cabinet accepts a single BLE connection and the
  bridge holds it persistently, so the vendor remote/app cannot connect while
  the bridge is running. (A reliable on-demand model that frees the link between
  reads is not feasible on single-core ESP32-C3 boards.)
- **Reconnects.** After the ESP32 reconnects, it re-reads the actual state
  automatically; you do not need to press anything.
- **Diagnostic sensors.** The **Actual …** sensors expose the raw read-back
  values (e.g. the lamp mask: bit 0 = outer, bit 1 = inner, so 3 = both on).
  They are handy for debugging and can be hidden in Home Assistant if not needed.
