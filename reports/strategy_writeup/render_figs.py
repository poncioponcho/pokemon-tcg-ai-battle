#!/usr/bin/env python3
"""Render the 6 media-gallery figures for the Strategy writeup.

Data source: reports/strategy_writeup/media_gallery_spec.md (+ writeup_en.md 2/3/5).
All numbers traceable to 00_框架.md section 1 (canonical truth).

Regenerate after the 8/31 final LB numbers land:
  update the SINGLE-SOURCE constants marked <<< FINAL-NUMBER >>> below, re-run:
  /Users/seyonmacbook/.workbuddy/binaries/python/envs/default/bin/python render_figs.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
from math import sqrt
from pathlib import Path

OUT = Path(__file__).resolve().parent / "figs"
OUT.mkdir(exist_ok=True)

# <<< FINAL-NUMBER >>> single source for live results (locked 2026-09-01)
FINAL_RATING = 830.9        # final public/private rating (team 874/6807, LB 2026-09-01)
FINAL_RANK = 874            # rank
FINAL_TEAMS = 6807          # team count
FINAL_TOP_PCT = 12.8        # top ~12.8%

# ---- flat palette ----
INK = "#26215C"
DARK = "#2C2C2A"
MUTE = "#6B6A66"
PURPLE = "#534AB7"
PURPLE_M = "#AFA9EC"
PURPLE_L = "#EEEDFE"
TEAL = "#0F6E56"
TEAL_M = "#5DCAA5"
TEAL_L = "#E1F5EE"
AMBER = "#854F0B"
AMBER_M = "#EF9F27"
AMBER_L = "#FAEEDA"
GRAY_L = "#F1EFE8"
GRAY_M = "#B4B2A9"
GRAY_D = "#5F5E5A"

plt.rcParams["font.family"] = "DejaVu Sans"
MONO = "DejaVu Sans Mono"

W = 190.0
UPI = 20.0  # canvas units per inch -> 190u = 9.5in wide


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def new_ax(h_units):
    fig = plt.figure(figsize=(W / UPI, h_units / UPI), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, h_units)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    return fig, ax


def rbox(ax, x, y, w, h, fc, ec, lw=1.0, rs=1.6, z=1, ls="solid"):
    b = FancyBboxPatch((x, y), w, h,
                       boxstyle="round,pad=0,rounding_size=%s" % rs,
                       facecolor=fc, edgecolor=ec, linewidth=lw, zorder=z,
                       linestyle=ls)
    ax.add_patch(b)
    return b


def T(ax, x, y, s, size=10, color=DARK, weight="normal", ha="left", va="center",
      family=None, z=3, style="normal", lsp=1.35, rotation=0):
    return ax.text(x, y, s, fontsize=size, color=color, fontweight=weight,
                   ha=ha, va=va, zorder=z, family=family, style=style,
                   linespacing=lsp, rotation=rotation)


def save(fig, name):
    p = OUT / name
    fig.savefig(p, dpi=200, facecolor="white")
    plt.close(fig)
    print("wrote", p)


# ---------------------------------------------------------------- fig 1
def fig1():
    H = 124
    fig, ax = new_ax(H)
    T(ax, W / 2, 119, "Five layers over a validated fallback", 16, INK, "bold", "center")
    T(ax, W / 2, 113,
      "policies/v22 · ~7,600 lines · 23 guard files · main.py entry is a 3-line forward (§3.1)",
      10, MUTE, ha="center")

    bands = [
        ("LAYER 4", "Guard policies · 23 files",
         "Born from diagnosed replay failures — surgical overrides with documented\ntriggers, each reason recorded in the decision ledger.",
         PURPLE_L, PURPLE, PURPLE, DARK, DARK),
        ("LAYER 3", "Continuity scheduler",
         "Turn-objective & phase inference plus in-game strategic memory; all state\nresets at every episode boundary (replay-audited, zero mismatches).",
         PURPLE_L, PURPLE, PURPLE, DARK, DARK),
        ("LAYER 2", "Deadline ledger",
         "A resource ledger (energy, attachments, supporter, stadium, Boss counts)\ndrives lexicographic deadline scheduling — it expresses 'attach now, the\nattack window closes next turn'; a fixed priority list could not.",
         AMBER_L, AMBER_M, AMBER, DARK, DARK),
        ("LAYER 1", "Processing queue + turn DAG",
         "Committed jobs (evolution, attack setup, board repair) execute through a\ndependency DAG that first completes missing prerequisites, instead of\nblindly running the queue head.",
         PURPLE_L, PURPLE, PURPLE, DARK, DARK),
        ("LAYER 0", "Validated fallback · ~2,545 lines",
         "Sole contract: legality — correct action count, valid indices, no\nduplicates. No code path can emit an invalid action.",
         INK, INK, PURPLE_M, "white", "white"),
    ]
    x0, xw = 14, 164
    top = 108
    bh, gap = 16.5, 1.5
    for i, (tag, name, why, fc, ec, tagc, namec, whyc) in enumerate(bands):
        y = top - i * (bh + gap) - bh
        rbox(ax, x0, y, xw, bh, fc, ec, lw=1.1, rs=1.8)
        T(ax, x0 + 5, top - i * (bh + gap) - 4.6, tag, 8.3, tagc, "bold")
        T(ax, x0 + 5, top - i * (bh + gap) - 10.2, name, 11.3, namec, "bold")
        ax.plot([x0 + 62, x0 + 62], [y + 1.6, y + bh - 1.6],
                color=ec, lw=0.7, alpha=0.55, zorder=2)
        T(ax, x0 + 67, y + bh / 2, why, 9.1, whyc, ha="left", va="center")

    ar = FancyArrowPatch((7.5, 100), (7.5, 27.5), arrowstyle="-|>",
                         mutation_scale=14, color=GRAY_M, lw=1.5, zorder=2)
    ax.add_patch(ar)
    T(ax, 3.3, 64, "any exception degrades", 7.5, MUTE, rotation=90,
      ha="center", va="center")

    rbox(ax, x0, 4, xw, 9.5, GRAY_L, GRAY_M, lw=0.8)
    T(ax, x0 + xw / 2, 8.8,
      "Each layer may only replace the choice of the layer below; any exception, "
      "malformed option, or unknown context degrades to Layer 0.",
      9, MUTE, ha="center")
    save(fig, "fig1_architecture.png")


# ---------------------------------------------------------------- fig 2
def fig2():
    H = 112
    fig, ax = new_ax(H)
    T(ax, W / 2, 106, "The 60-card list — engine · control · consistency", 16, INK, "bold", "center")
    T(ax, W / 2, 100.5,
      "Every slot is an engine piece or a tutor for one — deck-level determinism "
      "matching agent-level determinism (§2.2)", 9.6, MUTE, ha="center")

    # donut
    dax = fig.add_axes([4 / W, 28 / H, 50 / W, 50 / H])
    dax.pie([18, 10, 32], colors=[PURPLE, AMBER_M, TEAL], startangle=90,
            counterclock=False,
            wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2.5))
    dax.text(0, 0, "60\ncards", ha="center", va="center", fontsize=13,
             color=INK, fontweight="bold", linespacing=1.15)
    T(ax, 33, 21.5, "Pokémon 18 · Energy 10 · Trainers 32", 10, DARK, ha="center")

    # table
    tx, tw = 58, 126
    rbox(ax, tx, 84, tw, 9, INK, INK, rs=1.4)
    T(ax, tx + 4, 88.5, "Role", 9.5, "white", "bold")
    T(ax, tx + 32, 88.5, "Key cards", 9.5, "white", "bold")
    T(ax, tx + tw - 4, 88.5, "n", 9.5, "white", "bold", ha="right")

    rows = [
        ("Engine", ["Marnie's Impidimp ×4 · Morgrem ×3 · Grimmsnarl ex ×3"], 10, 10),
        ("Control", ["Munkidori ×4 · Snorunt ×2 · Froslass ×2"], 8, 10),
        ("Energy", ["Basic Darkness ×10"], 10, 10),
        ("Consistency", ["Buddy-Buddy Poffin ×4 · Rare Candy ×3 · Spikemuth Gym ×4",
                         "Team Rocket's Petrel ×4 · Lillie's Determination ×4 · Poké Pad ×4",
                         "Dawn ×1 · Pokégear 3.0 ×1"], 25, 17),
        ("Disruption", ["Night Stretcher ×3 · Boss's Orders ×2 · Unfair Stamp ×1 · Tool Scrapper"], 7, 10),
    ]
    y = 84
    for i, (role, card_lines, n, rh) in enumerate(rows):
        y -= rh
        fc = "white" if i % 2 == 0 else GRAY_L
        rbox(ax, tx, y, tw, rh, fc, GRAY_M, lw=0.6, rs=0.8)
        T(ax, tx + 4, y + rh / 2, role, 9.6, INK, "bold")
        if len(card_lines) == 1:
            fs = 8.3 if role == "Disruption" else 8.8
            T(ax, tx + 32, y + rh / 2, card_lines[0], fs, DARK)
        else:
            T(ax, tx + 32, y + rh / 2, "\n".join(card_lines), 8.4, DARK, lsp=1.45)
        T(ax, tx + tw - 4, y + rh / 2, str(n), 10.5, PURPLE, "bold", ha="right")

    # badges
    badges = [
        ("10 energy, no specials", "Punk Up ends the attachment game on its\nactivation turn"),
        ("21 of 32 trainers", "are search / filter cards"),
        ("Single ACE SPEC", "Unfair Stamp"),
        ("Zero coin-flip cards", "the entire pool was audited"),
    ]
    bw, bgap = 42.5, 2.8
    for i, (h1, h2) in enumerate(badges):
        bx = 8 + i * (bw + bgap)
        rbox(ax, bx, 4, bw, 13.5, PURPLE_L, PURPLE_M, lw=0.9, rs=1.4)
        T(ax, bx + bw / 2, 13.2, h1, 9.3, INK, "bold", ha="center")
        T(ax, bx + bw / 2, 8.2, h2, 8.2, MUTE, ha="center", lsp=1.3)
    save(fig, "fig2_deck.png")


# ---------------------------------------------------------------- fig 3
def fig3():
    H = 116
    fig, ax = new_ax(H)
    T(ax, W / 2, 110, "Local head-to-head — exact final archive", 16, INK, "bold", "center")
    T(ax, W / 2, 104,
      "n = 64 per leg · zero faults in every leg · engine exposes no shuffle seed "
      "(same-seed reruns = independent batches) (§5)", 9.6, MUTE, ha="center")

    groups = [
        ("vs Alakazam", "ability-loop engine · 51–13", 51),
        ("vs retreat-pivot", "own early build · 42–22", 42),
        ("vs full Grim v1", "same cards, other strategy · 39–25", 39),
        ("vs match-up router", "routing-layer candidate · 38–26", 38),
    ]
    x_left, x_right = 58.0, 118.0
    scale = (x_right - x_left) / 100.0
    ys = [88, 74, 60, 46]

    for v in (0, 25, 50, 75, 100):
        xv = x_left + v * scale
        ax.plot([xv, xv], [38, 95], color=GRAY_L if v != 50 else "white",
                lw=0.9, zorder=0)
        T(ax, xv, 34.5, ("%d%%" % v) if v else "0", 8, MUTE, ha="center")
    ax.plot([x_left, x_right], [37.5, 37.5], color=GRAY_M, lw=1.1, zorder=1)
    ax.plot([x_left + 50 * scale, x_left + 50 * scale], [38, 95],
            color=AMBER_M, lw=1.4, ls=(0, (5, 4)), zorder=2)
    T(ax, x_left + 50 * scale, 97.5, "50% — a coin flip", 8.5, AMBER, ha="center")

    for (name, rec, k), cy in zip(groups, ys):
        lo, hi = wilson(k, 64)
        star = (name == "vs Alakazam")
        bc = TEAL if star else TEAL_M
        bw_ = k / 64 * 100 * scale
        rbox(ax, x_left, cy - 3.25, bw_, 6.5, bc, TEAL if star else TEAL,
             lw=0.8 if star else 0.6, rs=1.0, z=3)
        for xv in (x_left + lo * 100 * scale, x_left + hi * 100 * scale):
            ax.plot([xv, xv], [cy - 4.6, cy + 4.6], color=DARK, lw=1.3, zorder=4)
        ax.plot([x_left + lo * 100 * scale, x_left + hi * 100 * scale],
                [cy + 4.6, cy + 4.6], color=DARK, lw=1.3, zorder=4)
        ax.plot([x_left + lo * 100 * scale, x_left + hi * 100 * scale],
                [cy - 4.6, cy - 4.6], color=DARK, lw=1.3, zorder=4)
        T(ax, 55, cy + 2.5, name, 10.2, INK if star else DARK,
          "bold" if star else "bold", ha="right")
        T(ax, 55, cy - 2.8, rec, 8.3, MUTE, ha="right")
        T(ax, x_left + lo * 100 * scale - 1.6, cy + 1.1, "%.1f%%" % (k / 64 * 100),
          10, "white" if star else DARK, "bold", ha="right")

    # why-callout
    rbox(ax, 124, 46, 60, 50, TEAL_L, TEAL_M, lw=1.0, rs=1.8)
    T(ax, 128, 91, "Why Alakazam tops the table", 11, TEAL, "bold")
    body = ("Froslass's Icy Curtain places a damage\ncounter on every Ability Pokémon at each\n"
            "Pokémon Check — symmetric on paper,\nasymmetric in practice: our key ability\n"
            "(Punk Up) fires once per game, while\nability-loop engines pay the tax every\n"
            "turn. Shadow Bullet's fixed 30 bench\ndamage then converts the spread into\n"
            "knockouts over stall walls.")
    T(ax, 128, 68, body, 8.8, DARK, va="center", lsp=1.5)

    # bottom boxes
    rbox(ax, 8, 6, 86, 24, "white", GRAY_M, lw=0.9, rs=1.6)
    T(ax, 12, 26, "Kept the simpler v22", 10.4, TEAL, "bold")
    T(ax, 12, 16.5,
      "v22 vs v29, merged decisive games: 383 played, 208–175 (54.3%),\n"
      "Wilson 95% ≈ 49.3–59.2% — still spans 50%. Non-significance\n"
      "is not a reason to ship an extra routing layer.", 8.7, DARK, lsp=1.5)
    rbox(ax, 98, 6, 86, 24, "white", GRAY_M, lw=0.9, rs=1.6)
    T(ax, 102, 26, "Noise rule", 10.4, AMBER, "bold")
    T(ax, 102, 16.5,
      "Differences inside the calibrated ±2.2pp cross-process band are\n"
      "treated as non-evidence. Every win rate carries a Wilson 95%\n"
      "interval and its batch size n.", 8.7, DARK, lsp=1.5)
    save(fig, "fig3_h2h.png")


# ---------------------------------------------------------------- fig 4
def fig4():
    H = 128
    fig, ax = new_ax(H)
    T(ax, W / 2, 122, "Twenty-three guard policies — named, motivated overrides",
      15.5, INK, "bold", "center")
    T(ax, W / 2, 116.5,
      "Each born from a diagnosed replay failure · every trigger recorded in the "
      "decision ledger · not a heuristic soup (§3.1, Layer 4)", 9.6, MUTE, ha="center")

    cards = [
        ("Stall defense", 3, "Deny Boss's Orders pulls on damaged /\nunenergized basics",
         ["boss_damaged_basic_stall", "boss_unenergized_kadabra_stall", "retreat_morgrem_stall"]),
        ("Energy preservation", 3, "Protect energized evolution-line\nmembers from trades",
         ["energized_impidimp_preservation", "energized_morgrem_preservation",
          "retreat_impidimp_preserve_grimmsnarl"]),
        ("Promotion timing", 6, "Who promotes first — and who is\nsacrificed",
         ["damaged_munkidori_early_promotion", "low_hp_mega_munkidori_promotion",
          "energized_munkidori_promotion", "energized_mixed_basic_promotion",
          "rare_candy_impidimp_promotion", "sacrificial_froslass_mega_promotion"]),
        ("Pre-ability attachment", 4, "Energy goes where it triggers an\nability or attack",
         ["preability_active_impidimp_attachment", "preability_morgrem_attachment",
          "preattack_froslass_attachment", "prestamp_attachment"]),
        ("KO math", 3, "Lethal lines and double-KO arithmetic",
         ["munkidori_lethal", "shadow_bullet_double_ko", "shadow_bullet_immediate_mega_ko"]),
        ("Matchup-specific", 5, "Zoroark boards, dead Poffins, backup\nengine + manual catch-all",
         ["zoroark_guard", "zoroark_pokepad_guard", "dead_poffin_guard",
          "punkup_backup_guard", "manual_guards"]),
    ]
    cw, ch = 54, 50
    xs = [9, 71, 133]
    ys = [62, 6]
    for i, (gname, count, purpose, names) in enumerate(cards):
        cx = xs[i % 3]
        cy = ys[i // 3]
        top = cy + ch
        rbox(ax, cx, cy, cw, ch, PURPLE_L, PURPLE_M, lw=1.0, rs=1.8)
        T(ax, cx + 3, top - 5, gname, 10.6, INK, "bold")
        c = Circle((cx + cw - 5.5, top - 5), 2.9, facecolor=PURPLE,
                   edgecolor="none", zorder=3)
        ax.add_patch(c)
        T(ax, cx + cw - 5.5, top - 5.05, str(count), 9.3, "white", "bold",
          ha="center", va="center", z=4)
        T(ax, cx + 3, top - 11.5, purpose, 8.2, MUTE, lsp=1.35)
        ax.plot([cx + 3, cx + cw - 3], [top - 15.5, top - 15.5],
                color=PURPLE_M, lw=0.7, zorder=2)
        for j, nm in enumerate(names):
            T(ax, cx + 3, top - 19.5 - j * 3.6, nm, 7.5, DARK, family=MONO)
    save(fig, "fig4_guards.png")


# ---------------------------------------------------------------- fig 5
def fig5():
    H = 108
    fig, ax = new_ax(H)
    T(ax, W / 2, 102, "Live results — one settled number", 16, INK, "bold", "center")
    T(ax, W / 2, 96.5,
      "40 completed submissions · final-2 slots hold the same frozen archive · "
      "only attributed, settled numbers are counted (§5)", 9.6, MUTE, ha="center")

    T(ax, 12, 60, "≈%d" % FINAL_RATING, 54, INK, "bold")
    T(ax, 14.5, 42, "converged final rating", 12.5, MUTE)
    T(ax, 14.5, 33, "rank %s / %s teams · top ≈%.1f%%" %
      ("{:,}".format(FINAL_RANK), "{:,}".format(FINAL_TEAMS), FINAL_TOP_PCT),
      14.5, DARK)

    rbox(ax, 8, 10, 50, 14, TEAL_L, TEAL_M, lw=0.9, rs=1.4)
    T(ax, 11, 19.3, "40 submissions", 10.3, TEAL, "bold")
    T(ax, 11, 14.2, "zero runtime errors", 8.7, MUTE)
    rbox(ax, 62, 10, 50, 14, PURPLE_L, PURPLE_M, lw=0.9, rs=1.4)
    T(ax, 65, 19.3, "final-2 slots = same frozen archive", 8.9, INK, "bold")
    T(ax, 65, 14.2, "SHA-256 599e19ae…", 8.7, MUTE)

    rbox(ax, 118, 10, 66, 78, GRAY_L, GRAY_M, lw=1.0, rs=1.8)
    T(ax, 122, 82, "Transient — not a settled value", 10.6, GRAY_D, "bold")
    ax.plot([122, 180], [77.5, 77.5], color=GRAY_M, lw=0.8)
    body = ("Mature reference 55539446 — first 29 public\nepisodes: 15–14 (51.7%) against an opponent\n"
            "mean of 812 → implied strength ≈830.\n\n"
            "A 29-game window sits at the edge of our own\n±2.2pp noise band — quoted for completeness,\n"
            "never as a headline.\n\n"
            "Early reads (e.g. 883.1) are unconverged\nvalues: not counted.")
    T(ax, 122, 50, body, 8.7, GRAY_D, va="center", lsp=1.55)

    T(ax, W / 2, 3.2,
      "Episodes attributed by submission ID, corrected for opponent mean strength; "
      "instantaneous score spikes were never chased (§4, live-read discipline).",
      8.4, MUTE, ha="center")
    save(fig, "fig5_lb.png")


# ---------------------------------------------------------------- fig 6
def fig6():
    H = 132
    fig, ax = new_ax(H)
    T(ax, W / 2, 126, "The measurement loop — measure first, then cut",
      16, INK, "bold", "center")
    T(ax, W / 2, 120.5,
      "Our originality claim is the discipline, not any single algorithm — "
      "every number in this writeup passed through this loop (§4)",
      9.6, MUTE, ha="center")

    stages = [
        ("Replay diagnosis", "failed games → hypotheses (collector + F2 slices)",
         PURPLE_L, PURPLE, PURPLE),
        ("Single-card hill-climb", "screen n=1000 → confirm n=4000 · joint fitness: mirror + vs_first",
         PURPLE_L, PURPLE, PURPLE),
        ("Three-seed gate", "Wilson 95% lower bounds, benchmark-calibrated",
         PURPLE_L, PURPLE, PURPLE),
        ("Classify", "STRONG / MARGINAL / REGRESS", AMBER_L, AMBER_M, AMBER),
        ("Freeze the exact archive", "two packings, identical SHA-256 → unpack & re-verify",
         TEAL_L, TEAL_M, TEAL),
        ("Isolated-runner H2H", "four opponent families · zero faults to ship",
         PURPLE_L, PURPLE, PURPLE),
        ("Live attribution", "episodes by submission ID + opponent-strength correction",
         PURPLE_L, PURPLE, PURPLE),
    ]
    sx, sw, sh, pitch = 26, 104, 12, 14.8
    top0 = 108
    for i, (name, sub, fc, ec, chip) in enumerate(stages):
        top = top0 - i * pitch
        y = top - sh
        rbox(ax, sx, y, sw, sh, fc, ec, lw=1.0, rs=1.6)
        c = Circle((sx + 7, top - sh / 2), 3.2, facecolor=chip, edgecolor="none", zorder=3)
        ax.add_patch(c)
        T(ax, sx + 7, top - sh / 2 - 0.05, str(i + 1), 10.3, "white", "bold",
          ha="center", va="center", z=4)
        T(ax, sx + 13.5, top - 4.3, name, 10.8, INK, "bold")
        T(ax, sx + 13.5, top - 9, sub, 8.8, MUTE)
        if i < len(stages) - 1:
            ar = FancyArrowPatch((sx + sw / 2, y - 0.4),
                                 (sx + sw / 2, y - pitch + sh + 0.4),
                                 arrowstyle="-|>", mutation_scale=13,
                                 color=PURPLE_M, lw=1.8, zorder=2)
            ax.add_patch(ar)

    # rejection side-path from stage 4
    s4_top = top0 - 3 * pitch
    s4_mid = s4_top - sh / 2
    ar = FancyArrowPatch((sx + sw + 0.5, s4_mid), (131.5, s4_mid),
                         arrowstyle="-|>", mutation_scale=13,
                         color=GRAY_M, lw=1.6, zorder=2)
    ax.add_patch(ar)
    rbox(ax, 132, s4_mid - 12, 56, 24, GRAY_L, GRAY_M, lw=1.0, rs=1.6)
    T(ax, 135.5, s4_mid + 7.5, "Inside ±2.2pp · MARGINAL · REGRESS", 8.6, GRAY_D, "bold")
    T(ax, 135.5, s4_mid - 2.5,
      "recorded, not shipped —\nnegative results are kept\nand pre-registered",
      8.2, GRAY_D, lsp=1.45)

    # feedback loop (dashed)
    fb_y0 = top0 - 6 * pitch - sh / 2
    ax.plot([sx, 16], [fb_y0, fb_y0], color=GRAY_M, lw=1.2,
            ls=(0, (4, 3)), zorder=2)
    ax.plot([16, 16], [fb_y0, top0 - sh / 2], color=GRAY_M, lw=1.2,
            ls=(0, (4, 3)), zorder=2)
    ar = FancyArrowPatch((16, top0 - sh / 2), (sx - 0.5, top0 - sh / 2),
                         arrowstyle="-|>", mutation_scale=12,
                         color=GRAY_M, lw=1.2, zorder=2)
    ax.add_patch(ar)
    T(ax, 12.5, (fb_y0 + top0 - sh / 2) / 2, "next hypothesis", 8, MUTE,
      rotation=90, ha="center", va="center")

    T(ax, W / 2, 4.2,
      "The discipline must be able to kill its own favorites — it retired the\n"
      "team's longest-running line (Mega Lucario) when the Grimmsnarl build measured better on the same gates.",
      8.6, MUTE, ha="center", lsp=1.45)
    save(fig, "fig6_methodology.png")


if __name__ == "__main__":
    fig1()
    fig2()
    fig3()
    fig4()
    fig5()
    fig6()
    print("done.")
