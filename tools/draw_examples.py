import html

THEMES = {
    "light": dict(lane="#f6f8fa", line="#d1d9e0", box="#ffffff", boxs="#59636e", acc="#ddf4ff", accs="#0969da",
                  t="#1f2328", s="#59636e", edge="#59636e", dash="#818b98", bad="#cf222e"),
    "dark": dict(lane="#151b23", line="#3d444d", box="#0d1117", boxs="#9198a1", acc="#121d2f", accs="#4493f8",
                 t="#f0f6fc", s="#9198a1", edge="#9198a1", dash="#656c76", bad="#f85149"),
}

U = ("User", "client app", False)
Q = ("Write queue", "+ leases", False)
API = ("Vendor API", "", False)
DB = ("Source database", "", False)
CAP = ("Change capture", "hints only", True)
ST = ("Store", "+ read models", True)
WA = ("Worker A", "sends intents", False)
WB = ("Worker B", "sends intents", False)
VU = ("Vendor app user", "outside ORCA", False)
CL = ("Client", "local cache", False)
OUT = ("Store", "outbox", True)

# (from, to, label, kind): kind is solid, dash (a signal) or lost (never arrives)
SCENARIOS = {
    "ordinary": ([U, Q, API, DB, CAP, ST], [
        (0, 0, "record intent, show it at once", "solid"),
        (0, 1, "enqueue (lease checked)", "solid"),
        (1, 2, "send (lease checked again)", "solid"),
        (2, 3, "update order 42", "solid"),
        (3, 4, "statement completed", "dash"),
        (4, 5, "hint: orders, key 42", "dash"),
        (5, 3, "re-read order 42, committed only", "solid"),
        (5, 5, "rebuild read models, version 1001", "solid"),
        (5, 0, "version 1001, delivered whole", "dash"),
        (0, 0, "intent judged: state reached", "solid"),
    ]),
    "lost-event": ([U, Q, API, DB, CAP, ST], [
        (1, 2, "send", "solid"),
        (2, 3, "update order 42", "solid"),
        (3, 4, "statement completed: event lost", "lost"),
        (0, 0, "timeout: nothing back yet", "solid"),
        (5, 3, "re-read order 42 (intent's check)", "solid"),
        (5, 5, "changed: version 1001", "solid"),
        (5, 0, "version 1001", "dash"),
        (0, 0, "judged on what arrived, never resent", "solid"),
    ]),
    "rollback": ([U, Q, API, DB, CAP, ST], [
        (1, 2, "send", "solid"),
        (2, 3, "update order 42", "solid"),
        (3, 4, "statement completed", "dash"),
        (3, 3, "transaction rolls back", "solid"),
        (4, 5, "hint: orders, key 42", "dash"),
        (5, 3, "re-read order 42, committed only", "solid"),
        (5, 5, "unchanged: no new version", "solid"),
        (0, 0, "values never arrived: undetermined, shown", "solid"),
    ]),
    "crashed-sender": ([WA, WB, API, DB, ST], [
        (0, 2, "send intent", "solid"),
        (2, 3, "update order 42", "solid"),
        (0, 0, "crashes before recording the send", "lost"),
        (1, 1, "claims the intent: outcome uncertain", "solid"),
        (1, 4, "check order 42 first", "solid"),
        (4, 1, "already holds the change", "dash"),
        (1, 1, "judged on that, API never called twice", "solid"),
    ]),
    "concurrent-edit": ([U, Q, API, DB, VU, ST], [
        (1, 2, "send: status = shipped", "solid"),
        (4, 3, "edits order 42 directly", "solid"),
        (2, 3, "update order 42", "solid"),
        (3, 5, "both changes captured, re-read", "dash"),
        (5, 0, "latest version of order 42", "dash"),
        (0, 0, "same values: state reached / different: undetermined", "solid"),
    ]),
    "offline-client": ([CL, OUT], [
        (0, 0, "offline overnight, last at version 1001", "solid"),
        (0, 1, "resume after 1001", "solid"),
        (1, 0, "outbox still holds it: 1002 onward, whole versions, in order", "dash"),
        (1, 0, "too old: resync read models instead of replaying", "dash"),
    ]),
}


def svg(parts, msgs, c):
    gap = 560 if len(parts) <= 2 else 200
    xs = [130 + gap * i for i in range(len(parts))]
    w = xs[-1] + 130 + (60 if len(parts) <= 2 else 0)
    top, row0, step = 24, 140, 62
    h = row0 + step * len(msgs) + 30
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="system-ui, -apple-system, \'Segoe UI\', Roboto, sans-serif">',
         '<defs>']
    for mid, col in (("a", c["edge"]), ("d", c["dash"]), ("x", c["bad"])):
        o.append(f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>')
    o.append('</defs>')
    for x, (name, sub, acc) in zip(xs, parts):
        o.append(f'<line x1="{x}" y1="{top + 64}" x2="{x}" y2="{h - 16}" stroke="{c["line"]}" stroke-width="1.5" stroke-dasharray="2 6"/>')
        fill, stroke = (c["acc"], c["accs"]) if acc else (c["box"], c["boxs"])
        o.append(f'<rect x="{x - 85}" y="{top}" width="170" height="64" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
        o.append(f'<text x="{x}" y="{top + (30 if sub else 38)}" text-anchor="middle" font-size="16" font-weight="650" fill="{c["t"]}">{html.escape(name)}</text>')
        if sub:
            o.append(f'<text x="{x}" y="{top + 50}" text-anchor="middle" font-size="13" fill="{c["s"]}">{html.escape(sub)}</text>')
    for n, (a, b, label, kind) in enumerate(msgs):
        y = row0 + step * n
        col, mark, da = {"solid": (c["edge"], "a", ""), "dash": (c["dash"], "d", ' stroke-dasharray="6 5"'),
                         "lost": (c["bad"], "x", ' stroke-dasharray="3 4"')}[kind]
        tcol = c["bad"] if kind == "lost" else c["t"]
        if a == b:
            x = xs[a]
            o.append(f'<path d="M{x + 12},{y} h44 v22 h-40" fill="none" stroke="{col}" stroke-width="1.6"{da} marker-end="url(#{mark})"/>')
            right_room = w - (x + 64)
            anchor, tx = ("start", x + 64) if right_room > len(label) * 7.2 else ("end", x - 20)
            o.append(f'<text x="{tx}" y="{y + 16}" text-anchor="{anchor}" font-size="13.5" fill="{tcol}">{html.escape(label)}</text>')
        else:
            x1, x2 = xs[a], xs[b]
            d = 1 if x2 > x1 else -1
            if kind == "lost":
                xm = (x1 + x2) / 2
                o.append(f'<line x1="{x1 + 13 * d}" y1="{y}" x2="{xm}" y2="{y}" stroke="{col}" stroke-width="1.6"{da}/>')
                o.append(f'<path d="M{xm - 6},{y - 6} l12,12 M{xm + 6},{y - 6} l-12,12" stroke="{col}" stroke-width="2"/>')
            else:
                o.append(f'<line x1="{x1 + 13 * d}" y1="{y}" x2="{x2 - 4 * d}" y2="{y}" stroke="{col}" stroke-width="1.6"{da} marker-end="url(#{mark})"/>')
            if len(label) * 7.2 > abs(x2 - x1) - 40:
                o.append(f'<text x="{min(x1, x2) + 20}" y="{y - 9}" text-anchor="start" font-size="13.5" fill="{tcol}">{html.escape(label)}</text>')
            else:
                o.append(f'<text x="{(x1 + x2) / 2}" y="{y - 9}" text-anchor="middle" font-size="13.5" fill="{tcol}">{html.escape(label)}</text>')
        o.append(f'<circle cx="{xs[a]}" cy="{y}" r="11" fill="{c["lane"]}" stroke="{c["line"]}"/>')
        o.append(f'<text x="{xs[a]}" y="{y + 4}" text-anchor="middle" font-size="11" font-weight="700" fill="{c["s"]}">{n + 1}</text>')
    o.append('</svg>')
    return "\n".join(o)


for slug, (parts, msgs) in SCENARIOS.items():
    for theme, c in THEMES.items():
        open(rf"docs/example-{slug}-{theme}.svg", "w", encoding="utf-8", newline="").write(svg(parts, msgs, c))
print("ok")
