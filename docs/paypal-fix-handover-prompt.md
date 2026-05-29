# Handover Prompt — Fix PayPal Support Page Issues

Paste everything below the line into a fresh agent session on the `paypal-bug-fix`
branch of the éist repo.

---

You are working in the éist radio Hugo site (`/home/john/eist`), on branch
`paypal-bug-fix`. The PayPal subscription page has been tested and three issues were
identified. The full investigation is in `docs/paypal-support-page-test-report.md` —
read it first. Your job is to fix all three issues on this branch.

## Context you need

- The live support page is `content/support.md`. The PayPal logic is an **inline
  `<script>`** at the top of that file (Hugo renders it because
  `hugo.toml` sets `[markup.goldmark.renderer] unsafe = true`).
- The whole page is wrapped in a single Turbo frame
  (`<turbo-frame id="main-content" data-turbo-action="advance">` in
  `layouts/_default/baseof.html`). Turbo is loaded globally; the page uses
  `turbo:load`, and on a direct visit `turbo:load` fires **twice**.
- There are five subscription plans, each with a `paypal-button-container-<PLAN_ID>`
  div, plus a one-time donation markdown link (leave that link as-is — it works).
- `assets/js/paypal.js` is dead, unreferenced, buggy code.

## Verifying your work (do this before and after)

Build and drive the page with a headless browser and the real PayPal SDK; confirm
all five buttons render with a live iframe and **zero** `zoid` /
`paypal_js_sdk_v5_unhandled_exception` console errors, across three scenarios:
(1) direct load of `/support/`, (2) home → click "support" nav link (Turbo nav),
(3) `/support/` → away → back. There is a working puppeteer harness pattern in the
test report; reproduce it (`hugo --baseURL http://localhost:PORT/ -d /tmp/build`,
serve `/tmp/build`, drive with `puppeteer-core` + `/usr/bin/chromium`). The
`/support/` page must work identically whether reached by direct load or Turbo nav.

## Fix 1 — Stop tearing down the SDK (primary bug)

In `content/support.md`, the script currently removes and re-injects the PayPal SDK
`<script>` on every `turbo:load`, which destroys already-rendered buttons (10–15
zoid errors per visit) and risks leaving a dead button.

Required behaviour:
- **Load the PayPal SDK at most once.** If a `script[src*="paypal.com/sdk/js"]`
  already exists, do **not** remove it and do **not** add another — just (re)render
  any empty button containers using the already-loaded global `paypal`.
- Only call `paypal.Buttons(...).render()` for containers that exist **and** are
  empty (keep the `childElementCount === 0` guard, and also null-check the container
  so a missing element never throws).
- Make it idempotent under `turbo:load` firing multiple times and under
  Turbo navigation away and back (no duplicate buttons, no teardown errors).

Suggested shape (adapt as needed):

```js
const PAYPAL_SDK_SRC = "https://www.paypal.com/sdk/js?client-id=...&vault=true&intent=subscription";

function renderPaypalButtons() {
  if (typeof paypal === "undefined") return;
  paypalPlans.forEach(plan => {
    const el = document.getElementById(plan.container);
    if (el && el.childElementCount === 0) {
      paypal.Buttons({ /* style */,
        createSubscription: (d, a) => a.subscription.create({ plan_id: plan.id }),
        onApprove: handleApprove,   // see Fix 3
      }).render(`#${plan.container}`);
    }
  });
}

function ensurePaypal() {
  // Only render if we're actually on the support page.
  if (!document.getElementById("paypal-button-container-...")) return;
  const existing = document.querySelector('script[src*="paypal.com/sdk/js"]');
  if (existing) { renderPaypalButtons(); return; }   // do NOT remove/re-add
  const s = document.createElement("script");
  s.src = PAYPAL_SDK_SRC;
  s.dataset.sdkIntegrationSource = "button-factory";
  s.onload = renderPaypalButtons;
  document.body.appendChild(s);
}

document.addEventListener("turbo:load", ensurePaypal);
```

Keep the existing client-id and the five plan IDs exactly as they are in the current
file. Preserve the existing button style block.

## Fix 2 — Replace the `alert()` onApprove with a real confirmation

Currently `onApprove: function (data, actions) { alert(data.subscriptionID); }` —
this shows the donor a raw subscription ID in a browser alert.

Replace it with an inline, dependency-free thank-you experience:
- Add a hidden thank-you element to `content/support.md`, e.g.
  `<div id="paypal-thankyou" hidden> ... warm thank-you copy ... </div>`, styled
  consistently with the page. Include a short, genuine message (e.g. thanking them
  for supporting independent radio and noting the subscription is now active).
- In `handleApprove(data)`: hide the subscription button grid + the surrounding
  subscription copy, reveal `#paypal-thankyou`, and scroll it into view. Do **not**
  surface the raw subscription ID to the user; if you want it for support purposes,
  log it to the console only.
- Keep it robust under Turbo: the thank-you element lives inside the turbo-frame, so
  navigating away and back resets it (which is fine).

Example:

```js
function handleApprove(data) {
  console.log("PayPal subscription created:", data.subscriptionID);
  document.querySelectorAll(".pp").forEach(el => { el.hidden = true; });
  const ty = document.getElementById("paypal-thankyou");
  if (ty) { ty.hidden = false; ty.scrollIntoView({ behavior: "smooth", block: "center" }); }
}
```

(Wire it as the `onApprove` for every plan's button.)

## Fix 3 — Delete dead code

Delete `assets/js/paypal.js` (unreferenced, buggy duplicate of the inline script).
Grep the repo first to confirm nothing references it
(`grep -rn "paypal.js\|renderPayPalButtons" --include=*.html --include=*.md --include=*.toml .`),
then remove it.

## Deliverables

- All three fixes applied on `paypal-bug-fix`.
- Headless verification showing five rendered buttons and **zero** zoid/SDK errors in
  all three navigation scenarios; the thank-you UX shown after a simulated approval
  (you can invoke `handleApprove({subscriptionID:'TEST'})` manually to verify the UI).
- A concise commit (do not push unless asked). Suggested message:
  `Fix PayPal SDK teardown, improve onApprove UX, remove dead paypal.js`.

Do not change the client-id, the plan IDs, or the one-time donation link.
