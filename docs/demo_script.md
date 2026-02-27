# A2Apex Demo Video Script
**Duration:** 60 seconds  
**Style:** Fast-paced, modern SaaS demo with electronic background music

---

## Scene 1: Opening Hook (0-5s)

**SCREEN:** A2Apex logo animates in on dark background with cyan glow. Tagline fades in below.

**VISUAL:**
- Logo: ⚡ A2Apex
- Tagline: "Postman for AI Agents"
- Subtle particle/grid animation in background

**NARRATION:** *(None — music only, logo speaks for itself)*

**TRANSITION:** Logo scales down, UI fades in behind it

---

## Scene 2: The Problem (5-15s)

**SCREEN:** Abstract visualization of AI agents communicating, then showing confusion/errors

**VISUAL:**
- Quick cuts of agent icons connected by lines
- One connection shows ❌ error
- Text overlay: "A2A Protocol" with Google attribution

**NARRATION:**
> "AI agents need a standard way to communicate. Google's A2A protocol is that standard. But how do you know your agent implements it correctly?"

**TRANSITION:** Zoom into the A2Apex web interface

---

## Scene 3: Agent Card Validation (15-25s)

**SCREEN:** A2Apex web UI — Validate tab

**ACTION SEQUENCE:**
1. Show empty URL input field
2. Type: `https://your-agent.com` (cursor typing animation)
3. Click "Validate Card" button (show button highlight)
4. Show loading spinner briefly
5. Score animates from 0 → 100 with confetti/glow effect
6. Compliance badge appears: "✅ A2A Compliant"

**NARRATION:**
> "Paste your agent's URL. Hit validate. Get instant compliance scoring."

**TRANSITION:** Smooth scroll/tab switch to Live Tests

---

## Scene 4: Live Protocol Tests (25-40s)

**SCREEN:** A2Apex web UI — Live Tests tab

**ACTION SEQUENCE:**
1. Show test list with all items pending (gray)
2. Click "Run Live Tests" button
3. Tests execute one by one:
   - ✅ Agent Card Structure — passes (green checkmark animates)
   - ✅ Required Fields — passes
   - ✅ JSON-RPC Endpoint — passes
   - ✅ Message Send/Receive — passes
   - ✅ Task Lifecycle — passes
4. Final summary: "5/5 Tests Passed" with green glow
5. Brief hover over a test to show expandable details

**NARRATION:**
> "Run live protocol tests against your actual agent. Watch them pass in real-time. Every A2A requirement, verified."

**TRANSITION:** Tab switch to Debug Chat

---

## Scene 5: Debug Chat (40-50s)

**SCREEN:** A2Apex web UI — Debug Chat tab

**ACTION SEQUENCE:**
1. Show chat interface (split view: chat left, raw JSON right)
2. Type in chat: `What's the weather in Tokyo?`
3. Press Enter / click Send
4. Agent response appears in chat bubble
5. Raw JSON panel highlights showing the actual protocol messages
6. Quick scroll through JSON to show structure

**NARRATION:**
> "Debug in real-time. See exactly what your agent sends and receives. Every JSON payload, exposed."

**TRANSITION:** Split screen or quick cut to terminal

---

## Scene 6: CLI Power (50-55s)

**SCREEN:** Terminal / command line on dark background

**ACTION SEQUENCE:**
1. Terminal prompt appears
2. Type: `pip install a2apex`
3. Show quick installation (sped up)
4. Type: `a2apex test https://your-agent.com`
5. Show colorful CLI output with passing tests

**NARRATION:**
> "Or use the CLI. One command. Instant validation."

**TRANSITION:** Fade to CTA screen

---

## Scene 7: Call to Action (55-60s)

**SCREEN:** Landing page hero or dedicated CTA screen

**VISUAL:**
- A2Apex logo prominent
- URL: **a2apex.io** (large, glowing)
- "Start Free" or "Join the Waitlist" button
- Social proof if available (GitHub stars, user count)

**NARRATION:**
> "Try it free at a2apex.io"

**TEXT ON SCREEN:**
```
⚡ A2Apex
a2apex.io

Ship confident agents.
```

**TRANSITION:** Logo hold for 1 second, fade to black

---

## Production Notes

### Music
- Upbeat electronic/tech track
- Build energy through scenes 3-5
- Softer on CTA

### Pacing
- Scenes 3-5 are the meat — don't rush the UI interactions
- Let animations complete before cutting
- Total typing time should feel natural, not rushed

### Recording Tips
- Use 1920x1080 or higher
- Zoom browser to 125% for better visibility
- Pre-fill some fields if typing takes too long
- Consider screen recording tool with zoom/highlight effects

### Assets Needed
- [ ] A2Apex logo (SVG, animated if possible)
- [ ] Screenshots for fallback/B-roll
- [ ] Background music track (royalty-free)
- [ ] Sound effects: typing, success chime

---

## Screenshot Checklist

| Screenshot | Filename | Description |
|------------|----------|-------------|
| Hero/Empty | `01_hero.png` | Fresh load, no tests run |
| Validation Result | `02_validate.png` | After validating agent card, showing 100 score |
| Live Test Results | `03_live_test.png` | All tests passed with green checkmarks |
| Demo Mode | `04_demo.png` | Demo mode results display |
| Debug Chat | `05_chat.png` | Chat with message history and JSON panel |
