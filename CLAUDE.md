# health-cloud

## Read the design context first

`docs/CONTEXT.md` holds the agreed architecture, the stack, the build order with
progress checkboxes, and an index of a design doc per area. **Read it before
proposing or implementing anything.**

The detail lives in the linked docs, not in `CONTEXT.md`: `stack.md`,
`ingestion.md`, `orchestration.md`, `data-model.md`, `auth.md`,
`observability.md`, `testing.md`, `operations.md`, `decisions.md`. **Follow the
links and read the ones covering the area you are about to touch** — they hold
the reasoning behind each decision and the alternatives already rejected. The
design was settled through a grilling session; do not relitigate decisions
recorded there unless the user reopens them.

The build order in `CONTEXT.md` is the source of truth for what is done and what
is next. Tick a checkbox only once the step is actually complete.

## Confirm before each step

Ask for explicit confirmation before implementing each build step. An agreed
plan is not authorisation for the whole plan — stop after each step and ask
before starting the next.


## Grill before implementing

Before writing code for any implementation task, invoke the
`mattpocock-skills:grilling` skill and work through it to completion. Do not
write or edit source files until the user has confirmed a shared understanding.

This applies to features, refactors, new modules, schema or API changes, and any
task whose shape is not already fully pinned down by the request.

It does not apply to: answering questions, reading or explaining code, running
commands, or a change the user has already specified exactly (an explicit
one-line edit, a rename, a typo fix).

If the user says to skip it — "just do it", "no questions", "skip the grilling" —
skip it and implement directly.
