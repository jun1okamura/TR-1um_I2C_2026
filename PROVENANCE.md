# Provenance

`src/tr_1um_i2c_slave_async.gds` / `src/tr_1um_i2c_slave_async.cir` in this
repository are exported copies, not designed here. This file records where
they came from and what was done to them on the way in.

## Source repository

[jun1okamura/TR-1um_Async_I2C](https://github.com/jun1okamura/TR-1um_Async_I2C)

| This repo (`src/`) | Source repo |
|---|---|
| `tr_1um_i2c_slave_async.gds` | `ring_osc/tr_1um_i2c_slave_async_ringosc_clean.gds` |
| `tr_1um_i2c_slave_async.cir` | `schematic/tr_1um_i2c_slave_async_ringosc_v9_lvs.spice` |

Exported via the source repo's own `script/export_to_mpw_submission.py`
(re-runnable there to refresh both files here plus this repo's `info.yaml`).

## What was done in the source repository

- Async I2C slave core implemented as **clockless logic** (all state
  transitions driven purely by SCL/SDA edges, no `clk` port) -- RTL design,
  MyHDL/iverilog functional verification, Yosys synthesis onto the TR-1um
  standard cell library, custom placement/routing, DRC/LVS closure, and
  chip-level IRSIM transistor-level verification (WRITE/READ/NACK, matching
  the Verilog testbench bit-for-bit). Full history in that repo's
  `design_notes.md` (103 numbered sections).
- A ring oscillator (`RING_OSC`) test structure was subsequently integrated
  onto the same chip, alongside the core, with its own power/signal
  routing and LVS reference netlist; a standalone ngspice testbench
  confirmed real oscillation (~6.5MHz and ~1.6MHz on its two rings).
- An OpenSUSI logo was placed as DRC-clean M2 metal art in the leftover
  space between the core and RING_OSC.
- The full chip (core + RING_OSC + logo) is confirmed **DRC/LVS clean**
  under real KLayout.

## Changes made specifically for this export (not present in the source)

- The real frame cell, named `OSS_FRAME_GIO` in the source repo, was
  renamed to `OSS_FRAME` in this copy only, to match this template's
  `scripts/pre_check.py` naming check. The source repo keeps
  `OSS_FRAME_GIO` (that name is used throughout its own scripts/docs).
- A handful of dead, unreferenced standard-cell definitions left over from
  an earlier synthesis pass (`AND3_X1`, `NAND4`, `DFF`, `TAP3`, `DFFS`) were
  dropped so the GDS has exactly one top-level cell, as this template
  requires. Verified (full-layer XOR diff) to leave the actual design
  geometry byte-for-byte unchanged.
- `.spice` was renamed to `.cir` to match `info.yaml`'s `lvs.extension`.
