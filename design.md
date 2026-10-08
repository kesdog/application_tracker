# Front-end design choices

## Design direction

The interface should feel like a calm, practical workspace. Prioritize readable information, fast scanning, and clear next actions. Use restrained decoration so application lists remain easy to work through.

Light and dark themes should have separate visual identities while keeping the same layout, control placement, and meaning of status colors.

## Layout and spacing

Use a sidebar for navigation and a slim header for the current page, navigation collapse control, and theme switch. Keep these controls in predictable positions so users can change the workspace appearance without interrupting their work.

Center page content within a maximum width of 1280 px. Use 32 px side padding on desktop, with smaller padding on narrow screens. Group related content into bordered panels with generous internal spacing; avoid placing a border around every individual value.

Use modest rounded corners: approximately 8 px for ordinary panels and 14 px for the creation wizard. The wizard has a narrower, 960 px maximum width to keep fields and instructions comfortable to scan.

## Typography

Use the system sans-serif stack, including Segoe UI on Windows. Keep body and control text around 13–14 px, page headings around 28 px, and wizard screen headings around 22 px.

Establish hierarchy with size, weight, and spacing before adding color. Supporting text uses a muted color with sufficient contrast; it should never become faint decoration. Short uppercase eyebrow labels help orient the user without competing with the main heading.

## Theme identities

| Visual role | Light: Paper | Dark: Midnight |
| --- | --- | --- |
| Character | Warm paper with forest-green navigation | Midnight navy with lavender actions and cyan links |
| Page background | `#f7f6f2` | `#0c1222` |
| Panels and fields | `#fffefb` | `#17213a` |
| Secondary surfaces | `#eeeee7` | `#25324d` |
| Main text | `#24352f` | `#f0f3ff` |
| Supporting text | `#526257` | `#b9c5df` |
| Primary action | `#1c5b53` | `#c3b2ff` |
| Links | `#1b625b` | `#8fe3dd` |

**Paper** pairs warm, almost-white panels with a filled forest-green sidebar and white navigation text. Borders are quiet and shadows are minimal. This creates a light, familiar workspace without relying on a stark white background.

**Midnight** separates the navy page background from lighter blue panels. Lavender identifies primary actions and active navigation, while cyan distinguishes links. Soft shadows give panels depth without brightening the entire screen.

The theme switch shows a sun or moon alongside the current theme name. Switching themes preserves the current page and unfinished form entries. Remember each theme's customized colors independently so switching does not erase the user's visual preferences.

## Navigation design

Pair each navigation label with a recognizable icon. Active destinations use both a background highlight and an edge indicator so selection does not depend on text color alone.

The expanded desktop sidebar is 238 px wide. Collapsing it produces a 76 px icon rail, giving more room to the main content. Keep every destination accessible in the collapsed state, with hover titles and accessible names. The expand/collapse control remains in the header.

On narrow windows, navigation appears above the content and can fold away completely. Preserve an obvious way to reopen it. Keep navigation transitions brief and respect reduced-motion preferences.

## Information density and emphasis

Use compact table rows, aligned headings, and consistent spacing to support comparison between applications. Allow optional columns and row-density choices. Place secondary information below the main value in smaller, readable text.

Use colored badges with explicit labels for statuses and outcomes. Keep meanings consistent across themes: blue for submitted or upcoming items, purple for interviews, green for successful outcomes, red for unsuccessful or overdue items, amber for near-term urgency, and neutral tones for inactive states.

Apply subtle row tints and edge accents for urgency rather than filling entire rows with saturated color. Keep the next action easy to find. Empty states should use a short explanation and a relevant action, without large decorative illustrations.

## Form and wizard interactions

Divide application creation into four short screens: Role, Posting, Contact & extras, and Review. This reduces the amount of information presented at once and gives users a clear sense of progress.

Show required fields first. Place less-used fields behind checkboxes or expandable sections. Keep optional sections visually separate from the main task, and preserve their entries when users move between screens.

Use a three-way segmented control for remote policy so all choices can be compared immediately. Use clear Email and Phone choices for contact method, with the relevant field visible and labeled. Present the optional deadline with a date picker and a plain-language choice of what the date means.

Offer autocomplete for short text and explicit previous-value choices for dates, numbers, and longer notes. Suggestions should support free entry rather than force users to select an existing value.

Place validation messages beside the affected field. Explain the correction in plain language and keep invalid entries available for editing. Back preserves the draft; Review provides edit links and a clearly labeled final save action. Keep the primary action in a consistent position at the end of each screen.

## Readability and accessibility

Target at least 4.5:1 contrast for normal text and 3:1 for large text. Include supporting text, placeholders, links, status text, and tinted rows in this requirement. Solid badges and selected controls use whichever black or white text provides stronger contrast against their fill.

Apply the theme consistently to fields, menus, calendars, dialogs, table headings, buttons, and validation messages. Disabled controls retain readable text while clearly communicating that they are unavailable.

Provide visible keyboard focus in both themes, including inside the sidebar. Labels remain available to assistive technology when their visible text is hidden in compact layouts. Pair color with text, icons, or shape, and provide a skip link to the main content.

## Responsive presentation

At widths of 760 px and below, move navigation above the workspace, reduce outer padding, and allow the header controls to wrap. Stack form fields and detail groups when horizontal space becomes limited. Wide tables may scroll horizontally rather than compressing their text into unreadable columns.

On very narrow screens, the theme's sun or moon can replace its visible name while the switch retains an accessible label. Preserve comfortable control spacing and avoid horizontal overflow in forms and panels.
