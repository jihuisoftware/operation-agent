# Website

本目录包含从 Hermes 继承的共享运行时参考。当前运营版仅支持 macOS Desktop 与简体中文，产品范围以[根 README](../README.md)、[平台支持](docs/getting-started/platform-support.md)和 `hermes_cli/data/operations-profile.json` 为准。

[快速开始](docs/getting-started/quickstart.md)与[安装说明](docs/getting-started/installation.md)面向当前分支。其他系统、旧消息适配器、Dashboard、Kanban、delegation、MCP 的专题说明保留为实现或历史参考，不代表运营版入口已开放，也不承诺上游网站的安装包属于本分支。技术参考使用英文不意味着产品提供英文界面。

This website is built using [Docusaurus](https://docusaurus.io/), a modern static website generator.

> **Reading the docs on GitHub?** The Markdown under `docs/` is authored for the rendered site at
> <https://hermes-agent.nousresearch.com/docs/>. Cross-page links are relative Markdown paths, so they
> follow through on GitHub's file viewer too. Every page on the site has an **Edit this page** link
> that opens the source file here.

## Authoring links in `docs/`

- Link to another page with a relative Markdown path, anchors included:
  `[Profiles](../user-guide/profiles.md)`, `[Bundles](../user-guide/features/skills.md#skill-bundles)`.
  Docusaurus turns the file path into the page route; GitHub follows the same path. Site routes
  (`/user-guide/profiles`, `/docs/user-guide/profiles`) only work on the rendered site — GitHub
  resolves them as repository paths and 404s, and the `/docs/` form also emits
  `/docs/zh-Hans/docs/...` 404s in the zh-Hans build because `baseUrl` is already `/docs/`.
- `python3 website/scripts/check_doc_links.py` fails on any route-style link in hand-authored pages
  (EN and the zh-Hans mirror); `--fix` rewrites them. It runs in the `Docs Site Checks` workflow.
  Generated pages (`user-guide/skills/{bundled,optional}`, `reference/*skills-catalog.md`) are
  produced by `scripts/generate-skill-docs.py`, which emits the same relative form.
- Pin `{#anchor}` on cross-linked headings so the zh-Hans mirror keeps the same id.

## Installation

```bash
yarn
```

## Local Development

```bash
yarn start
```

This command starts a local development server and opens up a browser window. Most changes are reflected live without having to restart the server.

## Build

```bash
yarn build
```

This command generates static content into the `build` directory and can be served using any static contents hosting service.

## Deployment

Using SSH:

```bash
USE_SSH=true yarn deploy
```

Not using SSH:

```bash
GIT_USER=<Your GitHub username> yarn deploy
```

If you are using GitHub pages for hosting, this command is a convenient way to build the website and push to the `gh-pages` branch.

## Diagram Linting

CI runs `ascii-guard` to lint docs for ASCII box diagrams. Use Mermaid (````mermaid`) or plain lists/tables instead of ASCII boxes to avoid CI failures.
