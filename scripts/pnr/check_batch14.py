#!/usr/bin/env python3
"""check_batch14.py -- ngspice の `.measure` 出力を 14 項目で判定する。

  usage: python3 scripts/pnr/check_batch14.py layout/chip/simulation/batch14.log

V10 の `reference/v10/check_batch14_v10.py` と**判定の論理は同じ**。
参照する JSON だけ `layout/chip/simulation/spice_batch14_expected.json`
（`gen_chip_tb_batch14.py` が TB と一緒に書く）に変えてある。

ngspice のバッチ出力は `name = value` の 1 行。評価できなかった measure は
`name = failed` になるので、その項目だけ NG にして全体は落とさない。
IRSIM / Verilog / V10 の SPICE と**同じ 14 項目・同じ書式**で出すので、
横に並べて比べられる。
"""
import json
import re
import sys
from pathlib import Path

VDD = 5.0
THRESH = VDD / 2

# ngspice batch .measure output is a plain "name = value" line (scientific
# notation), possibly with surrounding whitespace; a measure that could not
# be evaluated instead prints "name = failed" (no value) -- treated as an
# error for that check rather than crashing the whole parse.
MEASURE_RE = re.compile(r"^\s*(\S+)\s*=\s*(\S+)\s*$")


def parse_measures(log_text):
    values = {}
    for line in log_text.splitlines():
        m = MEASURE_RE.match(line)
        if not m:
            continue
        name, raw = m.group(1), m.group(2)
        try:
            values[name] = float(raw)
        except ValueError:
            values[name] = None   # "failed" or other non-numeric result
    return values


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <ngspice_log_file>")
        sys.exit(1)

    log_path = Path(sys.argv[1])
    expected_path = (Path(__file__).resolve().parents[2]
                     / "layout" / "chip" / "simulation"
                     / "spice_batch14_expected.json")

    values = parse_measures(log_path.read_text())
    checks = json.loads(expected_path.read_text())

    n_pass = 0
    n_fail = 0
    for c in checks:
        name = c["name"]
        desc = c["desc"]
        t_report = c["t"] if c["kind"] == "level" else (
            c["t"][0] if isinstance(c["t"], list) else c["t"]
        )

        if c["kind"] == "level":
            v = values.get(name)
            if v is None:
                ok = False
                detail = "measure not found / failed"
            else:
                is_high = v > THRESH
                expect_high = (c["expect"] == "high")
                ok = (is_high == expect_high)
                detail = f"{v:.3f}V"
        else:   # byte
            bits = [None] * 8
            missing = False
            for i, bit_idx in enumerate(c["bit_indices"]):
                v = values.get(f"{name}_bit{i}")
                if v is None:
                    missing = True
                    continue
                bits[bit_idx] = 1 if v > THRESH else 0
            if missing or any(b is None for b in bits):
                ok = False
                detail = "one or more bit measures not found / failed"
            else:
                got = 0
                for i, bit in enumerate(bits):
                    got |= (bit << i)
                ok = (got == c["expect"])
                detail = f"got 0x{got:02X}, expected 0x{c['expect']:02X}"

        status = "OK" if ok else "FAIL"
        if ok:
            n_pass += 1
        else:
            n_fail += 1
        print(f"[t={t_report * 1e9:.0f}ns] {status}: {desc:<55s} ({detail})")

    print()
    print("---- RESULT ----")
    if n_fail == 0:
        print(f"All {n_pass} checks PASSED")
    else:
        print(f"{n_pass} passed, {n_fail} FAILED")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
