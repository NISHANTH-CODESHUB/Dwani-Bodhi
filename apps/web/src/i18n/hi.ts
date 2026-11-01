/** All UI text (English). Keep sentences short and plain. (Export name `hi` kept for compatibility.) */
import { ApiError } from '../lib/api';

export const hi = {
  appName: 'Dhwani-Bodhi',
  loading: 'Loading…',
  save: 'Save',
  cancel: 'Cancel',
  back: 'Back',
  delete: 'Delete',
  open: 'Open',
  start: 'Start',
  retry: 'Try again',
  yes: 'Yes',
  no: 'No',
  done: 'Done',
  close: 'Close',

  // login
  loginTitle: 'Teacher login',
  phone: 'Mobile number',
  pin: 'PIN',
  login: 'Log in',
  logout: 'Log out',
  logoutConfirm: "Log out? Children's names and recordings will stay on this phone.",
  logoutPending: (n: number) =>
    `${n} items have not reached the server yet. They will be sent at your next login. Log out anyway?`,
  chooseClass: 'Choose a class',
  noClassrooms: 'You have no class yet. Add your first class below.',
  changeClass: 'Change class',

  // sync
  online: 'Online',
  offline: 'Offline',
  queued: (n: number) => `${n} pending`,
  syncNow: 'Sync now',
  syncing: 'Syncing…',
  lastSync: 'Last sync',
  never: 'Never',
  syncFailed: 'Sync failed — it will retry automatically when the network is back.',
  syncOk: 'Sync complete ✔',
  rejectedItems: (n: number) => `${n} items were not accepted by the server (e.g. no consent)`,

  // home
  greeting: (name: string) => `Hello, ${name}`,
  actionCard: "This week's card",
  todayCheck: "Today's checks",
  todayNone: 'No child needs a check today.',
  todayStale: (day: string) => `This list is from ${day} — please sync`,
  todaySlate: "Today's slate questions",
  slateScan: 'Slate scan',
  unsure: 'Not sure',
  listen: 'Listen',
  classList: 'Class',
  view: 'View',
  doneToday: 'Done ✔',
  needsConsent: 'Consent pending',
  firstSyncNeeded: 'Sync with the internet before first use.',
  reasons: {
    never_assessed: 'First check',
    routine: 'Routine check',
    uncertain: 'Not enough data',
    due: 'Due for a check',
    recheck: 'Re-check',
  } as Record<string, string>,

  // roster
  rosterTitle: 'Children in class',
  addChild: 'Add child',
  editChild: 'Child details',
  childName: "Child's name",
  nameNote: 'The name stays only on this phone and is never sent to the server.',
  grade: 'Grade',
  gradeN: (g: number) => `Grade ${g}`,
  slot: 'ID card number',
  slotHint: "0 to 99 — the number printed on the child's ID card",
  slotTaken: 'This ID card number already belongs to another child.',
  slotClash: 'On the server this card number is assigned to another child — change the number.',
  gender: 'Gender (optional)',
  genders: { f: 'Girl', m: 'Boy', x: 'Prefer not to say' } as Record<string, string>,
  consent: 'Parental consent',
  consentText:
    "I have told the child's parents/guardian that this app will record the child reading aloud to help with learning. The recording is deleted after scoring and the child's name never leaves the phone. The parents have given written consent (signature).",
  consentStates: { pending: 'Pending', granted: 'Consent given', withdrawn: 'Consent withdrawn' } as Record<string, string>,
  consentRequired: 'A child cannot be assessed without parental consent.',
  deleteChildConfirm: "All of this child's data will be deleted from both the phone and the server. Are you sure?",
  notSynced: 'Not yet sent to server',
  noChildren: 'No children added yet.',
  nameMissing: 'Name not on this phone — enter the name',
  idCards: 'Print ID cards',
  idCardsTitle: 'ID card list',
  idCardsHint:
    'Give each child the ID card with their number. When photographing slates, place the card on top of the slate. Print the cards from "Print ID cards" in the menu.',
  profile: 'Profile',
  check: 'Check',

  // kiosk
  kioskStart: 'Start',
  kioskExitHold: 'Teacher: press and hold for 2 seconds to exit',
  kioskListening: 'Listening…',
  kioskDoneBtn: '✔ Done',
  kioskListenAgain: 'Listen again',
  kioskThanks: 'Well done!',
  kioskBack: 'Back to teacher',
  kioskNoPlan: "This child's check plan is not on the phone. Sync when you have internet.",
  kioskNoContent: 'The content (questions) is not on the phone. Sync with the internet first.',
  micDenied: 'Microphone permission was denied. Allow the microphone in Chrome settings.',
  micUnsupported: 'Recording is not supported on this phone/browser.',
  simulateLabel: 'Demo: what did the child say?',
  simulateSend: 'Send',
  simulateSilent: 'Stayed silent',
  saveError: 'Could not save on the phone — check the storage space.',

  // slate
  slateTitle: 'Slate scan',
  slateWrite: 'Write these questions on the board:',
  slateHowTo: "Children solve on their slates. Place each child's ID card on top of their slate. Fit 4–5 slates in one photo.",
  slateTake: 'Take photo',
  slatePhotos: 'Photos taken',
  slateNoProblems: "Today's questions are not on the phone. Please sync.",
  slateProcessing: 'Preparing photo…',
  slateSaved: 'Photo saved ✔',
  slateUploaded: 'Sent',
  slatePending: 'Not sent yet',
  slateDeleteConfirm: 'Delete this photo?',
  slateImageError: 'Could not open the photo. Please take it again.',

  // card
  cardTitle: "This week's card",
  cardWeek: (w: string) => `Week ${w}`,
  cardNone: 'No card yet. A card will be created after a few children are checked and synced.',
  cardRegenerate: 'Make a new card',
  cardListen: 'Listen',
  cardStop: 'Stop',
  cardExamples: 'Examples',
  cardChildren: (n: number) => `${n} ${n === 1 ? 'child' : 'children'}`,
  cardMinutes: (n: number) => `${n} min`,
  cardMaterials: 'Materials',
  cardRecheck: 'Next week we will re-check these same children',
  cardCachedAt: (t: string) => `Saved: ${t}`,
  domains: { literacy: 'Reading', numeracy: 'Maths' } as Record<string, string>,
  materials: {
    chalk: 'Chalk',
    slate: 'Slate',
    blackboard: 'Board',
    pebbles: 'Pebbles',
    matchsticks: 'Matchsticks',
    rubber_bands: 'Rubber bands',
    paper_cards: 'Paper cards',
    body_movement: 'Games/actions',
    bottle_caps: 'Bottle caps',
    string: 'String',
  } as Record<string, string>,

  // profile
  level: 'Level',
  levelSure: 'Confirmed',
  levelUnsure: 'Not yet certain',
  skillsTitle: 'Skills',
  checking: 'Checking',
  notYet: 'No data yet',
  confusions: 'Confusions',
  noConfusions: 'No confirmed confusion found.',
  wcpm: 'Reading speed (words/min)',
  explain: 'Explain',
  explaining: 'Explaining…',
  explainWait: 'Writing an explanation from the evidence. This takes about 10 seconds.',
  explainAgain: 'Explain again',
  nextStep: 'Next step',
  lastAssessed: 'Last checked',
  offlineCached: 'Offline — showing saved data',

  // unsure
  unsureTitle: 'Not sure — you decide',
  unsureEmpty: 'Nothing to confirm right now.',
  unsureHelp: 'Listen and tell us whether the child read correctly. This makes the system better.',
  play: 'Listen',
  correctRead: 'Read correctly',
  wrongRead: 'Read wrongly',
  errorType: 'What kind of mistake? (optional)',
  slateAnswer: 'Answer written on slate',
  confirm: 'Confirm',
  mediaGone: 'The recording was deleted for privacy.',
  confirmed: 'Thank you ✔',
  target: 'Word',
  heard: 'System heard',
  rules: {
    MLEN: 'Short/long matra (ि/ी, ु/ू)',
    ASP: 'Aspirated sound (क/ख)',
    VIS: 'Look-alike letters (ब/व)',
    MDROP: 'Dropped matra',
    MSWAP: 'ए/ऐ, ओ/औ',
    NAS: 'Dropped bindi/chandrabindu',
    CONJ: 'Conjunct letters',
    OTHER: 'Something else',
  } as Record<string, string>,

  school: 'School',
  children: 'Children',
  suppressed: 'Few children (privacy)',
  topConfusions: 'Top confusions',
  literacyLevels: 'Reading — levels (%)',
  numeracyLevels: 'Maths — levels (%)',
  efficacy: 'Which activities worked',
  resolved: 'Resolved',
  improved: 'Improved',
  persists: 'Persists',
  noData: 'No data yet.',
  totals: (s: number, c: number) => `${s} schools · ${c} children`,
  tagline: "A true picture of every child's learning — a clear plan every Monday",
  loginPrivacy: "Children's names stay only on this phone. Voice recordings are deleted after scoring.",
  showPin: 'Show PIN',
  pinCurrent: 'Current PIN',
  pinNew: 'New PIN (6 to 12 digits)',
  pinAgain: 'New PIN again',
  pinRuleLength: 'At least 6 digits',
  pinRuleGuess: 'Hard to guess (not 123456, 111111, a birth date or mobile number)',
  pinMismatch: 'The two new PINs do not match.',
  pinSameAsOld: 'The new PIN must be different from the old one.',
  pinSave: 'Save new PIN',
  pinPrivacy: 'Do not share your PIN. Changing it logs you out of all other phones.',
  pinForcedTitle: 'Create a new PIN first',
  pinForcedSub: "Your old PIN is easy to guess. A new PIN is required to keep children's data safe.",
  pinPageTitle: 'Change PIN',
  pinChanged: 'New PIN saved. You have been logged out of all other phones.',
  hidePin: 'Hide PIN',
  // ---- v2 design: shell, dashboard, review, kiosk -------------------------------------------
  tabHome: 'Home',
  tabClass: 'Class',
  tabCard: 'Card',
  tabReview: 'Review',
  synced: 'All synced',
  syncOkShort: 'Synced ✓',
  syncFailShort: 'Sync failed',
  childrenN: (n: number) => `${n} ${n === 1 ? 'child' : 'children'}`,
  todayNoneShort: 'No checks due today',
  todayAllDone: "All of today's checks are done!",
  todayRemaining: (n: number) => `${n} ${n === 1 ? 'child' : 'children'} left to check today`,
  todayGreat: 'Great work — see you tomorrow.',
  heroAddKids: 'Add your children to begin',
  heroAddKidsNote: 'Add each child with their ID card number and parental consent.',
  heroConsent: 'Record parental consent',
  heroConsentNote: 'Children can be checked once a parent has given consent.',
  heroNoneNote: 'Every child is up to date. You can still check any child from the class list.',
  startWith: (name: string) => `Start with ${name}`,
  statConsented: 'Consent given',
  statReview: 'Review pending',
  statGroups: 'Groups this week',
  consentPendingN: (n: number) => `Consent pending for ${n} ${n === 1 ? 'child' : 'children'} — record it before checking`,
  todayListTitle: 'Who to check today',
  todayListHint: '~2–3 minutes per child',
  classPicture: 'Class picture',
  classPictureHint: 'Children by level',
  searchPlaceholder: 'Search name, ID card or register no.',
  addChildShort: 'Add',
  print: 'Print',
  rosterFilters: { all: 'All', consent: 'Consent pending', noname: 'No name', unsynced: 'Not synced' } as Record<string, string>,
  noMatches: 'No child found',
  addName: 'Enter name',
  cardHeroKicker: "Monday's plan",
  cardProgress: (d: number, t: number) => `${d}/${t} groups done`,
  cardByAI: 'Made by Claude',
  cardByTemplate: 'Made from set activities',
  lastWeekResult: (r: number, i: number, p: number) => `Last time: ${r} confusions resolved, ${i} improved, ${p} persist`,
  cardWhy: 'Why?',
  cardMarkDone: 'Done this week',
  cardDoneYes: 'Done',
  idCard: 'ID card',
  levelTitle: 'Level',
  levelHint: 'Where the child is on the TaRL ladder',
  confusionsHint: 'With evidence',
  wcpmGoal: (n: number) => `Goal: ${n} words/min`,
  reviewReason: (status: string, type: string, detail = '') =>
    type === 'slate'
      ? 'Read the answer written on the slate'
      : detail.includes('no acoustic model')
        ? 'Demo mode: the speech scoring model is off — listen and decide'
        : detail.includes('poor audio')
          ? 'Audio was unclear (noise/too quiet) — listen and decide'
          : status === 'NO_SPEECH'
            ? 'No voice heard — listen again'
            : status === 'OTHER'
              ? 'The child said something else'
              : 'The system is not sure',
  itemKind: {
    akshara: 'Letter reading',
    word: 'Word reading',
    nonword: 'Made-up word reading',
    passage: 'Story reading',
    repeat: 'Listen and repeat',
    slate: 'Slate maths',
  } as Record<string, string>,
  reviewCount: (n: number) => (n ? `${n} pending` : 'All done'),
  confirmedN: (n: number) => `${n} confirmed — thank you`,
  certSure: (n: number) => `Confirmed in ${n} ${n === 1 ? 'child' : 'children'}`,
  certMaybe: (n: number) => `Possible in ${n} ${n === 1 ? 'child' : 'children'} · still checking`,
  reviewNoMedia: 'No recording available. Answer only if you heard it yourself; otherwise skip.',
  reviewSkip: 'Not sure — skip',
  cellsSuppressed: '🔒 Levels with fewer than 5 children are hidden for privacy.',
  reviewBatch: (done: number, total: number) => `${done} of today's ${total}`,
  reviewBatchHelp: "Most important first. 5 a day is enough — you don't need to finish the whole list.",
  reviewBatchDone: "Great! That's enough for today.",
  reviewBatchDoneSub: (left: number) => (left ? `${left} more left — do them now if you like, or tomorrow.` : 'All done.'),
  reviewMore: 'Do 5 more',
  reviewWhy: {
    verifies_suspected: 'This will confirm or rule out a confusion',
    needs_reading: 'Nobody has read this slate yet',
    expiring: 'The recording will be deleted soon',
  } as Record<string, string>,
  kioskSpeakNow: 'Speak now!',
  kioskTapWhenDone: 'Finished? Tap here',
  kioskHello: (name: string) => (name ? `Hello ${name}!` : 'Hello, friend!'),
  kioskWellDone: (name: string) => (name ? `Well done ${name}! You were amazing.` : 'Well done! You were amazing.'),
  kioskStars: (n: number) => `${n} stars`,
  kioskExample: 'Example',
  // ---- v3 design: navigation shell + help ---------------------------------------------------
  appSub: "Teacher's companion",
  menu: 'Menu',
  closeMenu: 'Close menu',
  mainNav: 'Main navigation',
  tabSlate: 'Slate',
  navDaily: 'Daily work',
  navPlan: 'Class and plan',
  navSupport: 'Support',
  navHelp: 'User guide',
  navPin: 'Change PIN',
  roleTeacher: 'Teacher',
  currentClass: 'Selected class',
  viewProfile: 'View profile',
  helpTitle: 'User guide',
  helpIntro: "Dhwani-Bodhi gives a true picture of every child's reading and maths. Just a few minutes a day — follow these steps.",
  helpSteps: [
    { icon: 'school', title: '1. Choose a class', body: 'After opening the app, choose your class. You can change it later from "Change class" in the menu.' },
    { icon: 'users', title: '2. Add children and record consent', body: 'In "Class", tap "Add". Fill in the name, grade and ID card number. When parents give consent, choose "Consent given" — children cannot be checked without consent.' },
    { icon: 'idcard', title: '3. Hand out ID cards', body: 'The "ID card" screen shows each child\'s number. Print it and give that card to the child — children are identified by it in slate photos.' },
    { icon: 'home', title: "4. Today's checks", body: '"Home" lists today\'s children. Tap ▶ and hand the phone to the child. Cheenu the bird asks the child to read (2–3 minutes). To exit midway, hold the lock at the top for 2 seconds.' },
    { icon: 'camera', title: '5. Slate scan', body: "Write today's questions on the board. Children solve them on slates with their ID card on top. Fit 4–6 slates in one photo." },
    { icon: 'review', title: '6. Review', body: 'When the system is not sure, it asks you. Listen to the recording or look at the slate and tap "Correct" / "Wrong".' },
    { icon: 'clipboard', title: "7. Monday's card", body: 'Every week you get groups of children and 10-minute activities. After doing them, tap "Done this week". Next week you will see whether the activity worked.' },
    { icon: 'sync', title: '8. Sync', body: 'The app works without internet. It syncs automatically when the network is available. You can also tap the sync button at the top to sync right away.' },
  ] as { icon: string; title: string; body: string }[],
  loginWelcome: 'Welcome',
  loginSub: 'Log in with your mobile number and PIN',
  loginWrong: 'Wrong mobile number or PIN. Please check and try again.',
  loginOffline: 'Cannot reach the server. Check your internet connection and try again — you need to be online to log in the first time.',
  crashTitle: 'Something went wrong on this screen',
  crashSub: 'Your saved work and recordings are safe on this phone. Reload the app to continue.',
  crashReload: 'Reload app',
  kioskStorageError: 'This phone could not save the session (storage may be full). Free some space and try again.',
  openSub: 'Demo mode: no phone number or PIN needed',
  openAsTeacher: 'Open as teacher',
  loginFeatures: [
    "Every child's learning confusions — with evidence",
    'Set 10-minute activities every Monday',
    'Works even without internet',
  ],
  helpPrivacyTitle: 'Privacy',
  helpPrivacy: "Children's names stay only on this phone and are never sent to the server. Voice recordings are deleted after scoring (or after your review). Only you can see your class.",

  // sign-up + classes (teachers manage their own account and classes; no approval step)
  navActivity: 'Student activity',
  signupLink: 'New teacher? Create an account',
  signupTitle: 'Create your teacher account',
  signupSub: 'Your account is ready at once — no approval needed. Add your school and class now; you can add more classes later.',
  signupName: 'Your name',
  signupCreate: 'Create account and start',
  haveAccount: 'Already have an account? Log in',
  schoolName: 'School name',
  schoolHint: 'For example: GPS Rampur. Only you see it.',
  className: 'Class name',
  classHint: 'For example: Class 1-2 or Section A',
  grades: 'Grades in this class',
  gradesHint: 'Choose every grade taught together in this class.',
  region: "Children's home language area",
  regionHint: 'Regional pronunciations from this area are not counted as reading mistakes.',
  addClass: 'Add a class',
  addClassTitle: 'New class',
  addClassSave: 'Create class',
  editClass: 'Edit class',
  editClassSave: 'Save class',
  classSaved: 'Class saved.',
  kioskMinutes: 'Daily check time per class (minutes)',
  myClasses: 'My classes',
  pinForgotten: 'Forgot your PIN? Ask the person who runs your Dhwani-Bodhi server to reset it.',

  // shared activity vocabulary
  act: {
    registerNo: 'Register no.',
    registerPending: 'Assigned after the next sync',
    idCard: (n: number) => `ID card #${n}`,
    sessions: 'Sessions',
    sessions7d: 'Sessions (7 days)',
    answers: 'Answers',
    accuracy: 'Accuracy',
    correct: 'Correct',
    incorrect: 'Needs practice',
    toReview: 'To review',
    waiting: 'Being scored',
    lastActive: 'Last active',
    never: 'Not yet',
    level: 'Level',
    literacy: 'Reading',
    numeracy: 'Maths',
    confusions: 'Confirmed confusions',
    consent: 'Consent',
    consentLabel: { granted: 'Given', pending: 'Pending', withdrawn: 'Withdrawn' } as Record<string, string>,
    grade: 'Grade',
    class: 'Class',
    school: 'School',
    teacher: 'Teacher',
    timeline: 'Activity timeline',
    timelineEmpty: 'No activity yet. Sessions appear here after the phone syncs.',
    kioskSession: 'Kiosk session',
    slateCheck: 'Slate check',
    stopped: 'Stopped early',
    minutes: (s: number) => (s < 60 ? `${s} s` : `${Math.round(s / 60)} min`),
    outcome: { correct: 'Correct', incorrect: 'Needs practice', unsure: 'To review', pending: 'Being scored', error: 'Not scored' } as Record<string, string>,
    daily14: 'Sessions per day — last 14 days',
    daily30: 'Sessions per day — last 30 days',
    dailyTable: 'Show as table',
    dailyChart: 'Show as chart',
    day: 'Day',
    noData: 'No sessions in this period yet.',
    byDomain: 'Results by subject',
    showItems: (n: number) => `Show ${n} answers`,
    hideItems: 'Hide answers',
    studentsN: (n: number) => `${n} students`,
    searchReg: 'Search register no.',
    all: 'All',
    openProfile: 'Open full profile',
  },

  // teacher: class activity page
  classAct: {
    title: 'Student activity',
    sub: 'Every check your students did, and how they are doing',
    students: 'Students',
    active7d: 'Active this week',
    assessed: 'Assessed',
    sessions14d: 'Sessions (14 days)',
    accuracy: 'Class accuracy',
    toReview: 'Answers to review',
    table: 'All students',
    sortBy: 'Sort by',
    sort: { slot: 'ID card', active: 'Last active', accuracy: 'Accuracy', sessions: 'Sessions' } as Record<string, string>,
    offlineNote: 'Showing the last saved copy — connect to refresh.',
  },
};

/** English message for any thrown error (API, network, storage). */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.kind === 'network') return 'No internet connection. Keep working offline and try again later.';
    if (e.kind === 'timeout') return 'The network is very slow. Please try again in a little while.';
    switch (e.status) {
      case 400:
      case 422:
        return 'The information is not valid — please check it again.';
      case 401:
        return 'Wrong phone number or PIN, or your session has expired. Please log in again.';
      case 403:
        return 'You do not have permission for this.';
      case 404:
        return 'Not found.';
      case 409:
        return 'This conflicts with existing information (e.g. ID card number).';
      case 410:
        return 'This recording was deleted for privacy.';
      case 413:
        return 'The file is too large.';
      case 429:
        return 'Too many requests — please wait a little.';
      default:
        return e.status >= 500 ? 'Server problem. Please try again in a little while.' : 'Something went wrong.';
    }
  }
  if (e instanceof DOMException && e.name === 'QuotaExceededError') return 'The phone is low on storage. Remove old files.';
  return 'Something went wrong. Please try again.';
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return hi.never;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return hi.never;
  return d.toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export function formatDay(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

/** Local calendar date YYYY-MM-DD. */
export function localDay(d = new Date()): string {
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${dd}`;
}

export function opSymbol(op: string): string {
  return op === '-' ? '−' : op;
}
