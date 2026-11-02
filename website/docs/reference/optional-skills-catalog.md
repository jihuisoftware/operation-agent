---
sidebar_position: 9
title: "Optional Skills Catalog"
description: "Official optional skills shipped with hermes-agent — install via hermes skills install official/<category>/<skill>"
---

# Optional Skills Catalog

Optional skills ship with hermes-agent under `optional-skills/` but are **not active by default**. Install them explicitly:

```bash
hermes skills install official/<category>/<skill>
```

For example:

```bash
hermes skills install official/creative/social-media-content-calendar
hermes skills install official/research/rss-feeds
```

Each skill below links to a dedicated page with its full definition, setup, and usage.

To uninstall:

```bash
hermes skills uninstall <skill-name>
```

## communication

| Skill | Description |
|-------|-------------|
| [**one-three-one-rule**](../user-guide/skills/optional/communication/communication-one-three-one-rule.md) | 1-3-1 decision briefs: problem, three options, one pick. |

## creative

| Skill | Description |
|-------|-------------|
| [**ai-presenter-video**](../user-guide/skills/optional/creative/creative-ai-presenter-video.md) | Make a verified AI presenter video from script + image. |
| [**anatomy**](../user-guide/skills/optional/creative/creative-anatomy.md) | Explain an idea as an interactive isometric machine figure. |
| [**archify**](../user-guide/skills/optional/creative/creative-archify.md) | Validated interactive HTML diagrams, upstream-maintained. |
| [**ascii-art**](../user-guide/skills/optional/creative/creative-ascii-art.md) | ASCII art: pyfiglet, cowsay, boxes, image-to-ascii. |
| [**audiocraft-audio-generation**](../user-guide/skills/optional/creative/creative-audiocraft-audio-generation.md) | AudioCraft: MusicGen text-to-music, AudioGen text-to-sound. |
| [**auteur**](../user-guide/skills/optional/creative/creative-auteur.md) | Design and build cinematic, award-level web pages. |
| [**baoyu-article-illustrator**](../user-guide/skills/optional/creative/creative-baoyu-article-illustrator.md) | Article illustrations: type × style × palette consistency. |
| [**baoyu-comic**](../user-guide/skills/optional/creative/creative-baoyu-comic.md) | Knowledge comics (知识漫画): educational, biography, tutorial. |
| [**brag**](../user-guide/skills/optional/creative/creative-brag.md) | Project launch video via Hyperframes, upstream-maintained. |
| [**brag-slim**](../user-guide/skills/optional/creative/creative-brag-slim.md) | Launch video from a project or URL, upstream-maintained. |
| [**comfyui**](../user-guide/skills/optional/creative/creative-comfyui.md) | Generate images, video, and audio via diffusion workflows. |
| [**concept-diagrams**](../user-guide/skills/optional/creative/creative-concept-diagrams.md) | Generate flat, minimal educational SVG visuals as HTML. |
| [**creative-ideation**](../user-guide/skills/optional/creative/creative-creative-ideation.md) | Generate ideas via named methods from creative practice. |
| [**draw-your-font**](../user-guide/skills/optional/creative/creative-draw-your-font.md) | Turn a handwriting photo into an installable TTF font. |
| [**dream-loop**](../user-guide/skills/optional/creative/creative-dream-loop.md) | Build stunning 3D scenes via a concept-art fidelity loop. |
| [**excalidraw**](../user-guide/skills/optional/creative/creative-excalidraw.md) | Hand-drawn Excalidraw JSON diagrams (arch, flow, seq). |
| [**heartmula**](../user-guide/skills/optional/creative/creative-heartmula.md) | HeartMuLa: Suno-like song generation from lyrics + tags. |
| [**hyperframes**](../user-guide/skills/optional/creative/creative-hyperframes.md) | Render MP4/WebM videos from HTML compositions. |
| [**impeccable**](../user-guide/skills/optional/creative/creative-impeccable.md) | Frontend design guidance, upstream-maintained (impeccable). |
| [**ip-as-logo**](../user-guide/skills/optional/creative/creative-ip-as-logo.md) | Design minimal cute IP mascot marks readable at 32px. |
| [**meme-generation**](../user-guide/skills/optional/creative/creative-meme-generation.md) | Create meme PNGs from templates with Pillow text overlay. |
| [**mono-color**](../user-guide/skills/optional/creative/creative-mono-color.md) | Generate one- or two-ink editorial print poster images. |
| [**pixel-art**](../user-guide/skills/optional/creative/creative-pixel-art.md) | Pixel art w/ era palettes (NES, Game Boy, PICO-8). |
| [**pretext**](../user-guide/skills/optional/creative/creative-pretext.md) | Build creative browser demos with DOM-free text layout. |
| [**simple-english**](../user-guide/skills/optional/creative/creative-simple-english.md) | Rewrite text to ASD-STE100 Simplified Technical English. |
| [**sketch**](../user-guide/skills/optional/creative/creative-sketch.md) | Throwaway HTML mockups: 2-3 design variants to compare. |
| [**social-media-content-calendar**](../user-guide/skills/optional/creative/creative-social-media-content-calendar.md) | Plan multi-platform social campaigns: briefs to posting. |
| [**system-atlas**](../user-guide/skills/optional/creative/creative-system-atlas.md) | Build explorable isometric architecture atlases as HTML. |
| [**tldraw-offline**](../user-guide/skills/optional/creative/creative-tldraw-offline.md) | Drive and script tldraw offline canvases with an agent. |

## data-science

| Skill | Description |
|-------|-------------|
| [**jupyter-notebook**](../user-guide/skills/optional/data-science/data-science-jupyter-notebook.md) | Iterative Python via live Jupyter kernel (hamelnb). |

## devops

| Skill | Description |
|-------|-------------|
| [**inference-sh-cli**](../user-guide/skills/optional/devops/devops-inference-sh-cli.md) | Run 150+ AI apps (image, video, LLM) via inference.sh CLI. |
| [**watchers**](../user-guide/skills/optional/devops/devops-watchers.md) | Poll RSS, JSON APIs, and GitHub with watermark dedup. |

## email

| Skill | Description |
|-------|-------------|
| [**agentmail**](../user-guide/skills/optional/email/email-agentmail.md) | Use when an agent needs AgentMail CLI email inboxes. |

## finance

| Skill | Description |
|-------|-------------|
| [**excel-author**](../user-guide/skills/optional/finance/finance-excel-author.md) | Build auditable financial workbooks headless via openpyxl. |
| [**pptx-author**](../user-guide/skills/optional/finance/finance-pptx-author.md) | Build PowerPoint decks headless with python-pptx. |

## mcp

| Skill | Description |
|-------|-------------|
| [**mcporter**](../user-guide/skills/optional/mcp/mcp-mcporter.md) | List, auth, and call MCP servers/tools from the terminal. |

## mlops

| Skill | Description |
|-------|-------------|
| [**stable-diffusion**](../user-guide/skills/optional/mlops/mlops-stable-diffusion.md) | Text-to-image generation, inpainting, and img2img. |
| [**whisper**](../user-guide/skills/optional/mlops/mlops-whisper.md) | Transcribe and translate speech in 99 languages. |

## productivity

| Skill | Description |
|-------|-------------|
| [**decision-questionnaire**](../user-guide/skills/optional/productivity/productivity-decision-questionnaire.md) | Turn an unanswerable decision into a questionnaire doc. |
| [**here-now**](../user-guide/skills/optional/productivity/productivity-here-now.md) | Publish sites to &#123;slug&#125;.here.now and store files in Drives. |
| [**live-dashboard**](../user-guide/skills/optional/productivity/productivity-live-dashboard.md) | Build self-updating dashboards from live sources. |
| [**shopify**](../user-guide/skills/optional/productivity/productivity-shopify.md) | Query Shopify Admin/Storefront GraphQL APIs via curl. |
| [**siyuan**](../user-guide/skills/optional/productivity/productivity-siyuan.md) | Query and edit a SiYuan knowledge base via its API. |

## research

| Skill | Description |
|-------|-------------|
| [**blogwatcher**](../user-guide/skills/optional/research/research-blogwatcher.md) | Monitor blogs and RSS/Atom feeds via blogwatcher-cli tool. |
| [**duckduckgo-search**](../user-guide/skills/optional/research/research-duckduckgo-search.md) | Free keyless web, news, and image search via ddgs. |
| [**osint-investigation**](../user-guide/skills/optional/research/research-osint-investigation.md) | Follow the money via public records and sanctions data. |
| [**parallel-cli**](../user-guide/skills/optional/research/research-parallel-cli.md) | Agent-native web search, deep research, and enrichment. |
| [**qmd**](../user-guide/skills/optional/research/research-qmd.md) | Hybrid local search over notes, docs, and transcripts. |
| [**rss-feeds**](../user-guide/skills/optional/research/research-rss-feeds.md) | Read RSS, Atom, JSON feeds; discover feeds behind a page. |
| [**scrapling**](../user-guide/skills/optional/research/research-scrapling.md) | Scrape sites with stealth browsing and Cloudflare bypass. |
| [**searxng-search**](../user-guide/skills/optional/research/research-searxng-search.md) | Free keyless meta-search aggregating 70+ engines. |

## security

| Skill | Description |
|-------|-------------|
| [**1password**](../user-guide/skills/optional/security/security-1password.md) | Set up op CLI, sign in, and read or inject secrets. |

## social-media

| Skill | Description |
|-------|-------------|
| [**reddit-reading**](../user-guide/skills/optional/social-media/social-media-reddit-reading.md) | Read Reddit: subreddits, search, threads, users. No browser. |

## web-development

| Skill | Description |
|-------|-------------|
| [**cloudflare-temporary-deploy**](../user-guide/skills/optional/web-development/web-development-cloudflare-temporary-deploy.md) | Deploy a Worker live, no account, via wrangler --temporary. |
| [**publish-site**](../user-guide/skills/optional/web-development/web-development-publish-site.md) | Versioned site deploys to GitHub/Cloudflare/Netlify Pages. |
| [**scrollcraft**](../user-guide/skills/optional/web-development/web-development-scrollcraft.md) | Premium scroll-driven landing pages; scroll = timeline. |

---

## Contributing Optional Skills

To add a new optional skill to the repository:

1. Create a directory under `optional-skills/<category>/<skill-name>/`
2. Add a `SKILL.md` with standard frontmatter (name, description, version, author)
3. Include any supporting files in `references/`, `templates/`, or `scripts/` subdirectories
4. Submit a pull request — the skill will appear in this catalog and get its own docs page once merged
