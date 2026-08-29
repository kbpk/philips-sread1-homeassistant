# Philips EyeCare Smart Lamp 2 for Home Assistant

A focused Home Assistant custom integration for the **Philips EyeCare Smart
Lamp 2**, model `philips.light.sread1`.

The integration communicates exclusively over the local network using the MiIO
binary protocol over UDP port `54321`. It does not use Xiaomi Cloud and does not
use or depend on `python-miio`.

## Supported features

- Primary light power on/off
- Primary light power state
- Primary light brightness control
- Primary light brightness state
- Ambient/back light power and state (subject to the firmware's main-power supply)
- Ambient/back light brightness control while EyeCare is disabled
- EyeCare automatic-brightness mode control and state
- Three attempts for transient UDP timeouts and socket failures
- One-second handshake timeout for fast recovery from dropped UDP handshakes
- UI configuration through a Home Assistant Config Flow
- Polling every 15 seconds, including changes made with the physical controls
- Immediate Home Assistant state updates after acknowledged commands

Smart night light, fixed scenes, eye-fatigue reminders, and delayed off are not
currently exposed as Home Assistant entities.

On the tested `philips.light.sread1` firmware `1.3.0`, EyeCare takes hardware
control of automatic brightness and links the physical ambient output to that
mode. The lamp still accepts `set_amb_bright` and reports the requested
`ambvalue`, but the change has no visible effect while EyeCare is enabled. The
integration therefore exposes the ambient entity as ON/OFF only in EyeCare mode
and restores its brightness slider after EyeCare is disabled. Manual ambient
brightness accepts the native range `1..100`; the lamp rejects `0`.

The same firmware couples several otherwise separate commands. Enabling ambient
light or EyeCare wakes the primary light, and the tested firmware does not
provide a physical ambient-only state: turning primary power off extinguishes
both outputs even if `ambstatus` remains remembered as `on`. The integration
therefore reports ambient as physically on only while primary power is on and
keeps the main entity synchronized with these side effects. Disabling EyeCare
while the primary light is off requires waking it first and then restoring power
off, which may produce a very brief flash. Setting primary brightness manually
disables EyeCare in the firmware; the integration reflects that mode change
immediately.

## Requirements

- Home Assistant 2024.11.0 or newer
- A provisioned `philips.light.sread1` lamp reachable from Home Assistant
- The lamp's local IPv4 address or hostname
- Its 16-byte MiIO token written as exactly 32 hexadecimal characters
- UDP traffic from Home Assistant to the lamp on port `54321`

Reserve the lamp's address in DHCP if possible. Never publish your token in an
issue, screenshot, or debug log.

When obtaining the token locally from the lamp's setup access point, see
**Local provisioning and token stability** below. On the tested firmware, an
AP-derived token is replaced after the lamp gets DNS/cloud access.

## Installation with HACS

1. Open HACS.
2. Go to **Integrations**.
3. Open **Custom repositories**.
4. Add:

   ```text
   https://github.com/kbpk/philips-sread1-homeassistant
   ```

5. Select **Integration**.
6. Install **Philips EyeCare Smart Lamp 2**.
7. Restart Home Assistant.
8. Go to **Settings → Devices & Services → Add Integration → Philips EyeCare
   Smart Lamp 2**.
9. Enter the lamp IP/host and MiIO token.

HACS installs the directory under `/config/custom_components/philips_sread1`
and can update it from later GitHub Releases.

## Updating with HACS

When HACS shows an update for **Philips EyeCare Smart Lamp 2**, open the
integration in HACS, select **Update**, and restart Home Assistant after
installation. Existing devices and entity unique IDs are preserved.

The repository includes native `256×256` and `512×512` brand icons. Home
Assistant 2026.3 or newer loads them directly from the custom integration;
older supported releases continue to work but may display a generic icon.

## Manual installation

Copy the complete directory:

```text
custom_components/philips_sread1
```

to:

```text
/config/custom_components/philips_sread1
```

Then restart Home Assistant and add **Philips EyeCare Smart Lamp 2** from
**Settings → Devices & Services → Add Integration**. The integration itself
requires no YAML.

## Local provisioning and token stability

The optional offline helper can provision the lamp and verify the token both in
setup mode and after it joins the LAN:

```bash
uv run tools/provision_and_test.py
```

Real-device testing with `philips.light.sread1` firmware `1.3.0` showed that the
token exposed by the setup AP remains usable only while the lamp cannot resolve
or reach Xiaomi endpoints. A WAN block alone was insufficient when the gateway
DNS proxy still answered the lamp. After DNS/cloud access, the lamp replaces
the AP-derived token while continuing to hide the active token in normal
handshake responses.

For a fully local setup using an AP-derived token:

1. Prefer a dedicated IoT VLAN with no Internet access. If the lamp remains on
   a normal Internet-enabled LAN, add a router/firewall rule blocking
   **WAN/Internet** for the lamp's MAC address.
2. Block DNS from the lamp to the gateway and any other resolver on both TCP and
   UDP port `53`. On UniFi this requires a rule from the lamp device/object to
   the **Gateway** zone; an Internet-only rule does not block the gateway's DNS
   proxy. Keep DHCP (`UDP 67/68`) and local MiIO (`UDP 54321`) permitted.
3. Do not rely only on a Content Filter or a block for `ott.io.mi.com`. During
   real-device testing those policies blocked subsequent cloud traffic but
   still allowed DNS resolution, after which firmware `1.3.0` replaced the
   AP-derived token.
4. Factory-reset the lamp and connect the computer to its setup AP.
5. Run the helper. It reads `miIO.info`, provisions Wi-Fi, verifies LAN control,
   and can turn the lamp off as an end-to-end test.
6. Keep the lamp-specific WAN and DNS rules enabled permanently.
7. Read `.philips_sread1_token` locally and enter that value in the Home
   Assistant Config Flow. The file is mode `0600` and ignored by Git.

Alternatively, a current post-binding LAN token obtained independently can be
entered directly in the integration. The integration itself never contacts the
Xiaomi cloud.

## Troubleshooting

- Verify that the lamp answers at the configured address and UDP port `54321`
  is not blocked between the Home Assistant host/VLAN and the lamp.
- Confirm the token has exactly 32 hexadecimal characters. Re-provisioning or
  resetting a device can change its token.
- If an AP-derived token works immediately after provisioning but later reports
  an invalid checksum, verify both the WAN block and the lamp-to-gateway DNS
  block on TCP/UDP port `53`. Blocking all gateway or LAN access by mistake will
  also block DHCP or local MiIO and make the lamp unavailable.
- Avoid changing the lamp IP by creating a DHCP reservation.
- Commands update Home Assistant immediately after the lamp acknowledges them;
  they do not trigger a redundant `get_prop` transaction. Changes made with the
  lamp's physical controls are detected by the next poll, normally within 15
  seconds.
- Transient handshake/request timeouts and socket failures are retried up to
  three times with a fresh handshake and request ID. After a successful poll,
  the integration keeps the last confirmed state through brief communication
  gaps and only marks the entities unavailable after the state has been stale
  for more than 60 seconds. A command acknowledged by the lamp also renews this
  availability window. Authentication failures are never hidden by the grace
  period. Later successful coordinator polls recover automatically.
- If HACS does not offer a new version, confirm that the GitHub tag has a full
  GitHub Release. A tag alone is not enough for release-based HACS updates.

To enable debug logs temporarily, add this optional block to
`configuration.yaml` and restart Home Assistant:

```yaml
logger:
  default: info
  logs:
    custom_components.philips_sread1: debug
```

The integration logs the host, MiIO method, request ID, timeouts, packet length,
and parsing outcome. It never logs the token. Remove the debug override after
troubleshooting to keep logs compact.

## License

MIT
