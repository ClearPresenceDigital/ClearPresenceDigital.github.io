# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ClearPresence Digital marketing website — a **static GitHub Pages site** for a local business review management and Google Business Profile service based in New Jersey.

- **Live domain**: clearpresencedigital.com (configured via `CNAME`)
- **Hosting**: GitHub Pages (deploys automatically on push to `main`)
- **Architecture**: Single `index.html` file with all CSS inlined in a `<style>` block. No build step, no JavaScript frameworks, no external stylesheets.

## Development

There is no build system, bundler, or test suite. To preview changes locally, open `index.html` in a browser or use any local HTTP server:

```bash
python3 -m http.server 8000
# Then visit http://localhost:8000
```

Deploying is just pushing to `main` — GitHub Pages picks up changes automatically.

## Key Details

- **Form backend**: Contact form submits to Formspree (`https://formspree.io/f/xeeganjy`) via POST. Includes a honeypot field (`_gotcha`) for spam prevention.
- **CSS variables**: All theming is controlled via CSS custom properties in `:root` (accent color `#0b66ff`, surface/border/text colors). Change these to restyle the whole site.
- **Responsive**: Single breakpoint at `max-width: 960px` collapses grids to single-column.
- **Sections**: Hero, Services (`#services`), Pricing with FAQ, Contact form (`#contact`), Footer.
- **No JS**: The site is pure HTML/CSS. Any interactivity additions would need to consider that there's currently zero JavaScript.
