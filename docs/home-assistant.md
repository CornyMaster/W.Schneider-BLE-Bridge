# Home Assistant integration

Once the ESP32 is adopted (see the main [README](../README.md)), the cabinet
appears as a single ESPHome device with the entities listed below. This page
covers what they mean and an optional way to present them as regular lights.

## Entities

| Entity | Type | Purpose |
|--------|------|---------|
| Cabinet | `light` | Main control: on/off (both lamps) + brightness + color temperature. |
| Outer lamp | `switch` | Per-lamp on/off of the perimeter lamp. |
| Inner lamp | `switch` | Per-lamp on/off of the mirror lamp. |
| Cabinet connected | `binary_sensor` | Whether the ESP32 holds a BLE link. |
| Pair / send init | `button` | Re-sends the init handshake (timing helper for the first pairing). |

The **Cabinet** light is a native ESPHome `color_temperature` light, so it works
with Home Assistant's normal light card (brightness slider + color-temperature
slider) with no extra configuration on the Home Assistant side.

## How the light and the switches interact

- The **Cabinet** light's on/off is a *master*: turning it on switches **both**
  lamps on, turning it off switches both off.
- The **Outer lamp** / **Inner lamp** switches give per-lamp on/off. You can, for
  example, turn the Cabinet light on and then switch one lamp off.
- Brightness and color temperature always apply to **both** lamps at once (a
  hardware limitation) and only have a visible effect while at least one lamp is
  on.

## Behaviour notes

- **Optimistic state.** The controller gives no reliable feedback, so Home
  Assistant assumes commands succeed. Changes made through the vendor app do not
  appear in Home Assistant.
- **Light vs. switches, small quirks.** Because on/off lives on two layers, the
  Cabinet light's state can lag reality when you use the per-lamp switches (e.g.
  it still shows "on" after you switch both lamps off via the switches). Adjusting
  brightness or color temperature requires the Cabinet light to be on.
- **Reconnects.** After the ESP32 reconnects, it re-applies the last known state
  automatically; you do not need to press anything.
