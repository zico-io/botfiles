# Direct Linear tools in T3

Use this adapter when `issues__file` is unavailable. It calls authenticated
Linear tools; it does not implement a separate API client. Discover the actual
tool names before composing a call. When Linear is reached through a toolbox
`use` integration, pass the full evidenced draft, routing decisions and requested
actions to that integration; its tool calls use the same authenticated adapter.
If no authenticated Linear connection is available, stop before filing and
identify the missing connection.

1. Read `.mex/context/linear-teams.md` from the skills source repo, not the
   current project. Resolve the skill's own directory (following symlinks);
   in the source checkout the map is two levels above it. A packaged copy may
   omit the map. If it cannot be read, disclose that routing is proceeding
   without it, then list live teams and resolve ownership from the affected
   surface using the routing constraints below. Ask before filing when ownership
   is ambiguous or no permitted owner can be established. Live team membership
   alone does not make a team a valid destination.
2. List that team's labels and workflow states, and search open issues. Read a
   likely duplicate before deciding that it represents the same finding.
3. Prepare a compact issue with Initial ask, Context, Repro (when evidenced),
   Expected/Actual and observable acceptance criteria. Preserve safe source
   links and tenant context; do not manufacture a source permalink from a local
   transcript. Unknown evidence stays explicitly unknown.
4. Create in the owning team's Triage state, matching fleet intake. If Triage
   does not exist, ask which intake state the team uses. Derive one existing
   type label (Bug, Feature or Chore); report an unavailable label rather than
   creating new taxonomy. Feature requests map to Feature.
5. Derive priority from observed impact using the runtime policy below, then
   call the Linear issue-save tool once. Set assignee, project or cycle only
   when requested. Do not change an existing issue's labels without reading and
   merging its current set.
6. Report the issue's returned identifier and URL. Evidence upload and customer
   needs handled by `issues__file` are not automatically available here. Use
   available authenticated attachment tools only when authorized and report
   anything that did not transfer.

## Routing constraints

These apply with or without the team map:

- Never route intake to `Platform` (`PLT`), `Squeezers` (`COR`), `Product`
  (`PRD`), or `DevOps` (`IAC`). Platform/shared-code fixes belong to the domain
  whose feature broke; Squeezers is historical, Product is an umbrella, and
  DevOps deploy work is filed directly by its owner outside this intake path.
- Route by the affected surface, not the reporter's team or the location of
  shared implementation code. For example, a checkout bug fixed in a shared
  package belongs to Commerce, never Platform or Product.
- `Fleet` (`FLT`) owns `Bask-Health/bots`, its internal agents and their shared
  packages. Route that repo's engineering work there.
- Before saving, verify the chosen live team owns the surface and is not one
  of the four excluded teams. Include the missing-map disclosure in the result
  when fallback routing was used; do not silently treat a failed map read as success.

## Priority adapter

These are the ordered rules in `@repo/issues/src/prepare.ts` (`mapPriority`):

| First matching impact | Linear priority |
| --- | --- |
| PHI exposed across a security boundary | Urgent (1) |
| All users or a PHI path, with no workaround | Urgent (1) |
| Security/tenant isolation exposure | High (2) |
| Multiple accounts, with no workaround | High (2) |
| Money path, with no workaround | High (2) |
| No workaround, or single-tenant impact | Medium (3) |
| Limited impact with a workaround | Low (4) |

For a staging campaign, skip the money rule, cap Urgent at High unless PHI or
confirmed security exposure supports it, and cap feature requests at Medium.
Do not claim the fleet's assessment, estimate or ledger ran during direct MCP
filing. Those remain in `@repo/issues`, and should be reused rather than
reimplemented when a terminal runtime adapter is added.
