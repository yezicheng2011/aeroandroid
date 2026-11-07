# Memory management

Android's RAM budget is selected before the emulator starts. A running VM keeps that size until it stops;
aeroandroid does not expose live ballooning or hot-plug memory through the Android Emulator.

## Automatic mode

New installs default to Automatic, with a 2048 MiB minimum and an 8192 MiB maximum. At each new boot:

1. Read physical RAM with `sysctl hw.memsize` and reclaimable RAM with `vm_stat`.
2. Count free, inactive and speculative pages. Do not add purgeable pages, which overlap other counts.
3. Reserve the larger of 2048 MiB or one quarter of physical RAM for the host.
4. Use the smaller of half physical RAM or reclaimable RAM minus that reserve.
5. Round down to a 256 MiB boundary, then clamp to the configured minimum and maximum.

The minimum is a floor: it takes precedence even under severe memory pressure. A high minimum can therefore
leave less host headroom than the reserve above. Lower the bounds or close other Mac apps if the host swaps.
If macOS measurements fail or cannot be parsed, use the configured minimum and show the fallback in Settings.
This is a conservative estimate, not a measurement of an Android app's working set or a guarantee against swapping.

For example, on a 16 GiB Mac with 10 GiB reclaimable RAM, the host reserve is 4 GiB and Android receives 6 GiB
with the default bounds. If reclaimable RAM falls to 5 GiB before the next start, the 2 GiB floor applies.
Opening additional Android apps does not change the allocation while Android is running.

## Settings and compatibility

Stop Android, open **Settings → Runtime**, select Automatic or Manual, then save. The UI shows the active
allocation while running and the next-start estimate while stopped. The backend status includes both values.
Existing configurations with an explicit `memory_mb` and no mode retain their value in Manual mode.
Older clients that configure only `memory_mb` also select Manual mode. Switching modes preserves that saved value.

The controller accepts these configuration fields (sizes are in MiB):

| Field | Default | Accepted values |
| --- | --- | --- |
| `memory_mode` | `auto` | `auto` or `manual` |
| `memory_mb` | `4096` | Integer, 2048–16384; used in Manual mode |
| `memory_min_mb` | `2048` | Integer, 2048–16384, multiple of 256 |
| `memory_max_mb` | `8192` | Integer, 2048–16384, multiple of 256; at least the minimum |

Example backend request, while Android is stopped:

```bash
python3 backend/subsystem.py configure '{"memory_mode":"auto","memory_min_mb":2048,"memory_max_mb":6144}'
python3 backend/subsystem.py status
```

`status.memory.selected_mb` is the next-start estimate, not an instruction to resize a running VM.
`status.memory.active_mb` is the recorded budget of an owned live emulator process, or `null` if it is stopped
or was started by an older version without that record. Host measurements can change before the actual start.

## Quick Boot and data safety

Before starting a stopped emulator, the controller updates `hw.ramSize` and the selected CPU count in the AVD.
If the last recorded budget differs, its Quick Boot snapshots are removed so the guest cannot restore an
incompatible RAM image. Snapshots from older versions without a recorded allocation are removed once as well.
The next boot is cold. Installed APKs, app data and the AVD userdata image are retained.

Closing an Android app window keeps the subsystem and its background services running. Use **Stop Android**
in the manager or menu bar to release VM memory. Automatic idle shutdown is not enabled, so background work
and notifications are not interrupted by an invisible timer.

## Validation

`python3 -m unittest discover -s tests` covers host page parsing, memory pressure, configured bounds,
missing metrics, legacy/manual compatibility, launch arguments, snapshot invalidation and userdata retention.
The external runtime and JDK keep their existing licenses; this feature uses only Python's standard library.

On a Mac, test Automatic on multiple host workloads, compare the active allocation to the emulator's `-memory`
argument, stop and restart after changing bounds, and confirm apps retain their data after a cold boot.
Native Swift compilation runs in macOS CI. Real memory-pressure behavior and Quick Boot restore require Mac
hardware acceptance; fixture-based controller tests do not substitute for those checks.
