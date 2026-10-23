---
name: migrate-machine
description: Walk the user through moving the BKK StreetSmart servers (production :8000, test :8001, ENVIRO :5050, Cloudflare Tunnel) to a new computer. Use when the user says they are switching, replacing or moving to a new machine, e.g. "จะเปลี่ยนเครื่อง", "ย้ายเครื่อง", "เครื่องใหม่มาแล้ว", "move the server to a new PC".
---

# Move the servers to a new machine

The runbook is `docs/MIGRATE_MACHINE.md`. Read it in full first; it is the source of truth for every step.

## How to run it

1. Ask where the user is: planning, new machine ready, data copied, or ready to switch. Start from that section.
2. Before step 4 of the runbook, collect the new machine's facts: GPU and VRAM (`nvidia-smi`), free disk,
   drive letters, Windows user name, and whether the project can live at `E:\new_ccty_bangkok`.
   Use them to pick the YOLO option in section 5.1 and to tell the user which paths to change.
3. Go one section at a time. Run the read-only checks yourself. Explain each step in plain Thai: what it does
   and why.
4. Confirm with the user before each of these, every time:
   - stopping production, ENVIRO or the cloudflared service on the old machine (the public site goes down),
   - any `robocopy` onto a folder that already holds data,
   - disabling or registering scheduled tasks or services,
   - turning off Smart App Control (it cannot be turned back on without reinstalling Windows).
5. Never let cloudflared run on both machines at once: the tunnel would split visitors between them.
6. Test on :8001 before production, as the runbook says.
7. When done, walk the checklist at the end of the runbook with the user, then update the memories tied to
   the old machine (live server location, GPU, Smart App Control, load capacity, local models).
8. If a step in the runbook turned out wrong or missing, fix `docs/MIGRATE_MACHINE.md` too.
