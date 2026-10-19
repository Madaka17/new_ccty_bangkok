# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Everyday travellers in Bangkok and the surrounding provinces, mostly on a phone. They open the site
before leaving home or while on the way, and give it a few seconds. Their job: decide whether to go
now, and which way, given traffic, rain, flooding, dust and incidents.

## Product Purpose

BKK StreetSmart puts the live state of the city on one site in plain Thai: where traffic is jammed,
where it is flooding, how the air is, and what is happening on the roads. Success is a visitor who
opens the site and knows within seconds whether it is fine to go out now ("ตอนนี้ออกไปได้ไหม"),
then can tap into detail only when they want it.

## Positioning

It combines sources no single agency shows together (574 BMA cameras with on-server AI vehicle
counts, iTIC and DOH cameras, water, rain, dams, air, Longdo traffic, Traffy reports) and answers
in one plain-Thai verdict. Figures are computed from the numbers first; the AI only explains them
and never invents figures.

## Operating Context

- Phone first, often outdoors or in a vehicle, short visits; desktop users open the map, cameras
  and long detail views.
- Pages refresh on their own every 1-10 minutes; no reload needed.
- Heavy use spikes during floods, heavy rain and large incidents.
- Served publicly at https://bkksmartstreet.com through Cloudflare; the earthquake page is a
  separate app framed at `/enviro/`.

## Capabilities and Constraints

- React 18 + Vite + Tailwind 4 SPA in `web/`, hash routing, pages lazy-loaded; the home page
  (`dashboard`) is in the first download.
- Pages: home (ภาพรวม), map (แผนที่), alerts (ประกาศเตือน), floods (น้ำท่วม), earthquakes
  (แผ่นดินไหว), accident spots (จุดเสี่ยงอุบัติเหตุ), live cameras (ดูกล้องสด), camera AI
  (กล้อง AI), report a flood (แจ้งน้ำท่วม), ask AI (ถาม AI), visitor stats (สถิติผู้ใช้); PM2.5
  (ฝุ่น PM2.5) and my district (เขตของฉัน) are reached from home only.
- When a source is down the site says so and never passes old data off as live; an answer with
  no data is never shown as "fine".
- Down cameras are hidden, not removed, and come back when they recover.
- Strict CSP: no inline scripts. Light/dark follows the device by default, with a manual toggle.
- Current redesign scope: home page and navigation (sidebar, phone top bar, bottom bar) first;
  other pages follow one at a time.

## Brand Commitments

- Name: BKK StreetSmart.
- Every page in short, plain Thai with Thai menu names; codes, units and method notes live in
  detail views, not on the main surfaces.

## Evidence on Hand

Live data only, from the agencies listed in README.md. No testimonials, press or partnerships
exist; none may be invented.

## Product Principles

1. Answer "can I go out now?" first; everything else is one tap deeper.
2. Honest over reassuring: missing or stale data is said plainly, never shown as normal.
3. Plain Thai a non-technical reader understands at a glance.
4. Fast on a phone on a weak connection: the first screen loads before maps, video and AI pages.

## Accessibility & Inclusion

Thai glyphs run small, so type sizes are one step above defaults; touch targets at least 44px;
reduced-motion respected.
