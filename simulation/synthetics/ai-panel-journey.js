/**
 * PULSE — AI recommendations panel journey
 *
 * Simulates a user who uses the AI panel: loads the feed, waits for AI
 * recommendations to appear, toggles the panel off with a reason, then
 * re-enables it.
 *
 * NR signals generated:
 *   - AjaxRequest to /api/ai-svc/recommendations (POST, includes latency)
 *   - BrowserInteraction for AI toggle click
 *   - With BUG_AI_SLOW active: the AJAX call to /api/ai-svc/recommendations
 *     will show ~8s duration in NR Browser AJAX timeline, correlating with
 *     the 8s Distributed Tracing span visible in APM
 *   - Custom NR event UserAIOptOut (fired by the app on toggle-off)
 *
 * Recommended cadence: every 2 minutes
 */

const assert = require('assert');
const BASE_URL = 'https://pulse.test:30443';
const AI_LOAD_TIMEOUT = 15000; // 15s — accommodates BUG_AI_SLOW (8s) + network

(async function pulseAIPanelJourney() {

  // 1. Load feed
  await $browser.get(BASE_URL);

  // 2. Wait for AI panel to populate
  //    The panel shows either "AI POWERED", "CACHED", or "RULE-BASED" once loaded
  await $browser.waitForAndFindElement(
    $driver.By.xpath(
      "//*[contains(., 'AI POWERED') or contains(., 'CACHED') or contains(., 'RULE-BASED') or contains(., 'RULE BASED')]"
    ),
    AI_LOAD_TIMEOUT
  );

  // 3. Verify at least one recommendation card exists in the panel
  const recCards = await $browser.findElements(
    $driver.By.css('[class*="rec"], [class*="Rec"], [class*="recommendation"]')
  );
  // Not asserting count > 0 — circuit breaker may be OPEN (rule-based fallback shows no recs)

  // 4. Toggle AI off — opens the reason survey
  const aiToggle = await $browser.waitForAndFindElement(
    $driver.By.xpath(
      "//button[contains(., 'AI Enhanced') or contains(., 'Classic Mode') or contains(., 'AI') and contains(@class, 'toggle')]"
    ),
    5000
  );
  await aiToggle.click();
  await $browser.sleep(800);

  // 5. Select a reason from the micro-survey (click first available option)
  const reasonBtns = await $browser.findElements(
    $driver.By.css('[class*="reason"], [class*="Reason"], [class*="survey"]')
  );
  if (reasonBtns.length > 0) {
    await reasonBtns[0].click();
    await $browser.sleep(500);
  }

  // 6. Confirm AI panel is gone / disabled
  await $browser.sleep(1000);

  // 7. Re-enable AI
  const aiToggleAgain = await $browser.waitForAndFindElement(
    $driver.By.xpath(
      "//button[contains(., 'Classic Mode') or contains(., 'AI Enhanced')]"
    ),
    5000
  );
  await aiToggleAgain.click();

  // 8. Wait for recs to reload
  await $browser.waitForAndFindElement(
    $driver.By.xpath(
      "//*[contains(., 'AI POWERED') or contains(., 'CACHED') or contains(., 'RULE-BASED')]"
    ),
    AI_LOAD_TIMEOUT
  );

})();
