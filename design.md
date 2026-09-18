# Application Tracker — V1 Design Notes

This document intentionally stays simple until the functional implementation is stable and a frontend component library is chosen.

## Product design goal

The interface should feel like a practical replacement for an Excel application-tracking workbook.

Priorities:
1. information density
2. fast scanning
3. clear next actions
4. minimal navigation
5. predictable colors and icons

Avoid decorative UI that makes large application lists harder to read.

## Main navigation

Keep V1 to six primary destinations:

```text
Dashboard
Applications
Interviews
Tasks
Settings
```

`Application Focus` is opened from Applications and does not need to be a permanent navigation item.

## Dashboard

The dashboard is operational, not analytical.

Show:
- active applications
- follow-ups due/overdue
- tasks due/overdue
- upcoming interviews
- recent activity

Do not add charts in V1 unless they directly help with pending work.

## Applications table

This is the primary screen.

Suggested columns:

```text
Date Applied
Company
Position
Location
Contract
Status
Outcome
Next Action
Source
```

Requirements:
- searchable
- filterable
- sortable where useful
- compact rows
- source reachable in one or two clicks
- clear `Export current view` action

Filters:
- status/outcome
- company
- title
- location
- contract type
- source
- remote policy
- application date range
- document filename
- free text

## Application Focus

Suggested order:

```text
Header
- company
- job title
- status
- outcome
- date applied
- source

Next action / upcoming date

Job details

Timeline

Interviews

Tasks

Follow-ups

Notes

Documents
```

The most urgent pending date should be visually obvious near the top.

## Timeline

Use a vertical chronological timeline.

Each event should contain:
- icon
- event label
- short summary
- timestamp
- actor where useful

Example:

```text
● Interview scheduled       18 Sep 14:10
● Follow-up #1 sent         15 Sep 09:30
● Application submitted     07 Sep 11:02
```

## Semantic colors

Exact colors will be selected later, but meanings should remain consistent.

Suggested mapping:

```text
SUBMITTED       neutral / blue
INTERVIEW       purple
SUCCESSFUL      green
UNSUCCESSFUL    red
WITHDRAWN       grey
JOB_CANCELLED   orange
GHOSTED         muted grey
OVERDUE         red emphasis
DUE SOON        amber/orange emphasis
```

Do not use color as the only indicator; pair it with text and/or icons.

## Forms

Keep forms compact.

Application creation should show required fields first:
- job title
- company
- date applied
- job URL or email reference

Optional fields can appear under an expandable `More details` section.

This keeps manual entry fast while still supporting richer agent-created records.

## Empty states

Empty states should be functional.

Examples:

```text
No applications yet.
[Add application]

No tasks due.

No interviews scheduled.
```

Avoid large illustration-heavy empty states.

## Agent-generated changes

Agent changes should look like normal application changes but remain traceable.

Where relevant, show a small actor indicator such as:

```text
Human
Agent
System
```

Do not visually separate agent-managed applications from human-managed applications.

## Responsive behavior

Desktop is the V1 priority.

For narrow windows:
- table may horizontally scroll
- filters may collapse into a drawer/panel
- focus view sections should stack vertically

A dedicated mobile UI is not required for V1.

## Component library

Not selected yet.

Selection criteria later:
- strong Vue 3 support
- accessible components
- compact data tables
- filters/forms/dialogs
- low styling overhead
- easy theming
- no dependency on a heavy design system unless justified

Until then, use minimal CSS and avoid building a custom design system.
