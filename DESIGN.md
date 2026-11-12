---
name: BKK StreetSmart
description: The city as a working console. One status panel answers "can I go out now", six checks run under it like build stages.
colors:
  ground-dark: "#0f0f10"
  surface-dark: "#18181b"
  raised-dark: "#222226"
  seam-dark: "#2a2a2f"
  seam-strong-dark: "#3a3a40"
  ink-dark: "#f4f4f5"
  muted-dark: "#a1a1aa"
  action-dark: "#fb923c"
  action-fill-dark: "#f97316"
  on-action: "#0f0f10"
  ok-dark: "#56d364"
  watch-dark: "#facc15"
  act-dark: "#f85149"
  act-text-dark: "#ff7b72"
  none-dark: "#6e7681"
  yours-dark: "#c678dd"
  ground-light: "#f7f7f8"
  surface-light: "#ffffff"
  raised-light: "#f1f1f3"
  seam-light: "#e4e4e7"
  seam-strong-light: "#d4d4d8"
  ink-light: "#18181b"
  muted-light: "#52525b"
  action-light: "#c2410c"
  action-hover-light: "#ea580c"
  action-tint-light: "#fff1e6"
  ok-light: "#1a7f37"
  watch-ring-light: "#ca8a04"
  watch-text-light: "#854d0e"
  watch-fill-light: "#fef9c3"
  act-light: "#cf222e"
  act-text-light: "#b3141f"
  none-light: "#a1a1aa"
  yours-light: "#8250df"
typography:
  verdict:
    fontFamily: "Noto Sans Thai Looped, ui-sans-serif, system-ui, sans-serif"
    fontSize: "30px (36px from 640px)"
    fontWeight: 700
    lineHeight: 1.25
  headline:
    fontFamily: "Noto Sans Thai Looped, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.25rem (1.5rem from 640px)"
    fontWeight: 600
    lineHeight: 1.375
  page-title:
    fontFamily: "Noto Sans Thai Looped, ui-sans-serif, system-ui, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    lineHeight: "36px"
    letterSpacing: "-0.005em"
  answer:
    fontFamily: "Noto Sans Thai Looped, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.375
  body:
    fontFamily: "Noto Sans Thai Looped, ui-sans-serif, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  panel-label:
    fontFamily: "Noto Sans Thai Looped, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: "1.25rem"
    letterSpacing: "0.02em"
  figure:
    fontFamily: "JetBrains Mono, ui-monospace, Cascadia Mono, monospace"
    fontSize: "inherit"
    fontWeight: 500
    letterSpacing: "-0.01em"
    fontFeature: "tabular-nums"
rounded:
  control: "6px"
  md: "6px"
  panel: "12px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "20px"
  xl: "24px"
components:
  status-panel:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.ink-dark}"
    rounded: "{rounded.panel}"
    padding: "20px 24px"
  check-card:
    backgroundColor: "{colors.raised-dark}"
    textColor: "{colors.muted-dark}"
    rounded: "{rounded.md}"
    padding: "12px 14px"
  check-row:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.muted-dark}"
    padding: "10px 16px"
    height: "56px"
  button-primary:
    backgroundColor: "{colors.action-fill-dark}"
    textColor: "{colors.on-action}"
    rounded: "{rounded.md}"
    padding: "0 20px"
    height: "44px"
  button-emergency:
    backgroundColor: "transparent"
    textColor: "{colors.act-text-dark}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "44px"
  input-ask:
    backgroundColor: "{colors.ground-dark}"
    textColor: "{colors.ink-dark}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "44px"
  nav-row:
    textColor: "{colors.muted-dark}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "44px"
  nav-row-current:
    backgroundColor: "{colors.action-fill-dark}"
    textColor: "{colors.on-action}"
---

# Design System: BKK StreetSmart

## Overview

**Creative North Star: "The City Console"**

The site reads like a developer console that watches the city. One status panel states the verdict (the answer to "ตอนนี้ออกไปได้ไหม"), and six checks run under it as the stages of a pipeline. Dark is the first theme: a near-black zinc ground, panels split by 1px seams, one step of elevation. Light keeps the same grammar on a cool zinc white. There is no glass, no gradient on content, and no mosaic of equal tiles. The one glow is the soft orange halo on the selected menu row. The verdict is bigger than everything else on the screen.

Colour carries state and nothing else. Orange marks only action, the selected item and "you are here". Green, yellow and red mean fine, watch and act; grey means no data yet; purple means what belongs to the viewer (my district, my route). Blue is kept for water and other information data. Every state also has a shape, so colour is never the only sign. Figures and times are set in a monospaced face so columns line up.

This is a measured build: the home page and the app shell (sidebar, phone top bar, bottom bar) carry the system. Everything below the fold and every other page inherit only the tokens (see Don'ts and the drift line).

**Key Characteristics:**
- Dark-first near-black console with a full light twin; the theme follows the device and can be toggled.
- Flat: 1px seams and tonal steps, no shadows on panels.
- One verdict, six pipeline stages; the check rows with care needed come first on a phone.
- State is colour plus glyph shape plus a Thai word.
- One looped Thai face for all text, mono for figures only.

## Colors

A zinc neutral system (near-black and cool white) with a single action orange and four state colours; each theme has its own values, listed in the frontmatter with `-dark` / `-light` suffixes.

### Primary
- **Action Orange** (dark text/ring `action-dark`, button fill `action-fill-dark`; light `action-light`, hover `action-hover-light`): buttons, focus rings, the selected menu row, the current page's icon, the 2px tab rule, the "running" state. Also marks "you are here" (`--c-here`). Text on an orange fill is dark (`on-action`, #0f0f10), never white.
- **Water and info blue** (`--color-blue-*`): water levels, flood and other information data. It is not an action colour.

### Secondary
- **Yours Violet** (`yours-dark` / `yours-light`): only what belongs to the viewer, e.g. the "เขตของฉัน" button. Never decoration.

### State
- **Fine Green** (`ok-dark` / `ok-light`), **Watch Yellow** (`watch-dark` #facc15; light ring `watch-ring-light`, text `watch-text-light`, fill `watch-fill-light`), **Act Red** (`act-dark`, text `act-text-dark`; light `act-light`, text `act-text-light`), **No-data Grey** (`none-dark` / `none-light`). Each has ring, fill, text and tint roles, exposed to children as `--t-*` by a `tone-green|yellow|red|neutral` class set on the element.

### Neutral
- **Ground** (`ground-*`): page background. **Surface** (`surface-*`): panels. **Raised** (`raised-*`): the one elevation step (check cards, current nav row, hover). **Seam** (`seam-*`, strong variant): 1px borders and dividers. **Ink** and **Muted** (`ink-*`, `muted-*`): text; muted is the default for questions and labels, ink for the current item and the verdict sentence.

### Named Rules
**The State-Only Colour Rule.** Hue appears only to say fine, watch, act, no data, action, selected, or yours. A surface that needs emphasis uses a seam or the raised step, not a hue.

**The Dark Ink On Orange Rule.** Text on an orange fill is `on-action` (#0f0f10), never white.

**The Honest Grey Rule.** A check with no data is grey with a dashed ring and the words "รอข้อมูล"; it is never drawn green. The verdict says the data is not all in rather than "ปกติ".

## Typography

**Display / Body Font:** Noto Sans Thai Looped (with ui-sans-serif, system-ui). Weights 400, 500, 600, 700.
**Mono Font:** JetBrains Mono (with ui-monospace, Cascadia Mono). Weights 400, 500, 600.

**Character:** One compact looped Thai face for everything, so heads and body read the same way for any reader; the mono face is reserved for numbers and times, which gives the console its instrument feel.

### Hierarchy
- **Verdict** (700, 30px, 36px from 640px, 1.25): the one word answer beside its glyph.
- **Headline** (600, 20px, 24px from 640px, snug, max about 30em): the one plain sentence under the verdict.
- **Page title** (700, 26px, 36px line): the PageHeader h1 on inner pages.
- **Answer** (700, 18px phone care rows and pipeline cards, 17px calm phone rows): the check result in its tone text colour.
- **Body** (400-500, 15px, 1.6): details, nav labels, tabs (600).
- **Panel label** (600, 13px, 0.02em, muted, sentence case): the heading of a panel or nav group. It is a real heading, not a decoration above one.
- **Figure** (mono, tabular numerals, -0.01em): every count, time and measurement via `.num`.

Tailwind's size steps are raised one notch (xs 13px, sm 15px, base 17px) because Thai glyphs run small.

### Named Rules
**The Figures-In-Mono Rule.** Numbers and times use the mono face with tabular numerals; words never do.

## Layout

Desktop (from 1024px): a 232px sidebar rail split by a seam, a top bar (page title, page search from `TopBar.jsx` and `lib/pageSearch.js`, a live-cameras link, weather and the theme toggle), then the content column up to 1400px wide with 16px vertical gaps. The home page stacks the status panel (verdict, headline, detail, ask-AI input), then the six checks as a 3-column grid (6 across from 1280px) of cards joined by short seam lines, then the detail area as a 3fr/2fr grid. Phone: a 56px top bar (page title, theme), the status panel, then the six checks as one panel of rows (56px minimum, care rows first, ask-AI under them), and a five-item bottom bar with bottom padding for the safe area. Touch targets are 44px or more. Panel padding is 20-24px on wide screens and 16px on phones; gaps between panels are 16px.

## Elevation & Depth

Flat by default. Depth is one tonal step (surface to raised) plus 1px seams; panels carry no shadow. The only shadows left in the system are the hairline ring token (`0 0 0 1px` seam colour) and a soft drop on map popups and toasts. The selected menu row takes `--c-glow`, a soft orange halo under its orange fill; it is the only glow in the system. The live-source dot breathes a 5px ring in the fine colour; that is state, not glow.

### Named Rules
**The Seam Not Shadow Rule.** Separate panels with a 1px seam and, at most, the raised step. A panel that needs a shadow to be seen is placed wrong.

## Shapes

Small, quiet corners: panels 12px, controls and cards 6px, avatars/badges and scrollbar thumbs fully round. Borders are 1px. The signature silhouettes are the state glyphs, drawn in a 20px box: a ringed tick (fine), a ring half-filled on the right (watch), a filled warning triangle (act), a dashed ring (no data). A seam between two pipeline stages is solid when both have data and dashed while one waits.

## Components

### Buttons
- **Shape:** 6px corners, 44px tall on touch surfaces (the Button helper offers 40px md and 32px sm).
- **Primary:** action-fill background, dark text (`on-action`, #0f0f10), semibold, 20px side padding; hover steps to the darker action (`--c-primary-hover`). Dark theme fill is `#f97316`.
- **Secondary / Ghost:** seam border on surface, or transparent; hover raises to the raised step.
- **Emergency (inline):** transparent with a 1px dashed act-coloured border and act text, phone icon, 44px tall, sits beside the verdict; hover fills with the act tint. A destructive control is dashed so it is findable but never louder than the verdict.
- **Focus:** a 2px action outline with 2px offset on every focusable element.

### Cards / Containers
- **Panel:** surface background, 1px seam, 12px corners, no shadow.
- **Check card (wide):** raised background, 1px seam, 6px corners, 12px by 14px padding; hover borders in the tone's ring colour; contents are glyph, question (muted), answer (tone text, bold), tone word.
- **Check row (phone):** 56px minimum, glyph, question, right-aligned answer, chevron; hover raises.

### Inputs / Fields
- **Style:** 44px tall, ground background, strong seam border, 6px corners, muted placeholder.
- **Focus:** border turns action orange and a 2px action-tint ring appears.

### Navigation
- **Sidebar:** surface rail, 64px brand header, panel-label group headings, 44px rows with a 20px icon; the selected row is filled orange with dark text (`on-action`) and the one glow (`--c-glow`) (`aria-current`).
- **Bottom bar (phone):** five items on a hairline top seam; the current page is marked by a 2px action rule on that seam; "แจ้งน้ำท่วม" sits in the middle on a filled action square; the last item opens the menu drawer.
- **Tabs:** an underline row on a seam; the selected tab gets ink text and a 2px action rule that slides between tabs (spring); 44px tall, 15px semibold.

### State Glyph and Pipeline (signature)
Six checks, always the same order on wide screens, each led by its StateGlyph; on phones ranked care, then fine, then waiting. The seam fill animation draws solid joins from the left as the page opens.

### Motion
Panels expand along one axis only: a clip reveal downward (0.28s) for panels, sideways (0.26s) for the phone menu drawer, both on `cubic-bezier(0.16, 1, 0.3, 1)`; the pipeline seam scales in from the left (0.5s, staggered 70ms). Color transitions are 150ms. Reduced motion collapses all of it.

## Do's and Don'ts

### Do:
- **Do** put the verdict and its one sentence first on any new top-level screen, with the state glyph beside the word.
- **Do** pair every status colour with its glyph shape and a Thai word.
- **Do** set figures and times in the mono face with `.num`.
- **Do** build new surfaces from seams, the raised step and the `tone-*` classes; reach for the `--c-*` tokens before any Tailwind palette colour.
- **Do** keep touch targets at 44px or more and body text at 15px or more.
- **Do** use dark ink (`--c-on-primary`) on orange fills and reserve yellow for "watch".

### Don't:
- **Don't** use glass, glow outside the selected menu row, gradients on content, or soft drop shadows on panels.
- **Don't** put white text on an orange fill, or use orange for decoration.
- **Don't** colour a surface for decoration; hue means state, action or "yours".
- **Don't** draw a check with missing data as fine.
- **Don't** nest rounded cards inside cards on new work, or use saturated chart bars.
- **Don't** set text below 12px; new work stays at 13px or above.
- **Don't** make the emergency control louder than the verdict; it stays dashed and in the flow of the status panel.

## Known drift (recorded, not canonized)

The below-fold detail tabs on the home page and every other page still carry the pre-redesign grammar: nested rounded cards, saturated chart bars, and 9-11px text (the sidebar badge also uses 11px). They inherit only the tokens, through the slate remap and the Tailwind palette overrides in `index.css`. The floating round red emergency button (non-inline variant), the weather effects layer and the map popups also keep older shadow and ring treatments. Their redesign is planned for later rounds; none of these are rules for new surfaces.
