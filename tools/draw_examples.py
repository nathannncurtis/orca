import html

THEMES = {
    "light": dict(card="#ffffff", cards="#d1d9e0", sig="#f6f8fa", line="#d1d9e0", acc="#ddf4ff", accs="#0969da",
                  t="#1f2328", s="#59636e", bad="#cf222e", badbg="#ffebe9", h="#1f2328"),
    "dark": dict(card="#0d1117", cards="#3d444d", sig="#151b23", line="#3d444d", acc="#121d2f", accs="#4493f8",
                 t="#f0f6fc", s="#9198a1", bad="#f85149", badbg="#25171c", h="#f0f6fc"),
}

# (from, to, what happened, kind): kind is call, signal (a hint or delivery) or lost (never arrives / fails)
SCENARIOS = [
    ("The ordinary path", "judged: state reached (a create would be confirmed by its ID)", [
        ("User", "", "records the intent and shows it at once", "call"),
        ("User", "Write queue", "enqueues it; the lease is checked", "call"),
        ("Write queue", "Vendor API", "sends it; the lease is checked again", "call"),
        ("Vendor API", "Source database", "updates order 42", "call"),
        ("Source database", "Change capture", "statement completed", "signal"),
        ("Change capture", "Store", "hint: orders, key 42", "signal"),
        ("Store", "Source database", "re-reads order 42, committed only", "call"),
        ("Store", "", "rebuilds order 42's read models as version 1001", "call"),
        ("Store", "User", "version 1001, delivered whole", "signal"),
    ]),
    ("Capture loses the event", "resolved by observation, never resent", [
        ("Write queue", "Vendor API", "sends the intent", "call"),
        ("Vendor API", "Source database", "updates order 42", "call"),
        ("Source database", "Change capture", "statement completed: the event is lost", "lost"),
        ("User", "", "timeout: nothing has come back", "call"),
        ("Store", "Source database", "re-reads order 42 for the intent", "call"),
        ("Store", "User", "changed: version 1001", "signal"),
    ]),
    ("The change rolls back", "values never arrived: undetermined, shown to the user", [
        ("Vendor API", "Source database", "updates order 42", "call"),
        ("Source database", "Change capture", "statement completed", "signal"),
        ("Source database", "", "the transaction rolls back", "lost"),
        ("Change capture", "Store", "hint: orders, key 42", "signal"),
        ("Store", "Source database", "re-reads order 42, committed only", "call"),
        ("Store", "", "unchanged: no new version", "call"),
    ]),
    ("The sending worker crashes", "judged on what the store shows; the API is never called twice", [
        ("Worker A", "Vendor API", "sends the intent", "call"),
        ("Vendor API", "Source database", "updates order 42", "call"),
        ("Worker A", "", "crashes before recording the send", "lost"),
        ("Worker B", "", "claims the intent: outcome uncertain", "call"),
        ("Worker B", "Store", "checks order 42 first", "call"),
        ("Store", "Worker B", "already holds the change", "signal"),
    ]),
    ("Someone edits order 42 in the vendor's app", "same values: state reached; different: undetermined", [
        ("Write queue", "Vendor API", "sends status = shipped", "call"),
        ("Vendor app user", "Source database", "edits order 42 directly", "call"),
        ("Vendor API", "Source database", "updates order 42", "call"),
        ("Change capture", "Store", "both changes captured and re-read", "signal"),
        ("Store", "User", "the latest version of order 42", "signal"),
    ]),
    ("A client was offline overnight", "resumed in order, or resynced; never a partial version", [
        ("Client", "", "comes back, last saw version 1001", "call"),
        ("Client", "Store", "resume after version 1001", "call"),
        ("Store", "Client", "outbox still holds it: 1002 onward, whole versions, in order", "signal"),
        ("Store", "Client", "or, too old: resync the read models instead of replaying", "signal"),
    ]),
]

W = 820
X0 = 34           # timeline x
CX = 64           # card left
CW = W - CX - 20  # card width
CH, GAP = 58, 10


def svg(c):
    o, y = [], 20
    for si, (title, outcome, steps) in enumerate(SCENARIOS):
        o.append(f'<text x="20" y="{y + 22}" font-size="19" font-weight="700" fill="{c["h"]}">{si + 1}. {html.escape(title)}</text>')
        y += 42
        top = y
        for n, (src, dst, what, kind) in enumerate(steps):
            fill, stroke, dash = c["card"], c["cards"], ""
            if kind == "signal":
                fill, dash = c["sig"], ' stroke-dasharray="6 4"'
            if kind == "lost":
                fill, stroke = c["badbg"], c["bad"]
            o.append(f'<rect x="{CX}" y="{y}" width="{CW}" height="{CH}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.3"{dash}/>')
            tag = f"{src} → {dst}" if dst else src
            o.append(f'<text x="{CX + 16}" y="{y + 22}" font-size="12" font-weight="650" letter-spacing=".03em" fill="{c["bad"] if kind == "lost" else c["s"]}">{html.escape(tag.upper())}</text>')
            o.append(f'<text x="{CX + 16}" y="{y + 44}" font-size="16" fill="{c["t"]}">{html.escape(what)}</text>')
            o.append(f'<circle cx="{X0}" cy="{y + CH / 2}" r="12" fill="{c["card"]}" stroke="{c["bad"] if kind == "lost" else c["line"]}" stroke-width="1.5"/>')
            o.append(f'<text x="{X0}" y="{y + CH / 2 + 4}" text-anchor="middle" font-size="11.5" font-weight="700" fill="{c["s"]}">{n + 1}</text>')
            y += CH + GAP
        o.insert(len(o) - len(steps) * 5, f'<line x1="{X0}" y1="{top + CH / 2}" x2="{X0}" y2="{y - GAP - CH / 2}" stroke="{c["line"]}" stroke-width="2"/>')
        o.append(f'<rect x="{CX}" y="{y}" width="{CW}" height="40" rx="9" fill="{c["acc"]}" stroke="{c["accs"]}" stroke-width="1.3"/>')
        o.append(f'<text x="{CX + 16}" y="{y + 26}" font-size="15" font-weight="650" fill="{c["t"]}">{html.escape(outcome)}</text>')
        y += 40 + 44
    h = y - 24
    head = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" font-family="system-ui, -apple-system, \'Segoe UI\', Roboto, sans-serif">'
    return "\n".join([head] + o + ["</svg>"])


for theme, c in THEMES.items():
    open(f"docs/orca-examples-{theme}.svg", "w", encoding="utf-8", newline="").write(svg(c))
print("ok")
