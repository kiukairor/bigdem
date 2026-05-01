/**
 * PULSE — Bug 5: BUG_TECH_SAVE trigger
 *
 * Simulates a user trying to save a Tech event.
 * The save crashes with a TypeError before the optimistic UI update fires —
 * the event never appears in the saved panel.
 *
 * NR signals generated:
 *   - JavaScriptError: "TypeError: Cannot read properties of undefined (reading 'tags')"
 *   - Source: FeedApp.tsx → handleSave
 *   - BrowserInteraction for the TECH filter click and the save attempt
 *   - AjaxRequest to /api/event-svc/events (feed load)
 *
 * This script intentionally does NOT assert that the save succeeds —
 * the point is to fire the error so NR Browser JS Errors shows a spike.
 *
 * Recommended cadence: every 1 minute (each run = one JS error in NR)
 */

const assert = require('assert');
const BASE_URL = 'https://pulse.test:30443';

(async function pulseTechSaveBug() {

  // 1. Load feed
  await $browser.get(BASE_URL);
  await $browser.waitForAndFindElement(
    $driver.By.css('[class*="grid"]'),
    10000
  );

  // 2. Click TECH category filter
  const techBtn = await $browser.waitForAndFindElement(
    $driver.By.xpath("//button[contains(., 'TECH')]"),
    5000
  );
  await techBtn.click();
  await $browser.sleep(1500);

  // 3. Find a tech event card and click its Save button
  //    The save button has a ☆ or ★ in its text
  const saveBtn = await $browser.waitForAndFindElement(
    $driver.By.xpath("//button[contains(., '☆') or contains(., 'SAVE')]"),
    5000
  );
  await saveBtn.click();

  // 4. Wait briefly — the TypeError fires asynchronously as an unhandled rejection
  await $browser.sleep(2000);

  // 5. Verify the button reverted (star icon back to ☆, not ★)
  //    If the event was actually saved the button would show ★ — the revert is the bug signal
  const btnText = await saveBtn.getText().catch(() => '');
  assert.ok(
    btnText.includes('☆') || btnText.includes('SAVE'),
    'Save button should have reverted — if it shows ★ the bug may have been fixed'
  );

})();
