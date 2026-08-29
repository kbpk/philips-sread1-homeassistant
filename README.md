# Philips SREAD1 for Home Assistant

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
- UI configuration through a Home Assistant Config Flow
- Polling every 15 seconds and an immediate state refresh after commands

Ambient light, eyecare/night modes, scenes, reminders, and delayed off are not
part of version 0.1.0. The coordinator/client split keeps those additions
straightforward for future releases.

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
AP-derived token is replaced after the lamp gets Internet access.

## Installation with HACS

1. Open HACS.
2. Go to **Integrations**.
3. Open **Custom repositories**.
4. Add:

   ```text
   https://github.com/kbpk/philips-sread1-homeassistant
   ```

5. Select **Integration**.
6. Install **Philips SREAD1**.
7. Restart Home Assistant.
8. Go to **Settings → Devices & Services → Add Integration → Philips SREAD1**.
9. Enter the lamp IP/host and MiIO token.

HACS installs the directory under `/config/custom_components/philips_sread1`
and can update it from later GitHub Releases.

## Manual installation

Copy the complete directory:

```text
custom_components/philips_sread1
```

to:

```text
/config/custom_components/philips_sread1
```

Then restart Home Assistant and add **Philips SREAD1** from **Settings → Devices
& Services → Add Integration**. The integration itself requires no YAML.

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
- A single timeout marks the entity unavailable; later coordinator polls perform
  a fresh handshake and can recover automatically.
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

## MiIO commands used for `philips.light.sread1`

Version 0.1.0 uses the model-specific commands implemented by the Philips
EyeCare device support in `python-miio` as a protocol reference only:

| Operation | MiIO method | Parameters/property |
| --- | --- | --- |
| Read lamp state | `get_prop` | `["power", "bright", "notifystatus", "ambstatus", "ambvalue", "eyecare", "scene_num", "bls", "dvalue"]` |
| Turn primary light on/off | `set_power` | `["on"]` / `["off"]` |
| Set primary brightness | `set_bright` | `[1..100]` |

Version 0.1.0 reads the complete model-specific status tuple for firmware
compatibility, but only uses and exposes `power` and `bright`. The remaining
properties are reserved for later entities and features.

Sources:

- [`python-miio` Philips EyeCare implementation](https://github.com/rytilahti/python-miio/blob/master/miio/integrations/philips/light/philips_eyecare.py)
- [Home Assistant's current Xiaomi MiIO light platform](https://github.com/home-assistant/core/blob/dev/homeassistant/components/xiaomi_miio/light.py)
- [Home Assistant DataUpdateCoordinator guidance](https://developers.home-assistant.io/docs/integration_fetching_data/)
- [Home Assistant custom integration manifests](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- [HACS integration repository requirements](https://hacs.xyz/docs/publish/integration/)
- [HACS version/release behavior](https://hacs.xyz/docs/publish/start/)

`python-miio` is not imported, bundled, or installed by this repository.

## Architecture

- `miio_client.py` implements handshake, packet framing, checksum validation,
  AES-128-CBC encryption/decryption, request ID matching, UDP timeout handling,
  and the three model-specific operations.
- `coordinator.py` performs non-optimistic polling and translates communication
  failures into Home Assistant coordinator failures.
- `light.py` maps the lamp's `1..100` brightness to Home Assistant's `0..255`
  scale and refreshes state after every command.
- `config_flow.py` validates host/token connectivity and uses the handshake
  device ID as the config-entry unique ID to prevent duplicates.

Blocking socket operations run through `asyncio.to_thread`, so the Home
Assistant event loop is not blocked.

## Creating the GitHub repository

Create an empty public repository named `philips-sread1-homeassistant` under the
`kbpk` account. Do not initialize it with another README or license. From this
project directory, run:

```bash
git init -b main
git add .
git commit -m "Initial Philips SREAD1 integration"
git remote add origin git@github.com:kbpk/philips-sread1-homeassistant.git
git push -u origin main
```

Alternatively, GitHub CLI can create the remote and push the existing local
repository:

```bash
gh repo create kbpk/philips-sread1-homeassistant \
  --public --source=. --remote=origin --push
```

Enable GitHub Issues, add a short repository description, and add topics such
as `home-assistant`, `hacs`, `miio`, and `philips-sread1`. These repository
settings are among the checks performed by the HACS validation action.

## Releasing and updating

Keep `manifest.json` and the release version synchronized. For the first release:

```bash
git tag v0.1.0
git push origin v0.1.0
gh release create v0.1.0 --title "v0.1.0" --generate-notes
```

The last command creates the required non-draft GitHub Release. You can instead
create it in **Releases → Draft a new release**, selecting the existing
`v0.1.0` tag. HACS uses the GitHub Release tag as the remote version; publishing
only a Git tag is insufficient.

For a later update, change the manifest version (for example to `0.1.1`), commit
and push the changes, tag that commit as `v0.1.1`, push the tag, and publish a
GitHub Release for it:

```bash
git add .
git commit -m "Release 0.1.1"
git push origin main
git tag v0.1.1
git push origin v0.1.1
gh release create v0.1.1 --title "v0.1.1" --generate-notes
```

HACS will then offer **Update** to installed users.

## License

MIT
