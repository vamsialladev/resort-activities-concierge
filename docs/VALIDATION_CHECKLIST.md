# Validation checklist (needs the owner)

- [ ] Deploy on Streamlit Community Cloud (steps in the README, Deploy) with `ANTHROPIC_API_KEY`, `DATABASE_URL`
      and `STAFF_PASSWORD` in Secrets. Set a monthly spend limit in the Anthropic Console first.
- [ ] On the live app: the schedule loads (first visit may show "Waking up the database..."), the family question
      gets real times and a kids-club citation, "Yes, please request the kids club for our two kids" creates a
      PENDING request.
- [ ] Sign in to Staff on the live app yourself, approve that request, and see the update in the guest chat.
- [ ] Print a room QR code from Staff → Room QR codes and scan it with a phone: it opens the right property and room.
- [ ] Type every input in `docs/VIDEO_SCRIPT.md` on the live app before recording.
- [ ] Add the live URL to `streamlit-keep-awake` (`apps.txt`).
- [ ] Ask two people who haven't seen it to try it and write down the first thing they type (held-out questions
      written by someone other than me).
