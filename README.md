# ORCA: Operational store, Read models, Change capture, Anti-corruption layer

ORCA is an architectural pattern for building a fast, independent application platform on top of a system you do not
own and cannot change. It is not a stack: any language, database or message bus can implement it.

Draft. Not yet published.

## The problem

Many organizations run their core business on a vendor's system: a practice-management, ERP or line-of-business
product whose database you can read but whose schema, release cycle and API belong to someone else. Over the years
everything else grows around it:

- **Direct reads:** dozens of internal tools query the vendor's database directly, each with its own polling loop.
- **Private copies:** each tool keeps its own partial copy, drifting slightly differently.
- **Leaking quirks:** the vendor's model (packed flag bytes, coded columns that need lookups, one table doing several
  jobs) leaks into every one of them.
- **Slow, incomplete API:** it is too slow and too incomplete to build on, and changing it is not an option.

The usual answers do not fit:

- **Rebuild on the vendor's API:** it lacks the reads you need.
- **Replace the vendor:** out of scope.
- **Turn on the database's own change tracking:** that alters a schema you do not own.
- **Mirror the database:** you get speed, but every app still speaks the vendor's model.

ORCA is the shape that remains: own a translated, live copy for reads, and send every write back through the vendor.

## The four parts

### Change capture
A low-latency, best-effort signal of which records changed, taken from outside the vendor's schema. Examples are a
database trace session, a transaction-log reader, or network capture of the vendor's client traffic.

- **Hints, not facts.** A capture record says "look at this table, these keys". It never says what the new values
  are. It may arrive before the change commits, may describe a change that later rolls back, and may be missing
  entirely.
- **Resumable, with gaps marked.** The stream has a position. A consumer reconnects from its last position and is told
  explicitly when records may have been lost (a gap).

### Operational store
Your own full copy of the vendor's data, kept current.

- **First copy:** resumable and paced, in key order, so the vendor's system never feels it.
- **Re-read on every hint:** the touched rows are re-read from the source by primary key, with a read that only sees
  committed data. A rolled-back change re-reads as the original. The hint only decides where to look; the source
  decides what is true.
- **Reconciliation:** checksums compared by key range, re-copying only ranges that differ. It runs after every gap,
  as soon as each table's first copy finishes, and on a slow schedule. Reconciliation always wins over the copy and
  over the stream.
- **A raw layer:** the vendor's tables kept exactly as they are, so translations can be rebuilt without touching the
  vendor again.

### Anti-corruption layer
A translation library that turns the vendor's model into yours: decoding packed values, resolving codes, splitting
tables that do several jobs, and joining what always belongs together.

- **Source-agnostic:** it takes plain rows and returns your shapes, so it doesn't care whether the rows came from your
  store or straight from the vendor.
- **One copy of the vendor's quirks:** everything else in the platform only sees your model.

### Read models
Screen-shaped documents built by the translation layer from the raw layer, such as an order header, a notes log or a
list row.

- **Versioned in commit order.** Each change gets a version, and version order must equal commit order. A plain
  sequence is not enough, because sequence values are handed out before commit. A single counter row updated inside
  each shaping transaction serializes them.
- **Outbox.** Each shaping transaction also writes its changes to an outbox table: the durable record every delivery
  reads from.
- **Whole versions only.** One version can cover several read models. Delivery never splits a version, and a consumer
  applies a whole version and only then saves its position.

## Around the four parts

### Delivery
A fan-out layer (a pub/sub cache, a websocket service) carries committed versions from the outbox to everyone
listening. It is delivery only, never the record: anything it loses is recovered from the outbox by position.

### Clients
- **Local cache:** clients can keep their own embedded copy of the read models they need (for example open records plus
  a recent window), fed by the delivery layer and resumed by version.
- **Fallback:** when the platform is unavailable, a client may run the same translation library directly against the
  source. That fallback must be narrow (the one record on screen, rate-limited, clearly marked as live) so an outage of
  your platform never becomes a flood of reads on the vendor's.

### Writes
Nothing writes to the vendor's database directly. Every write goes through the vendor's own API.

- **Intents first.** A client records the user's intent in a durable local log, shows it at once, and can offer a short
  undo window.
- **One claimer per intent.** A queue (e.g. `FOR UPDATE SKIP LOCKED`) ensures each intent has one claimer, in order per
  record. That is not exactly-once delivery: a worker can send and then crash before recording it.
- **Never resend blind.** An uncertain outcome is resolved by observation, never by sending again.
- **Judged by what comes back.** A write is judged by what returns through change capture, with three outcomes:
  - **Confirmed:** tied to this operation. For a create, the API returns the new record's ID and that exact record
    arrives.
  - **State reached:** the record holds the values sent, after the intent was sent, but nothing proves this request
    caused it. Enough for plain "set this field" changes.
  - **Undetermined:** the evidence cannot tell. Never retried automatically; shown to the person.

  Anything with side effects (creating records, sending, billing) only counts when Confirmed.
- **Leases with fencing tokens coordinate your own writers.** They are checked when an intent is queued and again
  before it is sent. They cannot recall a request already in flight, and they mean nothing to people working directly
  in the vendor's application. Conflicts with those people are detected afterwards through capture, not prevented.
  The vendor's own record locks, if visible, are mirrored in as a warning.

## Guarantees and non-guarantees

| ORCA guarantees | ORCA does not guarantee |
|---|---|
| Every committed source change eventually appears in the store (reconciliation) | That every change is seen through capture |
| The store never keeps a rolled-back value past the next re-read or reconciliation | That reads are as fresh as the source at every instant |
| Version order equals commit order; no consumer skips a committed version | Exactly-once delivery of writes to the vendor |
| A write is only reported done with evidence, and side-effecting writes only when Confirmed | That a write's cause can always be proved (Undetermined exists) |
| The vendor's model never leaks past the translation layer | Coordination with people using the vendor's application directly |

## Failure cases

| Situation | What happens |
|---|---|
| Capture misses a change (trigger writes, unparsable statements) | Reconciliation finds the differing range and re-copies it |
| Capture reports a gap | The consumer requests reconciliation of everything the gap could cover |
| A change rolls back after its hint | The committed-only re-read returns the original values |
| The first copy races a change | Each table counts as correct only after its first reconciliation |
| A worker crashes after sending a write | The intent is resolved by observation; it is never resent blind |
| A client reconnects after its position has expired | Full resync of its read models, not a replay |
| The platform is down | Clients fall back narrowly to the source, visibly |
| The vendor changes its schema | The raw layer shows it; translations are rebuilt from the raw layer |

## When ORCA fits

**It fits when:**
- many tools depend on a system you do not control;
- reads vastly outnumber writes;
- the vendor's model is awkward;
- the vendor's API is incomplete;
- you cannot or will not alter the vendor's schema.

**It doesn't fit:**
- if you own the source (use its own change tracking and build read models directly);
- if a few direct queries are enough;
- if every write needs synchronous confirmation from the vendor in the user's path.

## Implementing it

**What one implementation used:**
- **Capture:** a SQL Server Extended Events session filtered to insert, update and delete, read by a small service
  next to the database.
- **Store and read models:** a Rust service with PostgreSQL holding the raw layer, the read models, the outbox, the
  write queue and the leases.
- **Delivery:** Redis for fan-out.
- **Clients:** LMDB caches.

**Any equivalent works:** log-based capture such as Debezium, another database, Kafka for delivery, or SQLite on
clients.
