# Provenance

`src/tr_1um_i2c_slave_async.gds` / `src/tr_1um_i2c_slave_async.cir` in this
repository are exported copies, not designed here. This file records where
they came from and what was done to them on the way in.

## Source repository

[jun1okamura/TR-1um_Async_I2C](https://github.com/jun1okamura/TR-1um_Async_I2C)

| This repo (`src/`) | Source repo |
|---|---|
| `tr_1um_i2c_slave_async.gds` | `layout/step10/v10_chip_final.gds` |
| `tr_1um_i2c_slave_async.cir` | `schematic/tr_1um_i2c_slave_async_v10_ringosc_lvs.spice` |

Exported via the source repo's own `script/export_to_mpw_submission_v10.py`
(V10 counterpart of the original `export_to_mpw_submission.py`, same role
-- re-runnable there to refresh both files here plus this repo's
`info.yaml`; see that script's own module docstring for exactly how it
differs from the V9 version).

**V10 supersedes the V9 export previously documented here.** V10 is not a
different design -- same RTL, same protocol -- but a re-placed,
re-routed build with a corrected GIO pad-to-signal assignment and a
from-scratch chip-level power/signal routing pass (see source repo
`design_notes.md` §108.52-108.72). **The physical pinout differs from
the V9 export**: which bond pad (`P3`..`P14`) carries which `tx_data`/
`rx_data` bit changed under V10's pad reassignment. The pad assignment
went through two iterations before landing on the final one exported
here: an initial lane-minimal assignment (§108.57), then -- per the
source repo owner's explicit request to keep the mapping monotonic and
readable -- a revised assignment ("Option2": physical pad number
ascending order tracks bit number ascending order, `P3`..`P6` = bit0-3,
`P11`..`P14` = bit4-7, §108.69), with a follow-up fix to a stale
hardcoded reset-net routing coordinate that the reassignment had broken
(§108.70). **Option2 is what's exported here.** See this repo's
`README.md` §1 for the current (V10, Option2) pin table -- do not reuse
any V9-era or §108.57-era pinout notes.

## What was done in the source repository

- Async I2C slave core implemented as **clockless logic** (all state
  transitions driven purely by SCL/SDA edges, no `clk` port) -- RTL design,
  MyHDL/iverilog functional verification, Yosys synthesis onto the TR-1um
  standard cell library, custom placement/routing, DRC/LVS closure, and
  chip-level IRSIM transistor-level verification (WRITE/READ/NACK, matching
  the Verilog testbench bit-for-bit). Full history in that repo's
  `design_notes.md` (105+ numbered sections).
- A ring oscillator (`RING_OSC`) test structure was subsequently integrated
  onto the same chip, alongside the core, with its own power/signal
  routing and LVS reference netlist; a standalone ngspice testbench
  confirmed real oscillation (~6.5MHz and ~1.6MHz on its two rings).
- An OpenSUSI logo was placed as DRC-clean M2 metal art in the leftover
  space between the core and RING_OSC.
- **V10 revision**: the core's DFF/latch cells were integrated as
  synthesized MUXDFFRB/RSLATCH standard cells, the chip was fully
  re-placed and re-routed (including a GIO pad-to-signal reassignment
  and a from-scratch GIO-ring power/signal routing pass, using
  ring-routing to work around `RING_OSC`'s footprint blocking the
  straightforward routing corridors), and the resulting chip-level
  netlist (RING_OSC excluded) was run through a real, locally-executed
  ngspice transistor-level simulation of the project's standard 14-check
  WRITE/READ/wrong-address-NACK regression -- confirmed **14/14 PASS**,
  matching the RTL/gate-level-Verilog/IRSIM results obtained earlier for
  the same protocol. A later regression run with different WRITE/READ
  data values transiently showed 2/14 FAIL; a detailed transistor-level
  investigation (measured, sub-10ns address-compare latch timing) traced
  this to the testbench's SPICE solver time-resolution setting, not a
  chip or pad-assignment defect -- tightening it resolved the failures,
  and the production testbenches were also updated to dynamically gate
  `DIS`/the tx-data sources (via a switch + 100kOhm series resistor)
  to match the design's intended WRITE-time driver behavior (source repo
  `design_notes.md` §108.71-108.72).
- The full chip (core + RING_OSC + logo), V10 revision included, is
  confirmed **DRC/LVS clean** under real KLayout.

## Changes made specifically for this export (not present in the source)

- The real frame cell, named `OSS_FRAME_GIO` in the source repo, was
  renamed to `OSS_FRAME` in this copy only, to match this template's
  `scripts/pre_check.py` naming check. The source repo keeps
  `OSS_FRAME_GIO` (that name is used throughout its own scripts/docs).
- A handful of dead, unreferenced standard-cell definitions left over from
  synthesis (`AND3_X1`, `NAND4`, `DFF`, `TAP3`, `DFFS`, and -- new in the
  V10 source GDS -- `DEL1`) were dropped so the GDS has exactly one
  top-level cell, as this template requires. Each was individually
  verified (klayout.db: zero parent cells AND zero child instances) to be
  a genuine dead leftover before removal, leaving the actual design
  geometry untouched.
- `.spice` was renamed to `.cir` to match `info.yaml`'s `lvs.extension`.
