# Philips EyeCare Smart Lamp 2 for Home Assistant

A focused [Home Assistant](https://www.home-assistant.io/) custom integration
for the **Philips EyeCare Smart Lamp 2**, model `philips.light.sread1`.

The integration communicates exclusively over the local network using the
[MiIO binary protocol](https://python-miio.readthedocs.io/en/latest/_modules/miio/protocol.html)
over UDP port `54321`. It does not use Xiaomi Cloud and does not use or depend
on [`python-miio`](https://github.com/rytilahti/python-miio).

## Supported features

- Primary light power and brightness
- Ambient/back light power and manual brightness
- EyeCare automatic-brightness mode
- Smart night light triggered by touching the physical controls in darkness
- State updates from the lamp, including changes made with its physical controls
- UI configuration through a Home Assistant Config Flow
- Configurable polling, timeouts, retries, and availability grace period
- Immediate state updates after acknowledged commands

Fixed scenes, eye-fatigue reminders, and delayed off are not currently exposed
as Home Assistant entities.

## Important lamp behavior

The following behavior was confirmed on `philips.light.sread1` firmware `1.3.0`:

- The ambient light cannot operate physically without primary power. Enabling
  ambient or EyeCare may therefore also wake the primary light.
- With smart night light enabled (`bls=on`), touching a physical control while
  the lamp is dark can temporarily illuminate the rear light. Firmware 1.3.0
  reports `bls` as the feature setting but does not report this temporary output
  as a separate current state, so Home Assistant continues to show both
  controllable light entities as off. Disabling the feature with `enable_bl`
  while that temporary light is active extinguishes it immediately without
  changing `power` or `ambstatus`.
- EyeCare controls ambient brightness automatically. While EyeCare is enabled,
  the ambient entity is exposed as ON/OFF without a manual brightness slider.
- Changing primary brightness manually disables EyeCare.
- Disabling EyeCare while the lamp is off may produce a very brief flash because
  the firmware must be woken before it accepts the command.
- Manual ambient brightness uses the lamp's native `1–100` range; the integration
  converts this to Home Assistant's brightness scale.

## Requirements

- Home Assistant 2025.8.0 or newer
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

1. Open [HACS](https://www.hacs.xyz/).
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

## Communication settings

After installation, open the integration's **Configure** action to adjust the
optional transport settings. The defaults are recommended for most networks:

- Polling interval: `60` seconds (`5–300`)
- Request timeout: `5` seconds (`1–30`)
- Handshake timeout: `1` second (`0.2–10`)
- Handshake cache TTL: empty by default (reuse until an error), `0` to
  handshake before every request, or `1–86400` seconds for periodic refresh
- Attempts per request: `3` (`1–5`)
- Retry delay: `0.35` seconds (`0–5`)
- Availability grace period: `60` seconds (`0–600`)

The initial state read and user commands use the configured bounded attempts.
Established background polls use one attempt. If the lamp becomes unavailable,
the integration probes it every `15` seconds and returns to the configured idle
interval after the first successful response.

Changing these values automatically reloads the integration. Host and token are
not part of this tuning form; they remain in the config entry created by the
initial setup flow. No YAML configuration is required.

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
uv run --with cryptography tools/provision_and_test.py
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
  is not blocked between the Home Assistant host/VLAN and the lamp. Routed and
  VPN access works when the firewall allows UDP destination port `54321` and
  return traffic.
- Confirm the token has exactly 32 hexadecimal characters. Re-provisioning or
  resetting a device can change its token.
- If an AP-derived token works immediately after provisioning but later reports
  an invalid checksum, verify both the WAN block and the lamp-to-gateway DNS
  block on TCP/UDP port `53`. Blocking all gateway or LAN access by mistake will
  also block DHCP or local MiIO and make the lamp unavailable.
- Avoid changing the lamp IP by creating a DHCP reservation.
- Commands update Home Assistant immediately after the lamp acknowledges them;
  they do not trigger a redundant `get_prop` transaction. While communication
  is healthy, changes made with the physical controls are detected by the next
  poll, normally within 60 seconds with the stability-oriented default. The
  client reuses authenticated session metadata until a transport or protocol
  failure, avoiding a discovery exchange before every poll. A retry after a
  timeout starts with a fresh handshake so lamp restarts recover automatically.
- By default, the initial state read, setup checks, and commands retry transient
  network failures up to three times. Established background polls use one
  attempt so they cannot hold the MiIO request lock through several cycles. The
  last confirmed state is kept for up to 60 seconds; once it expires, an
  unavailable lamp is probed every 15 seconds until it recovers. These values
  can be changed through **Configure** (the 15-second recovery probe is fixed).
- If HACS does not offer a new version, confirm that the GitHub tag has a full
  [GitHub Release](https://github.com/kbpk/philips-sread1-homeassistant/releases).
  A tag alone is not enough for release-based HACS updates.

To test basic UDP access without providing a token, download or clone this
repository and run the following from a computer that should be able to reach
the lamp:

```bash
python tools/test_miio_handshake.py LAMP_IP
```

A successful result confirms that the lamp answered the MiIO handshake on UDP
port `54321`. A timeout usually indicates routing, VPN, or firewall filtering.

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

## References and acknowledgements

The MiIO wire format and the SREAD1 method/property mapping were cross-checked
against these public references:

- [`python-miio` MiIO protocol implementation](https://github.com/rytilahti/python-miio/blob/master/miio/protocol.py)
  for the packet header, token-derived AES key/IV, checksum, and payload format
- [`python-miio` Philips EyeCare implementation](https://github.com/rytilahti/python-miio/blob/master/miio/integrations/philips/light/philips_eyecare.py)
  for the established SREAD1 properties and commands
- [`syssi/philipslight`](https://github.com/syssi/philipslight/blob/master/custom_components/xiaomi_miio_philipslight/light.py)
  for the earlier Home Assistant mapping of the same lamp model
- [Home Assistant Community real-device investigation](https://community.home-assistant.io/t/improved-support-of-the-xiaomi-philips-eyecare-2/43424/15)
  for observed main/ambient behavior and raw command examples

The integration structure follows the
[Home Assistant developer documentation](https://developers.home-assistant.io/docs/creating_integration_file_structure/),
and repository packaging follows the
[HACS integration requirements](https://hacs.xyz/docs/publish/integration/).
These projects are references, not runtime dependencies. Device-specific edge
cases documented above were additionally verified on a physical
`philips.light.sread1` running firmware `1.3.0`.

## License

Released under the [MIT License](LICENSE).
