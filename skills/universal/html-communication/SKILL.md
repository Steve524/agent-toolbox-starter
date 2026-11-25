---
name: html-communication
description: Use when the user asks for an HTML write-up about the work, such as a plan, spec, findings, summary, report, comparison, or UI mock variants. Not for HTML that ships in the product.
---

# HTML communication

Adapted from `html-communication` in the `postplan` 0.0.6 npm package (MIT, see `LICENSE`). The original always publishes to Postplan. This one is local only.

## The page

- **One self-contained file, under 512 KB.** Inline `<style>` and inline SVG. No remote assets: no CDNs, web fonts, remote images, or trackers. Embed small local images as data URIs.
- **Script only when interactivity really helps.** Keep it inline, and keep the page readable with JavaScript off.
- **Answer first.** The top of the page says the result or recommendation. Write it like a spec: dense and scannable. Detail goes below, or in `<details>`. No hero section, badges, decorative chrome, marketing voice, or em dashes.
- **Safe to share.** No secrets, tokens, private URLs, or local file paths in the page. External links get `target="_blank" rel="noopener noreferrer"`.
- **Accessible.** Set `lang`. Keep headings in order. Use `<main>` and `<section>`. Data goes in a real `<table>` with `<th scope>`. Give images alt text. Keep text contrast readable.
- **Responsive.** Use a fluid width that works at 360px. Wrap wide tables in a block with `overflow-x: auto`. Respect `prefers-reduced-motion`.
- **Theme-aware.** Leave the page background unset. Set `:root { color-scheme: light dark }`. Use T3's theme variables with system-color fallbacks: `var(--foreground, CanvasText)`, `var(--border, GrayText)`. In T3 the page follows the user's theme. Anywhere else it follows the OS light or dark mode.
- **Use color for meaning.** `--accent` for emphasis. `--success`, `--warning`, `--destructive` for status. `--chart-1` to `--chart-6` for series. Give each a hex fallback, like `var(--chart-1, #346bf1)`, so it works outside T3. Pair every color with a label.
- **Accurate.** Every number matches its source. Write dates as absolute dates.

**UI mock variants:** render each as a real styled block, not a description of one. Label them A, B, C so the user can reply with one letter. Put them side by side or in a clear sequence. On the next round, overwrite the same file so the path stays stable.

## Deliver it

**Always save it as a local file first.** Put it outside the repo unless the user wants it in the repo. Give the absolute path.

**T3 (`html_preview` and `html_render` are available):** also call `html_preview`. Fix every console error, and check the page at about 390px wide in light and dark. Then call `html_render` before your final reply. Set `height` to the preview's `contentHeight`, clamped to 80–2000. A longer page scrolls inside the frame. The reply adds only what the page doesn't say.

**Anywhere else:** open it in the browser if the user wants (`open` on Mac, `xdg-open` on Linux, `start` on Windows). If a browser tool such as `playwright-cli` is available, screenshot the page and check it.

Save the page locally and give the user its path. Upload only on explicit request to a destination the user has approved.

## Example

Bad: a 600-line page that loads Tailwind and Chart.js from a CDN, sets `background: #000`, opens with a hero banner, and buries the recommendation in section 4.

Good: a single file with no network requests. The first line says "Pick option B: half the cost, same latency". Then comes a three-row comparison table and a collapsible "how we measured" section.
