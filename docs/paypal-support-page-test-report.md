# PayPal Support Page — Test Report

**Date:** 2026-05-29
**Branch tested:** `main` (commit `7f7dd15`)
**Page:** `/support/` (`content/support.md`)
**Tested against:** local `hugo` build *and* the live site at https://eist.radio

## Summary

Subscribing **works** — all five subscription buttons render and the one-time
donation link is valid — but the support page's PayPal integration tears down and
rebuilds the PayPal SDK on every page settle, throwing 10–15 SDK errors per visit
and creating a real (if intermittent) risk of a dead/blank button. There is also a
poor post-subscription UX (`alert()`) and a piece of dead, buggy code
(`assets/js/paypal.js`).

## How it was tested

- Built the site with `hugo` and served the output over a local HTTP server.
- Drove it with headless Chrome (puppeteer-core + system Chromium), with the **real
  PayPal SDK loading** from `paypal.com`.
- Also drove the **live production site** at `https://eist.radio` the same way.
- Scenarios exercised:
  1. **Direct load** of `/support/`.
  2. **In-site Turbo navigation** — land on `/`, click the "support" nav link.
  3. **Revisit** — `/support/` → away → back to `/support/`.
- Instrumented the page to count `turbo:load` events, PayPal SDK `<script>`
  additions/removals, `zoid`/SDK errors, and the final rendered state (child count +
  presence of the PayPal iframe) of each of the five button containers.

## Results

### ✅ Working

- **All five subscription buttons render** (€25 / €20 / €15 / €10 / €5) in every
  scenario, on both the local `main` build and live eist.radio. Final state always
  had a live PayPal iframe in each container.
- **One-time donation link** (`https://www.paypal.com/ncp/payment/25VW6TA5ZNS6C`)
  returns HTTP 200 and resolves to a valid live PayPal payment page.

### ⚠️ Issue 1 — SDK is destroyed & rebuilt on every `turbo:load` (primary)

The inline script in `content/support.md` runs this on every `turbo:load`:

```js
let oldScript = document.querySelector('script[src*="paypal.com/sdk/js"]');
if (oldScript) oldScript.remove();   // destroys all already-rendered buttons
```

Removing the SDK `<script>` tears down PayPal's "zoid" button components.
Measured behaviour:

| Scenario | `turbo:load` fired | SDK added / removed | zoid errors |
|---|---|---|---|
| Direct `/support/` | **2** | 2 / 2 | **10** |
| Home → support (Turbo) | 3 (cumulative) | 1 / 0 | 0 |
| support → away → support | 4 (cumulative) | 7 / 6 | **15** |

`turbo:load` fires **twice on a plain direct load** (Turbo + turbo-frame behaviour),
so even a first visit builds the buttons, destroys them, and rebuilds them —
emitting `zoid destroyed all components` and `paypal_js_sdk_v5_unhandled_exception`
errors. These errors are present on the live site today.

Impact: buttons recovered (re-rendered) in every test, so users *can* subscribe.
But there is a genuine race window — between teardown and re-render the buttons are
dead, and the `childElementCount === 0` guard means a re-render can be skipped while
a stale child is still present, leaving a non-functional button. This matches the
profile of an intermittent "I clicked subscribe and nothing happened" report.

Root cause: removing/re-injecting the SDK is unnecessary. The
`childElementCount === 0` guard already prevents duplicate renders; the SDK should
be loaded once and left in place.

### ⚠️ Issue 2 — Poor post-subscription UX

`onApprove` does `alert(data.subscriptionID)`. After a successful subscription the
donor sees a raw browser alert containing only a subscription ID — no thank-you, no
confirmation, looks broken. Does not block subscribing.

### ⚠️ Issue 3 — Dead, buggy code

`assets/js/paypal.js` is **not referenced anywhere** and is buggy
(`"DOMCOntentLoded"` typo; it also never loads the SDK). Harmless because it is
unused, but it should be deleted so it is not mistaken for the live implementation
(the live implementation is the inline `<script>` in `content/support.md`).

## Environment notes

- Hugo `v0.137.1+extended`. `[markup.goldmark.renderer] unsafe = true` in
  `hugo.toml`, so the inline `<script>` in `content/support.md` is rendered as-is.
- All page content (header/main/footer) is wrapped in a single
  `<turbo-frame id="main-content" data-turbo-action="advance">` in
  `layouts/_default/baseof.html`; the button containers and inline script live
  inside that frame.
