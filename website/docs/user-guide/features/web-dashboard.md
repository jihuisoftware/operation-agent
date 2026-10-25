---
sidebar_position: 15
title: "Web Dashboard migration"
description: "This branch uses Hermes Desktop; the browser dashboard is removed while shared backend APIs remain."
---

# Web Dashboard migration

This branch uses **Hermes Desktop** as its primary interface. The browser dashboard
SPA, its `web/` workspace, and the `hermes dashboard` launch entry point have been
removed. This page retains the previous documentation URL for migration links.

Use the [Desktop guide](../desktop.md) for the supported graphical interface.
The TUI and CLI remain available for terminal use, automation, and diagnostics.

## What remains

Desktop continues to use the shared gateway, session/RPC contracts, and HTTP APIs.
The Python modules named `hermes_cli/web_server*` and `hermes_cli/web_routers/`
remain backend infrastructure; `apps/shared/` and `tui_gateway/` are also retained.
A filename containing `web` does not imply a dependency on the retired SPA.

Browser dashboard build, theme, and navigation instructions from upstream Hermes
no longer apply to this branch. Installing upstream Hermes does not install this
branch's Desktop-focused changes.

## Chat

Use Desktop chat for conversations, streaming, tool activity, and user decisions.
The old browser `/chat` page and its SPA assets are no longer an entry point.
Desktop is a native Electron/React interface; it does not embed the retired
browser dashboard.

## Connecting Hermes Desktop to a remote backend

Use Desktop's existing connection workflow. See
[Connecting to a remote backend](../desktop.md#connecting-to-a-remote-backend).
Removing the browser frontend does not remove the shared backend connection or
its authentication requirements. Do not start an upstream browser dashboard as a
workaround for a missing Desktop connection capability.

## Managing multiple profiles

Use [Desktop sessions and profiles](../desktop.md#sessions--profiles) or the CLI.
Profile-scoped settings, credentials, and sessions still belong to the backend.
Existing profile isolation must remain intact when adding operations features.

## REST API

Authenticated APIs used by Desktop and plugins remain available through the
configured backend connection. Their availability and access checks are owned by
the shared backend, independently of the removed frontend.

For new Desktop functionality, prefer the
[Desktop Plugin SDK](../../developer-guide/desktop-plugin-sdk.md) and its scoped
backend access. Do not infer that a retained endpoint is public, and do not copy
credentials or URLs from an old browser dashboard setup.

## Authentication (gated mode)

The browser dashboard login page is no longer provided. Retained backend APIs
continue to enforce their configured authentication and profile access rules.
Removing the SPA is not a reason to remove authentication middleware or change
Desktop's private gateway connection flow.

### Default provider: Nous Research

Upstream browser dashboard login instructions are retired on this branch. Model
provider sign-in and Desktop connection authentication are separate concerns;
use the relevant Desktop settings and connection workflow.

### Username/password provider (no OAuth IdP)

The former browser login form is unavailable. Existing backend authentication
configuration is handled by the shared server; this migration does not grant
unauthenticated access or require users to replace their credentials.

### Custom providers

Backend authentication extensions must follow the shared server's current
registration and access contracts. They do not restore the removed browser UI.
For the supported product extension surface, see
[Build a Hermes Plugin](../../developer-guide/plugins/index.md) and the
[Desktop Plugin SDK](../../developer-guide/desktop-plugin-sdk.md).

## Existing extensions

Browser theme files, dashboard tabs, and `window.__HERMES_PLUGIN_SDK__` extensions
have no browser host in this branch. Migrate their UI to Desktop and retain any
needed authenticated backend APIs. See
[Dashboard extension migration](./extending-the-dashboard.md).
