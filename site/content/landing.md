<!--
  landing.md — the ONLY site-authored Markdown.

  Marketing decomposition (hero subtitle, feature cards, how-it-works steps)
  that exists nowhere else. The hero headline, install commands and usage are
  rendered from README.md (the canonical source). Keep this TL;DR and punchy.

  Format contract (parsed by site/src/lib/content.ts):
    "## Subtitle"     → the hero subtitle (one short line)
    "## Features"     → each "### " below it becomes a feature card
    "## How it works" → each "### " below it becomes a numbered step
  Icons are assigned by order in the components (presentation), not here.
-->

# frontprompt

## Subtitle

A real browser, an in-page HUD, and a built-in MCP server — you and your agent annotate and drive the same live page.

## Features

### In-page overlay

A shadow-DOM HUD on any page. Pick, region, relate — right on the live site.

### Cross-origin survival

State lives in Python, not the page. Navigate anywhere; your picks stay.

### MCP server built in

Your agent navigates, queries, screenshots, and reads your picks as state.

### Zero-config install

One command. Launches via `uvx`, Chromium self-installs. No Bun, no Node.

## How it works

### Open

`frontprompt show <url>` opens real Chromium with the HUD on top.

### Annotate

Pick elements, capture regions, draw relations — each a real entity, not a brittle selector.

### Drive

Point your agent at `frontprompt mcp`. It reads your picks as state and acts.
