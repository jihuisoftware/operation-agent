---
sidebar_position: 17
title: "Dashboard extension migration"
description: "Migrate retired browser dashboard extensions to the supported Desktop Plugin SDK."
---

# Dashboard extension migration

This branch uses Hermes Desktop and no longer ships the browser dashboard SPA.
The old dashboard theme/tab/shell-slot system and
`window.__HERMES_PLUGIN_SDK__` are not supported UI extension targets here.
This page keeps the original documentation URL so existing links can reach the
migration guidance.

Build new operations pages with the
[Desktop Plugin SDK](../../developer-guide/desktop-plugin-sdk.md). Desktop uses
`@hermes/plugin-sdk`; browser dashboard bundles and manifests cannot be loaded
as Desktop plugins without adapting their UI to that SDK.

## Migration steps

1. Identify the extension's business operations and the authenticated backend
   endpoints it needs. Keep those responsibilities in the backend plugin.
2. Recreate its page, pane, or sidebar contribution using the Desktop SDK's
   documented contribution points. Keep the existing Desktop chat surface.
3. Use the SDK's scoped backend access so requests follow the active connection
   and Profile. Do not embed credentials or a hardcoded server address in the UI.
4. Verify the migrated UI against the real backend contract, including failed
   requests and Profile changes, before retiring the old extension package.

A browser-only CSS theme does not have a direct runtime host in this branch.
Desktop themes use the Desktop SDK's own contribution contract.

## Backend API routes

Removing the browser frontend does **not** remove the shared Python HTTP server,
Desktop-consumed REST routes, or the plugin API namespace. Keep required
`plugin_api.py` endpoints and their authentication and Profile checks intact.
For the supported client contract, see
[A backend for your plugin](../../developer-guide/desktop-plugin-sdk.md#a-backend-for-your-plugin).

A route's existing access policy remains authoritative. The former dashboard's
localhost assumptions do not authorize an unauthenticated replacement endpoint.
Route changes belong in topical backend modules and must preserve Desktop callers.

## Don't block the event loop

Shared API handlers serve Desktop as well as other backend clients. Move blocking
I/O out of asynchronous request handlers using the existing backend patterns;
preserve the owning Profile's context when starting deferred work. A slow plugin
request must not stall unrelated sessions.

## Related guides

- [Desktop](../desktop.md)
- [Desktop Plugin SDK](../../developer-guide/desktop-plugin-sdk.md)
- [Build a Hermes Plugin](../../developer-guide/plugins/index.md)
- [Web Dashboard migration](./web-dashboard.md)
