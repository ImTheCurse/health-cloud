# Skills

Part of the [health-cloud design context](CONTEXT.md). Which agent skills this
repo runs with, where each comes from, and when it applies.

A skill is a packaged set of instructions Claude Code loads when a task matches
its description. Project instructions in `CLAUDE.md` and the design docs take
precedence over any skill: where a skill's advice contradicts a recorded
decision (a fetching library, TypeScript, a test framework), the decision wins.

## Project skills

Checked in under `.claude/skills/<name>/`. Claude Code does not load
`.agents/skills/`, so nothing goes there.

| Skill | Source | Use it for |
| --- | --- | --- |
| `python-patterns` | `affaan-m/ECC` @ `bf70150eb2df` | Idiomatic Python, typing and PEP 8 in `server/` and `tests/` |
| `react` | `thongdn-it/react-agent-skills` @ `22b5ec4` | React 19 hooks, rendering and memoisation in `client/` |
| `vercel-react-best-practices` | `thongdn-it/react-agent-skills` @ `22b5ec4` | Re-render, data-fetching and bundle performance in `client/` |
| `vercel-composition-patterns` | `thongdn-it/react-agent-skills` @ `22b5ec4` | Component APIs: compound components, avoiding boolean-prop sprawl |
| `ui-design` | `thongdn-it/react-agent-skills` @ `22b5ec4` | Accessibility, layout, colour contrast and responsive CSS in `client/` |

The four `react-agent-skills` were copied verbatim from the repository and carry
its MIT `LICENSE`. They were picked from a collection of eighteen.

Parts of their advice do not apply here:

- `react` and `vercel-react-best-practices` cover Server Components and Next.js.
  The client is a Vite SPA, so those rules do not apply.
- `vercel-react-best-practices` recommends caching libraries such as SWR, but the
  client fetches through its own `request()` helper. See [Charting](charting.md).

**Skipped from the collection, and why:**

| Skill | Reason |
| --- | --- |
| `nextjs`, `nuqs` | Next.js only |
| `typescript` | The client is JavaScript |
| `tailwind`, `shadcn` | Neither is used; styles are hand-written CSS |
| `tanstack-query` | Data fetching uses no library |
| `zod`, `react-hook-form` | The dashboard has no forms |
| `vitest`, `playwright`, `msw` | No frontend tests yet, by choice. See [Testing](testing.md) |
| `tdd` | Duplicates the `mattpocock-skills` `tdd` skill |
| `feature-arch` | Folder-by-feature layout; not wanted for now |
| `web-design-guidelines` | Fetches its rules from a remote URL on every run and follows them, so whoever edits that URL steers the agent |

## Plugins

Enabled in `.claude/settings.json`, each bringing several skills or hooks.

| Plugin | What it brings |
| --- | --- |
| `mattpocock-skills` | `grilling` (required before implementation by `CLAUDE.md`), `tdd`, `diagnosing-bugs`, `prototype`, `research`, `domain-modeling`, `codebase-design`, `code-review`, `pr`, `wizard`, `writing-for-agents` |
| `superpowers` | Process skills: `brainstorming`, `writing-plans`, `executing-plans`, `systematic-debugging`, `test-driven-development`, `verification-before-completion`, `requesting-code-review`, `receiving-code-review`, `using-git-worktrees`, `finishing-a-development-branch` and others |
| `frontend-design` | `frontend-design`: visual direction for new UI |
| `code-review` | `code-review`: reviewing a pull request |
| `code-simplifier` | A sub-agent that tidies recently changed code |
| `security-guidance` | Hooks that flag risky patterns as code is edited; no skill to invoke |

Where two process skills overlap, the project's rule decides: the
`mattpocock-skills` `grilling` skill runs before implementation, not
`superpowers` `brainstorming`.

## Skills that come with Claude Code

Not configured by this repo, but relevant to it:

- `dataviz`: chart colour, marks and dashboard layout. Read it before writing
  chart code in `client/`, alongside [Charting](charting.md).
- `code-review`, `simplify`, `security-review`: built-in review commands.

## Adding a skill

1. Clone the source into a scratch directory and read every file before copying
   anything. Reject a skill that fetches instructions from a URL at run time.
2. Copy the skill directory verbatim into `.claude/skills/<name>/`, with the
   upstream licence, and diff it against the source. Do not use an installer.
3. Confirm the skill appears in Claude Code's loaded skill list, since a file on
   disk is not proof that it loads.
4. Add a row above, with the source pinned to a commit.
