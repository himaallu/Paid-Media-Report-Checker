// Opens the deployed app in a real headless browser so Streamlit Community Cloud
// counts it as a visit. If the app is asleep, it clicks the wake-up button and
// waits until the app has loaded. Exits non-zero if the app never loads, so a
// failure shows up as a red run in GitHub Actions.
//
//   node scripts/keep-awake.cjs [url]
const { chromium } = require("playwright");

const URL = process.argv[2] || process.env.APP_URL || "https://paid-media-report-checker.streamlit.app/";
const LOADED_TEXT = /This week at a glance|Paid Media Report Checker/;
const WAKE_BUTTON = /get this app back up/i;
const TIMEOUT_MS = 4 * 60 * 1000;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  let ok = false;
  let woke = false;
  try {
    await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 90_000 });
    const deadline = Date.now() + TIMEOUT_MS;
    while (Date.now() < deadline && !ok) {
      for (const frame of page.frames()) {
        const wake = frame.getByRole("button", { name: WAKE_BUTTON });
        if (!woke && (await wake.count().catch(() => 0))) {
          console.log("App is asleep: clicking the wake-up button");
          await wake.first().click();
          woke = true;
        }
        if (await frame.getByText(LOADED_TEXT).count().catch(() => 0)) {
          ok = true;
          break;
        }
      }
      if (!ok) await page.waitForTimeout(5_000);
    }
    if (ok) {
      console.log(`App loaded${woke ? " after waking it" : " (it was already awake)"}`);
      await page.waitForTimeout(20_000); // stay a moment so the visit registers
    } else {
      console.error(`App did not load within ${TIMEOUT_MS / 60000} minutes`);
      await page.screenshot({ path: "keep-awake-failure.png", fullPage: true });
    }
  } finally {
    await browser.close();
  }
  process.exit(ok ? 0 : 1);
})();
