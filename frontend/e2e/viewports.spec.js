// frontend/e2e/viewports.spec.js
import { test, expect } from '@playwright/test'

const sizes = [[320,568],[390,844],[844,390],[601,900],[761,900],[768,1024],[961,800],[1280,800],[1920,1080]]
const routes = ['/#/', '/#/team', '/#/team/1', '/#/odds', '/#/matchup', '/#/methodology']

for (const [w, h] of sizes) for (const route of routes) {
  test(`${route} @ ${w}x${h}`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h })
    await page.goto(route)
    await page.waitForLoadState('networkidle')

    // The page itself must never scroll sideways (inner .table-wrap scrolling is fine).
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow).toBeLessThanOrEqual(0)

    await expect(page).toHaveScreenshot(`${route.replace(/\W/g, '_')}-${w}x${h}.png`, { fullPage: true })
  })
}