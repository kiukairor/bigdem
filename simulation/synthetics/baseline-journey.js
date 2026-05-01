/**
 * PULSE — Baseline browser journey
 *
 * Simulates a normal user session:
 *   1. Load the feed page
 *   2. Wait for events to render
 *   3. Click a category filter
 *   4. Open an event detail modal
 *   5. Close the modal
 *
 * NR signals generated (via SPA agent on pulse-shell):
 *   - PageView + PageViewTiming (load time)
 *   - AjaxRequest to /api/event-svc/events
 *   - BrowserInteraction for category filter click
 *   - BrowserInteraction for modal open/close
 *
 * Attach to private location pointing at pulse.test:30443
 * Recommended cadence: every 1 minute
 */

const assert = require('assert');
const BASE_URL = 'https://pulse.test:30443';

(async function pulseBaselineJourney() {

  // 1. Load the feed
  await $browser.get(BASE_URL);
  await $browser.waitForAndFindElement(
    $driver.By.css('[class*="grid"]'),
    10000
  );

  // 2. Wait for at least one event card to appear
  const cards = await $browser.findElements(
    $driver.By.css('[class*="card"], [class*="Card"]')
  );
  assert.ok(cards.length > 0, `Expected event cards, found ${cards.length}`);

  // 3. Click a category filter — 'MUSIC' tab
  const musicBtn = await $browser.waitForAndFindElement(
    $driver.By.xpath("//button[contains(., 'MUSIC')]"),
    5000
  );
  await musicBtn.click();
  await $browser.sleep(1000);

  // 4. Click 'All' to reset filter
  const allBtn = await $browser.waitForAndFindElement(
    $driver.By.xpath("//button[contains(., 'ALL') or contains(., '✦')]"),
    5000
  );
  await allBtn.click();
  await $browser.sleep(500);

  // 5. Open first event card detail (click on the card body, not the save button)
  const firstCard = await $browser.waitForAndFindElement(
    $driver.By.css('[class*="card"], [class*="Card"]'),
    5000
  );
  await firstCard.click();
  await $browser.sleep(1000);

  // 6. Confirm modal opened
  const modal = await $browser.findElements(
    $driver.By.css('[class*="modal"], [class*="Modal"]')
  );
  assert.ok(modal.length > 0, 'Event detail modal did not open');

  // 7. Close modal
  const closeBtn = await $browser.waitForAndFindElement(
    $driver.By.css('[class*="close"], [class*="Close"]'),
    3000
  );
  await closeBtn.click();
  await $browser.sleep(500);

})();
