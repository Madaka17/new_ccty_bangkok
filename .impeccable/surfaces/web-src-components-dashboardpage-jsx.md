---
version: 1
slug: "web-src-components-dashboardpage-jsx"
primary_target: "web/src/components/DashboardPage.jsx"
related_targets: ["web/src/components/Sidebar.jsx","web/src/components/BottomNav.jsx","web/src/App.jsx"]
---

# Home + navigation (BKK StreetSmart)

Scope: the home page (`dashboard`) and the shell: desktop sidebar, phone top bar, phone bottom bar. Other pages
inherit the new tokens and are redesigned later, one at a time. Visitor mode: Operate.

Audience and job: everyday travellers on a phone, a few seconds before or during a trip; they need
"ตอนนี้ออกไปได้ไหม" first, detail one tap deeper. Must keep: every existing answer, link, poll and honest
no-data / stale state; plain Thai; the details tabs below the fold. Roll-out: built and checked on the test
server (:8001, instances/test/dist) before production.

## Direction contract

THESIS: The city as a working console. One status panel answers "ตอนนี้ออกไปได้ไหม"; the six checks run under
it like the stages of a build. It refuses the category's mosaic of same-size tiles, glass, glow and gradients.

OWN-WORLD: Graphite ground #0d1117, panels #151a22 split by 1px seams #262c36, one elevation step #1b212b.
Text #e6edf3, muted #8b949e. Colour only for state: blue #79c0ff action and running, green #56d364 fine, amber
#e3b341 watch, red #f85149 act, purple #c678dd yours. Noto Sans Thai Looped, compact; JetBrains Mono for every
figure and time. Light theme keeps the grammar on #f6f8fa / #ffffff.

STORY: The visitor reads the verdict, scans six check rows, taps one for its page, or asks AI about a road.
The emergency call stands alone with space around it.

FIRST VIEWPORT: Phone 390: 56px graphite top bar (page title, theme). Status panel: state glyph + verdict 30px
with the dashed emergency button beside it, headline sentence, detail. Then the check panel: six rows (glyph,
question, answer, chevron), care rows first, ask-AI under them. Hairline bottom bar, five items. No floating
buttons on home. Desktop: 232px rail with seam; status panel with ask-AI input; the six checks as a pipeline.

FORM: Dark-first developer console (catalog world, adopted by the user from the declined row; not on the
grounded list). Signature: the six checks drawn as pipeline stages; glyph shape (check, ring, triangle, dashed
ring) carries state beside colour, joined by a seam that is solid up to each finished check. Motion: panels
expand along one axis only. seed:5067a770748f2881

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
