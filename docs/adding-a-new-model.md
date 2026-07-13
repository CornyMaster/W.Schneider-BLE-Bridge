# Adding support for another W.Schneider cabinet

Only the WSC LC10 has been verified so far. Other W.Schneider cabinets are
expected to use the same or a very similar controller, but this is unconfirmed.
This guide describes how to check a new model and, if needed, add support.

## 1. Capture the GATT database

With the cabinet powered and in range, dump its services and characteristics:

```bash
cd scripts
python discover_gatt.py            # or: --mac <ADDRESS>
```

Compare the output with [protocol.md](protocol.md):

- **Same service UUID and characteristics** → the model very likely speaks the
  WSC LC10 protocol. Continue at step 2.
- **Different UUIDs but the same layout** (one vendor service with ~10 writable
  characteristics) → probably the same protocol under different UUIDs. The
  scripts and ESPHome package already take the UUID as a parameter, so you may
  only need to fill in the new UUID. Continue at step 2.
- **A genuinely different structure** → treat it as a new protocol: work out the
  payload formats (see step 2) and add a dedicated ESPHome package under
  `esphome/packages/`.

## 2. Determine the payload semantics

Discovery reveals structure, not meaning. Establish what each characteristic
does by observing the device:

1. Read the current values with `python wsc_ctl.py read` and note them.
2. Operate the cabinet with the vendor app and re-read, watching which
   characteristic changes and how (brightness, color temperature, on/off).
3. Confirm with targeted writes, e.g.
   `python wsc_ctl.py raw <char> <hex bytes>`.
4. When the command set matches, run the interactive check and keep the summary:
   ```bash
   python validate_protocol.py
   ```

If the payloads differ from the WSC LC10 (byte order, scale, mask layout),
capturing an HCI snoop log of the vendor app while it operates the cabinet is
the most reliable way to decode them.

## 3. Record the model

Add a short notes file under `models/` (copy `models/wsc-lc10.md` as a
template) describing:

- the model designation and how it identifies itself over BLE,
- lamp layout (how many lamps, inner/outer bit assignment),
- supported ranges (brightness, color temperature),
- validation status (which commands were confirmed, and how),
- anything that differs from the WSC LC10.

Do **not** put a specific unit's MAC address in the repository — it is per-unit
and is read at setup time.

## 4. Wire it up

- **Same protocol, different UUID:** no code change needed — users just fill in
  the new UUID as described in the README.
- **Different protocol:** add a new package under `esphome/packages/` (copy
  `wsc-lc10.yaml` and adapt the write routines), extend `scripts/wsc_lc10.py`
  with the new encoders, and point the device config's `packages:` at your new
  file.

## 5. Update the support table

Add the model to the "Supported models" table in the main [README](../README.md)
with its verification status.
