# Cross-Viewport Testing

## 1. Purpose and scope
- Why: backlog item US-06 ("site works well on my phone").
- In scope: the six frontend routes (Rankings, Team Details list, Team Details page,
  Weekly Odds, Matchup, Methodology).
- Out of scope: backend/API behavior, accessibility audit beyond tap targets, performance.

## 2. Pass criteria (applies to every page and viewport)
1. The page never scrolls horizontally (inner `.table-wrap` / `.eq-body` scrolling is allowed).
2. No clipped, overlapping, or unreadable text.
3. All nav links and primary controls are reachable and usable by touch.
4. The sticky top bar does not hide content.
5. Text is readable without pinch-zoom.
6. Interactive elements are at least 24px (WCAG 2.2 AA); note any under 44px.

## 3. Test matrix
### Viewports (chosen around the CSS breakpoints at 600 / 760 / 960px)
| Size | Reason |
|---|---|
| 320×568 | `body` min-width floor |
| 390×844 | typical phone |
| 844×390 | phone landscape |
| 599 / 601, 759 / 761, 959 / 961 | either side of each breakpoint |
| 768×1024 | tablet portrait |
| 1280×800, 1920×1080 | desktop; `.app-shell` max-width 1200px |

### Browsers
Chromium, WebKit (Safari proxy), Firefox via Playwright; real iPhone Safari and
Android Chrome for the manual pass.

## 4. Environment and how to run
- Node / npm versions, Playwright version, OS used for baselines.
- Start backend: `uvicorn app.main:app --reload`
- Run: `cd frontend && npx playwright test`
- Update baselines: `npx playwright test --update-snapshots`
- Real-device setup: `vite --host`, `VITE_API_BASE_URL`, uvicorn `--host 0.0.0.0`,
  and the temporary CORS origin change.

## 5. Automated tests
What `e2e/viewports.spec.js` covers: the overflow assertion and full-page screenshots
for every route × viewport. Note the stubbed logo requests and the wait for fonts.

## 6. Manual checklist (per page)
| Page | What to check | Pass criteria / notes |
|---|---|---|
| Rankings | table scrolls inside wrapper, sort buttons work by touch | no page-level overflow |
| Weekly Odds | 12 columns at 700–1000px, kickoff time and team name wrapping | |
| Team Details | `.trend-chart` with many weeks; schedule row at 320px | opponent name still legible |
| Matchup | pickers at 601–700px; score size at 320px | |
| Methodology | equations scroll in their own box; figures scale; TOC at 961–1100px | |
| All | sticky bar height on phones and landscape | |

## 7. Results log
| Date | Tester | Build/commit | Browser/device | Viewport | Page | Result | Issue # |
|---|---|---|---|---|---|---|---|

## 8. Defects found
| ID | Page / viewport | Description | Severity | Status | Fix commit |
|---|---|---|---|---|---|

## 9. Known limitations and accepted deviations
Example: Inter is not loaded, so fonts fall back per OS and wrapping differs slightly.

## 10. Re-test policy
When to rerun: any CSS change, new page or component, dependency upgrade of
React/Vite, and before each release. Name who signs off.