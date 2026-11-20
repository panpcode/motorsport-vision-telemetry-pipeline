"""Lap comparison figure: speed / throttle / brake / delta by distance + track map."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection

MINI_SECTORS = 25


def colours(res):
    ca, cb = res["lap_a"]["team_colour"], res["lap_b"]["team_colour"]
    return ca, (cb if cb.lower() != ca.lower() else "#888888")  # teammates share a colour


def plot(res, path):
    a, b, delta = res["a"], res["b"], res["delta"]
    A, B = res["lap_a"]["driver"], res["lap_b"]["driver"]
    ca, cb = colours(res)
    d = a["d"]

    fig = plt.figure(figsize=(16, 9))
    gs = fig.add_gridspec(4, 2, width_ratios=[2.2, 1], height_ratios=[3, 1.2, 0.8, 2], hspace=0.08, wspace=0.12)
    ax_v, ax_t, ax_b, ax_d = (fig.add_subplot(gs[i, 0]) for i in range(4))
    for ax in (ax_t, ax_b, ax_d):
        ax.sharex(ax_v)

    ax_v.plot(d, a["speed"], color=ca, label=A, lw=1.4)
    ax_v.plot(d, b["speed"], color=cb, label=B, lw=1.4)
    ax_v.set_ylabel("Speed (km/h)")
    ax_v.legend(loc="lower right")
    ax_t.plot(d, a["throttle"], color=ca, lw=1.2)
    ax_t.plot(d, b["throttle"], color=cb, lw=1.2)
    ax_t.set_ylabel("Throttle %")
    ax_b.fill_between(d, 0.5, 0.5 + 0.45 * a["brake"], step="mid", color=ca, lw=0)
    ax_b.fill_between(d, 0.5, 0.5 - 0.45 * b["brake"], step="mid", color=cb, lw=0)
    ax_b.set_yticks([0.25, 0.75], [B, A])
    ax_b.set_ylabel("Brake")
    ax_d.plot(d, delta, color="black", lw=1.4)
    ax_d.axhline(0, color="grey", lw=0.6)
    ax_d.fill_between(d, 0, delta, where=delta >= 0, color=ca, alpha=0.25, lw=0)
    ax_d.fill_between(d, 0, delta, where=delta < 0, color=cb, alpha=0.25, lw=0)
    ax_d.set_ylabel(f"Gap {B} to {A} (s)\n↑ {A} ahead")
    ax_d.set_xlabel("Distance (m)")

    # Corner markers + gain/loss labels
    for c in res["corners"]:
        for ax in (ax_v, ax_t, ax_b, ax_d):
            ax.axvline(c["apex_m"], color="grey", lw=0.5, ls=":")
        ax_v.annotate(f"C{c['corner']}", (c["apex_m"], a["speed"].min() - 15), ha="center", fontsize=9)
        col = ca if c["faster"] == A else cb
        ax_d.annotate(f"{c['faster']} {abs(c['time_diff_s']):.2f}", (c["apex_m"], ax_d.get_ylim()[1]),
                      ha="center", va="top", fontsize=8, color=col, weight="bold")
    for ax in (ax_v, ax_t, ax_b):
        ax.tick_params(labelbottom=False)
    ax_v.set_ylim(a["speed"].min() - 25, None)

    # Track map coloured by who is faster in each mini-sector
    ax_m = fig.add_subplot(gs[:, 1])
    edges = np.linspace(0, len(d) - 1, MINI_SECTORS + 1).astype(int)
    for i0, i1 in zip(edges[:-1], edges[1:]):
        gained = delta[i1] - delta[i0]  # > 0: A faster here
        pts = np.c_[a["x"][i0:i1 + 1], a["y"][i0:i1 + 1]]
        segs = np.stack([pts[:-1], pts[1:]], axis=1)
        ax_m.add_collection(LineCollection(segs, colors=ca if gained > 0 else cb, linewidths=5))
    for c in res["corners"]:
        i = int(c["apex_m"] / d[-1] * (len(d) - 1))
        ax_m.annotate(f"C{c['corner']}", (a["x"][i], a["y"][i]), fontsize=9, ha="center",
                      xytext=(0, 9), textcoords="offset points")
    ax_m.plot(a["x"][0], a["y"][0], "k>", ms=9)
    ax_m.set_aspect("equal")
    ax_m.autoscale()
    ax_m.axis("off")
    ax_m.set_title("Faster per mini-sector", fontsize=11)
    ax_m.legend(handles=[plt.Line2D([], [], color=ca, lw=5, label=A),
                         plt.Line2D([], [], color=cb, lw=5, label=B)], loc="lower center", ncol=2, frameon=False)

    fig.suptitle(res.get("title", f"{A} vs {B}"), fontsize=14, weight="bold", x=0.36)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
