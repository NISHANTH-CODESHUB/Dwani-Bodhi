# Dhwani-Bodhi — User Guide

This guide covers starting the system and using it day to day as a **teacher**. There are only two kinds
of users: teachers (who sign up themselves) and the children they check. There is no admin.
The app's screens are in Hindi. Hindi labels are shown in quotes with an English meaning next to them.
The same steps are also in the app under **मेनू → उपयोग गाइड** (Menu → User guide).

---

## 1. Start the system (local / demo)

You need three terminals. Run these from the repository root.

```bash
# Terminal 1 — API
cd services/api
.venv/Scripts/activate            # macOS/Linux: source .venv/bin/activate
python -m app.demo                # first time only: creates a demo classroom
uvicorn app.main:app --reload     # http://localhost:8000

# Terminal 2 — background worker (scoring, learner model, Action Cards)
cd services/api
.venv/Scripts/activate
python -m app.jobs.worker --scheduler

# Terminal 3 — web app
cd apps/web
npm install                       # first time only
npm run dev                       # open http://localhost:5173
```

To try voice items without a microphone, start the web app with `npm run dev -- --mode demo`.
A text box will appear so you can type what the child "said".

**Create your account.** On the login screen tap **New teacher? Create an account** and fill in your name,
mobile number, a PIN, your school, your class name and the grades taught in it (optionally, the children's
home-language area, so regional pronunciations are not counted as reading mistakes). The account is
**ready at once — nobody has to approve it** — and you go straight to your class. Add more classes later
under **☰ → Change class → Add a class**; tap the ✎ next to a class to rename it or change its grades.

**Who sees what.** Each teacher sees only their own classes. Children's names stay on the teacher's phone;
the server knows a child only by an ID and a register number.

**Forgotten PIN.** There is no admin to reset it, so whoever runs the server resets it:
`python -m app.cli reset-pin --phone 98xxxxxxxx` (prints a new PIN once and signs the account out everywhere).

**Demo data (developers).** `python -m app.demo` seeds a demo class with a teacher account whose random phone
number and PIN are printed once and saved to the git-ignored `data/demo-credentials.txt`
(`--reset-credentials` issues new ones). `python -m app.cli reset-data --yes` deletes every account, class,
child and answer for a fresh start.

**PIN rules (all accounts).** A PIN must have 6–12 digits and must be hard to guess: no repeats like
`111111` or `121212`, no sequences like `123456`, no common PINs, and no digits taken from your mobile
number. If an account still has an old, weak PIN, the app asks for a new one straight after login and
can't be used until it is changed. You can also change your PIN any time under **☰ → पिन बदलें**.
Changing it signs you out on every other phone.

---

## 2. Finding your way around

The layout changes with screen size:

| Screen | Navigation |
|---|---|
| **Phone** | A **bottom tab bar** with the 5 daily screens: होम (Home) · कक्षा (Class) · स्लेट (Slate) · कार्ड (Card) · समीक्षा (Review). Tap **☰** (top left) to open the full menu. |
| **Tablet / laptop** (≥ 1024 px) | A permanent **dark sidebar** on the left with every screen, grouped as *रोज़ का काम* (Daily work), *कक्षा और योजना* (Class & plan) and *सहायता* (Help). |

These are on every screen:

- **Class switcher.** The box at the top of the sidebar/menu shows the current class. Tap it to change class.
- **Sync status.** The pill shows *सब सिंक* (all synced), *N बाकी* (N items waiting) or *ऑफ़लाइन* (offline). Tap it to sync now.
- **Back arrow (←).** Sub-screens like a child's profile or the add-child form show a back arrow instead of the menu button.
- **Review badge.** The orange number on *समीक्षा* shows how many items are waiting for your judgement.
- **Log out.** At the bottom of the sidebar/menu, next to your name.

---

## 3. Teacher workflow

### Step 1 — Sign in and choose a class
New teachers create an account first (see section 1). After that, enter your mobile number and PIN and tap **Log in**.
If you teach more than one class, pick one. You can change it later from the class switcher.

### Step 2 — Add children and record consent
1. Open **कक्षा** (Class) and tap **+ जोड़ें** (Add).
2. Fill in:
   - the name. It is stored **only on this phone** and never sent to the server.
   - the grade.
   - the **ID card number** (0–99). The app suggests the next free number.
3. Under **माता-पिता की सहमति** (Parental consent), choose **सहमति मिली** (Consent given) only once you have the parents' signed consent.
   **A child cannot be assessed without consent.**
4. Tap **सहेजें** (Save).

The filter chips on the Class screen make clean-up quick. They show children who need consent (*सहमति बाकी*), have no name on this phone (*नाम नहीं*) or are not synced yet (*सिंक बाकी*).
The search box finds a child by name or ID number.

### Step 3 — Hand out ID cards
Open **ID कार्ड छापें** (Print ID cards) from the sidebar or menu, or use the card icon on the Class screen.
Tap **प्रिंट** (Print) and give each child the card with their number. Slate photos identify children by this card.

### Step 4 — Daily check (2–3 minutes per child)
1. **होम** (Home) lists *आज किसकी जाँच* (who to check today). The system chooses these children for you.
2. Tap the big **▶ … के साथ शुरू करें** (Start with …) button, or **▶** next to any child.
3. Hand the phone to the child. Cheenu the sparrow guides them through reading and tapping tasks.
   Children earn stars for effort. They never see right or wrong.
4. To leave early, **press and hold the lock icon (top corner) for 2 seconds**.
5. The progress ring on Home fills as children finish.

### Step 5 — Slate maths
1. Open **स्लेट** (Slate). The day's problems are shown on a blackboard; copy them onto the real board.
2. Children solve them on their slates and place their ID card at the top of the slate.
3. Tap **फ़ोटो लें** (Take photo). Fit 4–6 slates in one photo, as the frame guide shows.
   Photos are queued and uploaded when there is network.

### Step 6 — Review what the system is unsure about
Open **समीक्षा** (Review). For each item:
- **Reading:** tap **सुनें** (Listen), then **सही पढ़ा** (Read correctly) or **गलत पढ़ा** (Read wrongly).
  You can also pick the error type.
- **Slate:** look at the cropped slate, type the answer the child wrote, and tap **पक्का करें** (Confirm).

Each answer you give makes the system more accurate.

The most useful items come first, and the purple note on an item says why it matters (for example, "इससे एक उलझन पक्की या खारिज होगी", "this will confirm or clear a confusion"). Five a day is enough: after five, the app tells you to stop, and you don't need to empty the list. If you aren't sure, or there is no recording to listen to, tap **पक्का नहीं — छोड़ें** (Not sure, skip). Never guess.

On the Action Card, a green chip (**पक्का**) means the confusion was seen at least twice and checked. An orange chip (**शायद · जाँच जारी**) means it was seen but is still being checked.

### Step 7 — Monday Action Card
Open **कार्ड** (Card). Children are grouped by the specific difficulty they share.
Each group comes with:
- the evidence (*क्यों?* — why), with example words or sums,
- a 10-minute activity with step-by-step instructions, the time needed and the materials,
- **सुनें** (Listen), which reads the plan aloud.

After running an activity, tap **इस हफ़्ते किया** (Done this week).
Next week the system re-checks these children and shows whether the difficulty was resolved.

### Step 8 — A child's profile
Tap any child's name to open their profile. It shows:
- **स्तर** (Level): where the child is on the reading and maths ladders. A dashed ring means the level is not certain yet.
- **उलझन** (Confusions): specific mistakes, with evidence. Only confirmed patterns appear as certain.
- **कौशल** (Skills): each skill as *आता है* (knows) / *सीख रहा है* (learning) / *अभी नहीं* (not yet).
- **पढ़ने की रफ़्तार** (Reading speed): words per minute over time, against the grade goal.
- **समझाइए** (Explain): a short plain-language summary of the child's progress and the next step.

---

## 4. Student register numbers and activity

- **Register numbers.** Every student gets a permanent register number such as `STU-2026-00012`, generated by
  the server the first time the phone syncs the new student. It appears in the roster (you can search by it),
  on the student's profile and in every dashboard. Until the first sync it shows "Assigned after the next sync".
- **Teacher: Menu → Student activity.** Class totals, sessions per day for the last 14 days, and a table of
  every student (register number, sessions, accuracy, reading and maths level, last active). Tap a student for
  the profile, which now ends with the full **activity timeline**: every kiosk session and slate check, with
  each answer and its result.

## 5. Working offline
- Everything works without internet: the roster, daily checks, slate photos and the last downloaded card.
- Recordings and photos wait in the phone's storage and upload automatically when there is a network.
- If you log out while items are still waiting, the app warns you. Waiting items are kept and sent at the next login.

## 6. Privacy in one paragraph
Children's names stay on the teacher's phone. Audio is deleted right after scoring (or, when the teacher
reviews recordings, after the 7-day review window).
Claude (the AI) only sees cropped slates and de-identified data. Only the class teacher can see a class.
Consent is enforced at sync: the server rejects data for children without consent.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| "जानकारी नहीं मिली" (information not found) at login during development | The API is not running on port 8000. Start Terminal 1. |
| Home says *पहली बार इस्तेमाल के लिए इंटरनेट से सिंक करें* (sync over the internet before first use) | Connect to the internet and tap the sync pill. |
| ▶ is missing next to a child | Consent has not been recorded. Open the child and choose *सहमति मिली*. |
| "माइक की अनुमति नहीं मिली" (microphone permission denied) | Allow microphone access for the site in Chrome settings. |
| No Action Card yet | Assess a few children and sync. The card is built from their results. |
| "Cannot reach the server" at login | The API is not running (locally: start Terminal 1) or the phone is offline. |
| A child added today is missing from *Who to check today* | Sync once (tap the sync pill): the list is rebuilt when the class roster changes. |
