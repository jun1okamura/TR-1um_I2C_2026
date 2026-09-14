#!/usr/bin/env python3
"""place.py -- TD4 の標準セル配置。**STEP ごとに GDS を残す**。

  usage:
    python3 scripts/pnr/place.py
    python3 scripts/pnr/place.py --restarts 2000 --order-passes 80 --seed 3

`TR-1um_SCLK_SPI/scripts/place.py` の派生。配置規約（I2C 実チップの GDS から
実測したもの）は同じ:

  * セルは prBoundary (235/0) でアバット。回転・反転なし（行はミラーしない）
  * 行は x=0 から始まり ROW_WIDTH_UM ちょうどで終わる
  * TAP2 は全行同じ x（0 / 534.6 / 1069.2 / 行幅-10.8）— **縦 M2 電源メッシュ用**
  * 残りは FILL3(16.2) / FILL2(10.8) で埋め、TAP 直後の 1 枠は優先 M2 コリドー

TD4 で増えたもの = **ハードマクロ `REG8x16`**。

  信号ピン 21 本 (ADD/WEB/D/Q) は全部 M2 で**下辺 1 列** (y 1.1…4.5)、
  OBS は M1/M2 とも全面。したがってピンの真下にチャネルが要る。
  `td4_config.macro_box()` はマクロを ch[0] ぶん持ち上げて **row0 の底面と
  面一**にしてある。チャネルルータから見ると「933 µm 高い row0 のセル」。

  配置器での扱い:
    - 行割当では**擬似行 -1**（row0 の下）に固定する。マクロにつながるネットは
      ch[0] から出発するので、自然に「低い行ほど有利」という力が働く。
    - 行内順序では**固定の x アンカー**（ピンの実座標）として効かせる。
    - 行幅の計算には入れない（行に置かない）。

STEP:
  step1  行割当        FM 風分割。セルは x=0 からアバット（TAP/FILL なし）
  step2  行内順序      バリセンタ反復（HPWL 評価）
  step3  TAP 挿入      固定ピッチのセグメント分割
  step4  FILL 挿入     行幅を厳密に揃える（最終）
"""

from __future__ import annotations
import argparse, json, os, random, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import td4_config as cfg                                    # noqa: E402
import netlist_util as nu                                   # noqa: E402
import lef_parser                                           # noqa: E402

EPOCH = __import__("datetime").datetime(2026, 1, 1)   # GDS ヘッダの固定日付
SUPPLY = {"VDD", "VSS", "GND", "vdd", "vss", "gnd",
          "1'b0", "1'b1", "1'h0", "1'h1"}
MACRO = cfg.MACRO_NET_CELL     # ネットリスト上の名前
MACRO_PHYS = cfg.MACRO_CELL    # 置く物理セル
# 擬似行。マクロのピン列が向くチャネルの**下**の行に置く。
# 横倒し（帯）は row0 の下なので -1。縦置きで `TD4_MACRO_ROW=k` なら k-1。
MACRO_ROW = (getattr(cfg, "MACRO_ALIGN_ROW", 0)
             if getattr(cfg, "MACRO_MODE", "landscape") == "portrait" else 0) - 1
LOOKAHEAD = 6                  # 区画詰めで先を見る本数（行内順序を崩さない範囲）


# ---------------------------------------------------------------- ネット展開
def expand(pin, expr):
    """`.ADD({ a, b, c, d })` を [(ADD[3], a), (ADD[2], b), ...] に開く。

    連結は **MSB 先頭**。スカラーはそのまま 1 要素。
    """
    e = expr.strip()
    if not e.startswith("{"):
        return [(pin, e)]
    parts = [p.strip() for p in e[1:-1].split(",")]
    n = len(parts)
    return [(f"{pin}[{n - 1 - i}]", p) for i, p in enumerate(parts)]


def load(net_path, info_path):
    src = open(net_path).read()
    insts = nu.parse(src)
    info = json.load(open(info_path))

    macro = [i for i in insts if i.cell == MACRO]
    if len(macro) != 1:
        raise SystemExit(f"{MACRO} のインスタンスが {len(macro)} 個。1 個のはず")
    macro = macro[0]
    cells = [i for i in insts if i is not macro]

    width = {i.name: info[i.cell]["width_um"] for i in cells}
    cellof = {i.name: i.cell for i in cells}

    m = re.search(r"module\s+\w+\s*\((.*?)\)\s*;", src, re.DOTALL)
    ports = {p.strip() for p in m.group(1).split(",") if p.strip()} if m else set()

    net_cells = defaultdict(set)
    macro_pin = {}                       # net -> マクロのピン名
    for i in insts:
        for pin, expr in i.conns.items():
            for pn, n in expand(pin, expr):
                n = n.strip()
                if n in SUPPLY or not n:
                    continue
                net_cells[n].add(i.name)
                if i is macro:
                    macro_pin[n] = pn
    # **set のままにしない。** 集合の反復順は PYTHONHASHSEED で毎回変わり、
    # バリセンタの sum(xs)/len(xs) が丸めの最下位で揺れて順序が入れ替わる。
    # 同じ seed でも GDS が一致しなくなるので、ここで順序を固定する。
    net_cells = {k: sorted(v) for k, v in sorted(net_cells.items())}
    return cells, macro, width, cellof, net_cells, ports, macro_pin


def macro_pin_x(macro_pin):
    """net -> マクロのピン中心 x（コアローカル）。LEF から実測。"""
    lef = lef_parser.parse_lef(cfg.LEF_PATH)[MACRO_PHYS]["pins"]
    mx0, my0, _, _ = cfg.macro_box()
    out = {}
    for net, pn in macro_pin.items():
        r = lef[pn]["rects"]
        if not r:
            raise SystemExit(f"{MACRO} のピン {pn} に矩形が無い")
        out[net] = (mx0 + (r[0][1] + r[0][3]) / 2.0, my0 + (r[0][2] + r[0][4]) / 2.0)
    return out


# ------------------------------------------------------------------ 行割当
def cut_cost(assign, net_cells):
    c = 0
    for cells in net_cells.values():
        rows = {assign[x] for x in cells if x in assign}
        if len(rows) > 1:
            c += max(rows) - min(rows)
    return c


def row_widths(assign, width, n):
    w = [0.0] * n
    for x, r in assign.items():
        if x in width:
            w[r] += width[x]
    return w


def balanced_init(names, width, n, rng, cap):
    order = names[:]
    rng.shuffle(order)
    assign, cur, r = {}, 0.0, 0
    for x in order:
        if cur + width[x] > cap and r < n - 1:
            r += 1
            cur = 0.0
        assign[x] = r
        cur += width[x]
    return assign


def refine(assign, width, net_cells, n, cap, fixed, passes=60):
    best = cut_cost(assign, net_cells)
    for _ in range(passes):
        improved = False
        w = row_widths(assign, width, n)
        for x in list(assign):
            if x in fixed:
                continue
            r0 = assign[x]
            for r1 in range(n):
                if r1 == r0 or w[r1] + width[x] > cap:
                    continue
                assign[x] = r1
                c = cut_cost(assign, net_cells)
                if c < best:
                    best = c
                    w[r0] -= width[x]
                    w[r1] += width[x]
                    improved = True
                    break
                assign[x] = r0
        if not improved:
            break
    return best


def partition(names, width, net_cells, n, cap, macro_name, restarts, seed,
              tol=0.02):
    """行を**均す**。上限を実効行幅そのものにすると、カット最小化が働いて
    セルが下の行に寄り、最後の行が空になる（充填率が上がりすぎて
    フィードスルーの隙間が無くなるうえ、TAP セグメントの端数で
    step3 が詰まる）。上限は「平均 x (1+tol)」と実効行幅の小さい方。

    tol は締める方が良い。実測（BUFTH 込み 140 セル / 4,303.8 µm）:

      tol   行の充填率                 カット
      0.10  85, 85, 80, 69, 72 %       137
      0.05  78, 77, 81, 82, 72 %       152
      0.02  79, 79, 79, 74, 79 %       148   <- 既定

    緩めるとカットは 7% ほど減るが行の凸凹が 16 ポイントに広がる。
    チャネル予算には余裕があるのでカットより**均一な充填**を取る。
    混んだ行はフィードスルーの隙間が無くなって配線で詰まる。"""
    cap = min(cap, sum(width.values()) / n * (1.0 + tol))
    rng = random.Random(seed)
    fixed = {macro_name}
    best_a, best_c = None, None
    for _ in range(restarts):
        a = balanced_init(names, width, n, rng, cap)
        a[macro_name] = MACRO_ROW
        c = refine(a, width, net_cells, n, cap, fixed)
        if best_c is None or c < best_c:
            best_a, best_c = dict(a), c
    return best_a, best_c


def crossings(assign, net_cells, ports, n):
    """チャネル i は行 i の**下**。ch[n] だけ最上行の上。"""
    cross = [0] * (n + 1)
    for net, cells in net_cells.items():
        rows = sorted({assign[c] for c in cells if c in assign})
        if not rows:
            continue
        if is_port_net(net, ports):
            up, dn = rows[0] + 1, n - rows[-1]
            rng = range(max(rows[0], 0) + 1) if up <= dn else range(rows[-1] + 1, n + 1)
        else:
            # マクロ（擬似行 -1）を含むネットは rows[0] = -1 になり、
            # range(0, rmax+1) すなわち ch[0] から rmax の上まで数える。
            rng = range(rows[0] + 1, rows[-1] + 1)
        for ch in rng:
            if 0 <= ch <= n:
                cross[ch] += 1
    return cross


def is_port_net(net, ports):
    return net.split("[")[0] in ports or net in ports


# ------------------------------------------------------------------ 行内順序
def hpwl(order, width, net_cells, ports, rows_y, mpin):
    cx, cy = {}, {}
    for r, seq in enumerate(order):
        x = 0.0
        for c in seq:
            cx[c] = x + width[c] / 2.0
            cy[c] = rows_y[r] + cfg.ROW_HEIGHT_UM / 2.0
            x += width[c]
    total = 0.0
    for net, cells in net_cells.items():
        if is_port_net(net, ports):
            continue
        xs = [cx[c] for c in cells if c in cx]
        ys = [cy[c] for c in cells if c in cy]
        if net in mpin:                       # マクロのピンは固定アンカー
            xs.append(mpin[net][0])
            ys.append(mpin[net][1])
        if len(xs) > 1:
            total += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return total


def order_rows(assign, width, net_cells, ports, rows_y, n, mpin,
               passes=40, seed=1):
    rng = random.Random(seed)
    # マクロは `width` を持たない（行に置かない）。擬似行が実在の行番号に
    # なる縦置き `TD4_MACRO_ROW>=1` では、これを外さないと hpwl が
    # `KeyError: 'u_mem'` で落ちる。
    order = [[c for c in assign if assign[c] == r and c in width]
             for r in range(n)]
    for seq in order:
        rng.shuffle(seq)
    best = [list(s) for s in order]
    best_hp = hpwl(order, width, net_cells, ports, rows_y, mpin)

    nets_of = defaultdict(list)
    for net, cells in net_cells.items():
        if is_port_net(net, ports):
            continue
        for c in cells:
            if c in width:
                nets_of[c].append(net)

    for p in range(passes):
        cx = {}
        for r, seq in enumerate(order):
            x = 0.0
            for c in seq:
                cx[c] = x + width[c] / 2.0
                x += width[c]
        for r, seq in enumerate(order):
            key = {}
            for c in seq:
                xs = [cx[o] for net in nets_of[c] for o in net_cells[net]
                      if o in cx and o != c]
                xs += [mpin[net][0] for net in nets_of[c] if net in mpin]
                key[c] = sum(xs) / len(xs) if xs else cx[c]
            seq.sort(key=lambda c: (key[c], c))
        hp = hpwl(order, width, net_cells, ports, rows_y, mpin)
        if hp < best_hp:
            best_hp, best = hp, [list(s) for s in order]
        elif p % 7 == 6:
            r = rng.randrange(n)
            if len(order[r]) > 2:
                i, j = rng.randrange(len(order[r])), rng.randrange(len(order[r]))
                order[r][i], order[r][j] = order[r][j], order[r][i]
    return best, best_hp


# ------------------------------------------------------------- TAP / FILL
def tap_positions(row_w):
    """TAP2 の x。`cfg.TAP_X` があればそれを正とする。

    既定は `TAP_PITCH` (534.6) 刻み + 行末。ただし行幅がピッチの整数倍から
    外れると**最後の区間だけ極端に狭くなる**。実測（縦置き・行幅 1177.2）:
    区間が 502.2 / 502.2 / **64.8** になり、64.8 に回されたセルが入らず
    step3 で「1 個が行に入りきらない」で落ちた。`cfg.TAP_X` で等間隔
    （0 / 388.8 / 777.6 / 1166.4）に置き直すと 3 区間とも 378 µm になる。
    """
    xs = getattr(cfg, "TAP_X", None)
    if xs:
        if abs(xs[-1] - (row_w - cfg.TAP_W)) > 1e-6:
            raise SystemExit(f"cfg.TAP_X の最後 {xs[-1]} が行末 "
                             f"{row_w - cfg.TAP_W} と違う")
        gaps = [b - a for a, b in zip(xs, xs[1:])]
        if gaps and max(gaps) > cfg.TAP_PITCH + 1e-6:
            raise SystemExit(f"cfg.TAP_X の間隔 {max(gaps)} が TAP_PITCH "
                             f"{cfg.TAP_PITCH} を超える")
        return list(xs)
    xs, x = [], 0.0
    while x + cfg.TAP_W <= row_w - cfg.TAP_W:
        xs.append(round(x, 3))
        x += cfg.TAP_PITCH
    xs.append(round(row_w - cfg.TAP_W, 3))
    return xs


MIN_FILL_W = min(w for _n, w in cfg.FILLS)


def pad(width_um):
    """隙間を FILL で埋める。`cfg.FILLS` は広い順。

    残りが「0 か、いちばん狭い FILL 以上」でなければ次のセルに進まない。
    `FILLS` に `FILL1` (5.4) を入れておくと**サイトグリッドの倍数なら
    どんな隙間も埋まる**ので、区画への詰め込みが一気に楽になる
    （優先コリドーを増やすと区画が細かくなり、10.8 刻みでは詰め切れない）。
    """
    out, w = [], round(width_um, 3)
    if w < -1e-6:
        raise ValueError(f"負の隙間 {w}")
    for name, cw in cfg.FILLS:
        while w - cw >= -1e-6 and (abs(w - cw) < 1e-6 or w - cw >= MIN_FILL_W - 1e-6):
            out.append((name, cw))
            w = round(w - cw, 3)
    if abs(w) > 1e-6:
        raise ValueError(f"{w} um の隙間は {[n for n, _ in cfg.FILLS]} で埋められない")
    return out


def fixed_blocks(row_w):
    """行の中で**全行同じ x に固定で置くもの**を返す。[(x, w, kind)]。

      kind='tap'  TAP2。縦 M2 電源メッシュの柱
      kind='pri'  優先 M2 コリドー（FILL2）。**行またぎ用の空き列**

    優先コリドーを TAP 直後の 1 枠だけでなく `cfg.PRI_PITCH` ごとに置く。

    理由: ルータは行を跨ぐたびに「その行で M2 が無い x」を探すが、配置率が
    79% あると M2 の無い x は 216 トラック中 48 本しかなく、しかも FILL の
    位置が行ごとにばらばらなので**同じ x で上下に抜けられない**。
    実測で 155 回の行またぎのうち 63 回が「clear な x が見つからない」と言って
    遠くへ逃げ、それが短絡の主因になっていた。

    全行同じ x に 10.8 µm（2 トラック）を予約すると、ルータはそこを
    優先的に使う（`route_channels_nrow_fm.py` が `FILLPRI_*` を自動検出する）。
    """
    taps = tap_positions(row_w)
    out = [(t, cfg.TAP_W, "tap") for t in taps]
    for a, b in zip(taps, taps[1:]):
        lo, hi = round(a + cfg.TAP_W, 3), b
        xs = []
        x = lo
        while x + cfg.PRI_W <= hi - 1e-6:
            xs.append(x)
            x = round(x + cfg.PRI_PITCH, 3)
        if getattr(cfg, "PRI_MODE", "after") == "both":
            # 次の TAP の**手前**にも 1 枠。これで行末の TAP の左にも
            # 縦に抜ける列ができる（"after" だと行の右端に列が無い）。
            xb = round(hi - cfg.PRI_W, 3)
            if xb - (xs[-1] if xs else lo - cfg.PRI_W) >= cfg.PRI_W - 1e-6:
                xs.append(xb)
        out += [(x, cfg.PRI_W, "pri") for x in xs]
    # 狙い撃ちの追加コリドー（`TD4_PRI_X`）。既存の固定ブロックと重なる物と
    # 行からはみ出す物は黙って捨てる（重なったら packing が壊れるため）。
    for x in getattr(cfg, "PRI_EXTRA_X", []):
        if x < 0 or x + cfg.PRI_W > row_w + 1e-6:
            continue
        if any(x < bx + bw - 1e-6 and bx < x + cfg.PRI_W - 1e-6
               for bx, bw, _k in out):
            continue
        out.append((x, cfg.PRI_W, "pri"))
    return sorted(out)


def row_segments(row_w):
    """固定ブロックの間の空き [(x0, 容量)] と、固定ブロックそのもの。"""
    fx = fixed_blocks(row_w)
    segs = []
    for (x0, w0, _k), (x1, _w1, _k1) in zip(fx, fx[1:]):
        cap = round(x1 - x0 - w0, 3)
        if cap > 1e-6:
            segs.append((round(x0 + w0, 3), cap))
    return fx, segs


def interleave(cells, fills):
    if not fills:
        return list(cells)
    if not cells:
        return list(fills)
    slots = len(cells) + 1
    per = len(fills) / slots
    out, fi, acc = [], 0, 0.0
    for i in range(slots):
        acc += per
        while fi < len(fills) and fi + 1 <= acc + 1e-9:
            out.append(fills[fi])
            fi += 1
        if i < len(cells):
            out.append(cells[i])
    out.extend(fills[fi:])
    return out


def pack_row(seq, width, cellof, row_w, with_tap, with_fill, mode="alternate"):
    """行を組む。戻りは ([(セル名, インスタンス名 or None, x, w), ...], 右端)。

    **FILL の置き方がルータの成否を左右する。** 行を跨ぐ配線は「その行で M2 の
    無い x」を探すので、FILL がどこにどう固まっているかで空き列の数が決まる。

    区画への詰め方（`quota`）:
      素直に左から貪欲に詰めると**手前の区画が満杯になり、余りが右端の区画に
      まとめて落ちる**。実際そうなっていて、どの行も右 1/3 が FILL の塊だった。
      ここでは「残りのセル幅 : 残りの容量」の比で区画ごとの目標量を決めるので、
      FILL は全区画に均等に散る。

    区画内の並べ方（`mode`）:
      alternate    区画ごとに FILL を左右へ振る（偶数区画は右寄せ、奇数区画は
                   左寄せ）。**全行で同じ振り方**にするので、区画の境目に
                   幅の広い空き列が縦一直線に揃う。行を跨ぐ配線はここを通る。
                   `TR-1um_Async_I2C` の anchor-left/right と同じ考え方。
      distributed  FILL を論理セルの間に散らす（幅 10.8 の隙間が多数）。
                   via パッド (3.4) + 間隔 (2.0) が両側に要るので、10.8 の
                   隙間からは**行またぎ用の x が 1 本しか取れない**。
      end          区画の右端にまとめる（旧挙動）。

    TAP の左右に置いた優先コリドー (`PRI_MODE="both"`) は区画に含めない。
    **あれはグローバル配線用の予約**で、通常の FILL では埋めない。
    """
    if not with_tap:
        out, x = [], 0.0
        for c in seq:
            out.append((cellof[c], c, x, width[c]))
            x = round(x + width[c], 3)
        return out, x

    fx, segs = row_segments(row_w)
    out, todo = [], list(seq)
    for x, w, kind in fx:
        if kind == "tap":
            out.append((cfg.TAP_CELL, None, x, w))
        elif with_fill:
            out.append(("__PRI__", None, x, w))

    left_cells = sum(width[c] for c in todo)
    left_cap = sum(c for _x, c in segs)
    picked_by = [[] for _ in segs]
    used_by = [0.0] * len(segs)
    for si, (x0, cap) in enumerate(segs):
        # 残りのセルと残りの容量の比で、この区画に入れる量を決める
        quota = cap if left_cap <= 1e-9 else min(cap, left_cells * cap / left_cap)
        picked, used = picked_by[si], 0.0
        while todo:
            take = None
            for j in range(min(LOOKAHEAD, len(todo))):
                w = width[todo[j]]
                rest = round(cap - used - w, 3)
                if rest < -1e-6 or (1e-6 < rest < MIN_FILL_W - 1e-6):
                    continue
                if used + w > quota + 1e-6 and picked:
                    continue          # 目標を超える。次の区画へ回す
                take = j
                break
            if take is None:
                break
            c = todo.pop(take)
            picked.append((cellof[c], c, width[c]))
            used = round(used + width[c], 3)
        used_by[si] = used
        left_cells = round(left_cells - used, 3)
        left_cap = round(left_cap - cap, 3)

    # --- 取りこぼしの回収 --------------------------------------------------
    # 上は「区画を左から 1 回だけ見る貪欲割り当て」なので、区画が細かいと
    # （= 優先コリドーを増やすと）最後に数個あぶれて step3 が落ちる。
    # 実測: 縦置き・`PRI_PITCH=108` で 2 個あぶれた。
    # **容量の残っている区画へ best-fit で入れ直す**と、行全体に空きがある
    # 限り落ちない。詰め方の性格（quota で均等に散らす）は変えない。
    for c in list(todo):
        w = width[c]
        best, best_rest = None, None
        for si, (x0, cap) in enumerate(segs):
            rest = round(cap - used_by[si] - w, 3)
            if rest < -1e-6 or (1e-6 < rest < MIN_FILL_W - 1e-6):
                continue
            if best is None or rest < best_rest:
                best, best_rest = si, rest
        if best is None:
            continue
        picked_by[best].append((cellof[c], c, w))
        used_by[best] = round(used_by[best] + w, 3)
        todo.remove(c)

    for si, (x0, cap) in enumerate(segs):
        picked, used = picked_by[si], used_by[si]
        gap = round(cap - used, 3)
        fills = [(fn, None, fw) for fn, fw in
                 (pad(gap) if (with_fill and gap > 1e-6) else [])]
        if mode == "distributed":
            items = interleave(picked, fills)
        elif mode == "alternate":
            items = (picked + fills) if si % 2 == 0 else (fills + picked)
        else:
            items = picked + fills
        x = x0
        for name, inst, w in items:
            out.append((name, inst, x, w))
            x = round(x + w, 3)
    if todo:
        raise SystemExit(f"!! {len(todo)} 個が行に入りきらない: {todo[:5]}")
    end = round(row_w, 3) if with_fill else max(x + w for _, _, x, w in out)
    out.sort(key=lambda e: e[2])
    return out, end


# ------------------------------------------------------------------ GDS 出力
def write_gds(path, rows, rows_y, macro_inst, info, top=None):
    import gdstk
    top = top or cfg.TOP_CELL_NAME
    lib = gdstk.read_gds(cfg.CELL_GDS)
    src = {c.name: c for c in lib.cells}
    out = gdstk.Library(name=top, unit=1e-6, precision=1e-9)

    keep = {MACRO_PHYS}
    for row in rows:
        for cname, _, _, _ in row:
            keep.add(cfg.PRI_CELL if cname == "__PRI__" else cname)

    def add_deep(c, seen):
        if c.name in seen:
            return
        seen.add(c.name)
        out.add(c)
        for r in c.references:
            add_deep(r.cell, seen)

    seen = set()
    for n in sorted(keep):
        add_deep(src[n], seen)

    core = out.new_cell(top)
    for r, row in enumerate(rows):
        for cname, _, x, _ in row:
            core.add(gdstk.Reference(
                src[cfg.PRI_CELL if cname == "__PRI__" else cname], (x, rows_y[r])))
    # マクロ。GDS のセル原点は prBoundary 左下ではないので実測オフセットを足す。
    mx0, my0, _, _ = cfg.macro_box()
    ox, oy = info[MACRO_PHYS]["origin"]
    core.add(gdstk.Reference(src[MACRO_PHYS], (mx0 - ox, my0 - oy)))

    cw, ch = cfg.core_size()
    core.add(gdstk.rectangle((0, 0), (cw, ch), layer=235, datatype=0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # **タイムスタンプを固定する。** 既定では書き出し時刻が GDS のヘッダに
    # 入るので、同じ配置でもファイルの md5 が毎回変わって「配置が変わったのか
    # 書き直しただけか」が区別できない。日付を捨てて再現性を取る。
    out.write_gds(path, timestamp=EPOCH)
    return path


def dump(step, tag, rows, rows_y, macro_inst, info, extra, verbose=True):
    d = os.path.join(cfg.LAYOUT, f"step{step}")
    os.makedirs(d, exist_ok=True)
    gds = os.path.join(d, f"place_step{step}_{tag}.gds")
    write_gds(gds, rows, rows_y, macro_inst, info)
    cw, ch = cfg.core_size()
    js = os.path.join(d, f"place_step{step}_{tag}.json")
    mx0, my0, mx1, my1 = cfg.macro_box()
    data = dict(step=step, tag=tag, core_w=cw, core_h=ch,
                row_h=cfg.ROW_HEIGHT_UM, row_y=rows_y,
                row_width=cfg.ROW_WIDTH_UM,
                ch_heights=cfg.CH_HEIGHTS,
                macro=dict(cell=MACRO_PHYS, net_cell=MACRO, inst=macro_inst,
                           box=[mx0, my0, mx1, my1]),
                rows=[[dict(cell=(cfg.PRI_CELL if c == "__PRI__" else c),
                            inst=i, x=x, w=w, pri=(c == "__PRI__"))
                       for c, i, x, w in row] for row in rows], **extra)
    json.dump(data, open(js, "w"), indent=1)
    if verbose:
        used = [sum(w for _, _, _, w in row) for row in rows]
        print(f"  step{step} {tag:8} -> {os.path.relpath(gds, cfg.ROOT)}")
        print(f"        行: " + ", ".join(f"{u:.1f}" for u in used)
              + f" um   コア {cw:.1f} x {ch:.1f} um")
    return gds


# ---------------------------------------------------------------------- main
def main(net_path=None, info_path=None, restarts=800, order_passes=40,
         seed=7, fill_mode="alternate", tol=0.02):
    net_path = net_path or cfg.NET_PATH
    info_path = info_path or cfg.CELL_INFO
    if not os.path.exists(info_path):
        raise SystemExit(f"{info_path} が無い。先に scripts/pnr/mkcellinfo.py")

    cells, macro, width, cellof, net_cells, ports, macro_pin = \
        load(net_path, info_path)
    info = json.load(open(info_path))
    mpin = macro_pin_x(macro_pin)
    names = [c.name for c in cells]
    n, row_w = cfg.N_ROWS, cfg.ROW_WIDTH_UM

    fx = fixed_blocks(row_w)
    taps = sum(1 for _x, _w, k in fx if k == "tap")
    pris = sum(1 for _x, _w, k in fx if k == "pri")
    usable = row_w - sum(w for _x, w, _k in fx)
    total = sum(width.values())
    print(f"配置: 標準セル {len(cells)} 個 / 幅合計 {total:.1f} um")
    print(f"      + マクロ {MACRO_PHYS}（ネットリストでは {MACRO}）{macro.name} "
          f"{cfg.MACRO_W} x {cfg.MACRO_H} um @ {cfg.macro_box()}")
    print(f"      {n} 行 x {row_w:.1f} um（TAP {taps} + 優先コリドー {pris}"
          f"（{cfg.PRI_PITCH} um ごと）を引いて実効 {usable:.1f} um/行、"
          f"計 {n*usable:.1f} um）")
    if total > n * usable:
        raise SystemExit(f"!! 入らない: {total:.1f} um 必要、{n*usable:.1f} um しかない")
    print(f"      マクロのパッド {len(mpin)} 本は y {cfg.macro_box()[3]-4.5:.1f}…"
          f"{cfg.macro_box()[3]-1.1:.1f}（ルータ座標の下）から ch[0] を向く")

    rows_y, _ = cfg.row_y()

    # ---- step1: 行割当
    assign, cut = partition(names, width, net_cells, n, usable, macro.name,
                            restarts, seed, tol=tol)
    cross = crossings(assign, net_cells, ports, n)
    need = [c * cfg.TRACK_PITCH for c in cross]
    print(f"  行割当: チャネル交差 {cross} → 必要 "
          + ", ".join(f"{h:.0f}" for h in need) + " um")
    print(f"          予算 " + ", ".join(f"{h:.0f}" for h in cfg.CH_HEIGHTS) + " um")
    tight = [i for i, (a, b) in enumerate(zip(need, cfg.CH_HEIGHTS)) if a > b]
    if tight:
        print(f"  ** ch{tight} は見積りが予算を超えている（ルータのジョグでさらに"
              f"増えるので td4_config.CH_HEIGHTS を見直すこと）")

    order = [[c for c in names if assign[c] == r] for r in range(n)]
    hp1 = hpwl(order, width, net_cells, ports, rows_y, mpin)
    rows = [pack_row(s, width, cellof, row_w, False, False)[0] for s in order]
    dump(1, "rows", rows, rows_y, macro.name, info,
         dict(assign=assign, cut=cut, channel_crossings=cross,
              hpwl_um=round(hp1, 1)))

    # ---- step2: 行内順序
    order, hp2 = order_rows(assign, width, net_cells, ports, rows_y, n, mpin,
                            passes=order_passes, seed=seed)
    rows = [pack_row(s, width, cellof, row_w, False, False)[0] for s in order]
    print(f"  行内順序: HPWL {hp1:.0f} → {hp2:.0f} um "
          f"({(hp1-hp2)/hp1*100:.1f}% 改善)")
    dump(2, "ordered", rows, rows_y, macro.name, info,
         dict(assign=assign, hpwl_um=round(hp2, 1)))

    # ---- step3: TAP
    rows = [pack_row(s, width, cellof, row_w, True, False)[0] for s in order]
    dump(3, "tap", rows, rows_y, macro.name, info,
         dict(assign=assign, tap_x=tap_positions(row_w),
              pri_x=[x for x, _w, k in fixed_blocks(row_w) if k == "pri"],
              segments=row_segments(row_w)[1]))

    # ---- step4: FILL（最終）
    packed = [pack_row(s, width, cellof, row_w, True, True, fill_mode)
              for s in order]
    rows = [p[0] for p in packed]
    gds = dump(4, "fill", rows, rows_y, macro.name, info,
               dict(assign=assign, tap_x=tap_positions(row_w),
                    pri_x=[x for x, _w, k in fixed_blocks(row_w) if k == "pri"],
                    channel_crossings=cross, hpwl_um=round(hp2, 1),
                    row_end_x=[p[1] for p in packed]))

    ra = os.path.join(cfg.LAYOUT, "row_assignment.json")
    json.dump({k: v for k, v in assign.items() if k != macro.name},
              open(ra, "w"), indent=1)
    print(f"  wrote {os.path.relpath(ra, cfg.ROOT)}")
    return gds


if __name__ == "__main__":
    # --- 決定性: PYTHONHASHSEED を固定して自分を起動し直す ----------------
    # ルータのどこかで**集合を反復している**（未特定）。集合の反復順は
    # PYTHONHASHSEED で毎回変わるので、**同じ配置 JSON から走らせても結果が
    # 変わる**。実測: seed=1 の同一配置 (md5 31d6cb77…) で step6 が
    # 3 短絡 → 0 短絡と揺れた。ここで固定して、再現しない結果を掴まされない
    # ようにする。
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable] + sys.argv)
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--netlist", default=None)
    ap.add_argument("--cell-info", default=None)
    ap.add_argument("--restarts", type=int, default=800)
    ap.add_argument("--order-passes", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--fill-mode", choices=("alternate", "distributed", "end"),
                    default="alternate")
    ap.add_argument("--balance-tol", type=float, default=0.02,
                    help="行幅の許容ばらつき（平均比）。緩めるとカットは減るが"
                         "行が凸凹になる")
    a = ap.parse_args()
    main(a.netlist, a.cell_info, a.restarts, a.order_passes, a.seed, a.fill_mode,
         a.balance_tol)
