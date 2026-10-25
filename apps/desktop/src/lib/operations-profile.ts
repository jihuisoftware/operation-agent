import profile from '../../../../hermes_cli/data/operations-profile.json'

export const OPERATIONS_PROFILE = profile
export const DISABLED_OPERATIONS_ROUTES: readonly string[] = profile.desktop.disabledRoutes

export function operationsPluginAllowed(id: string): boolean {
  return !profile.desktop.disabledPlugins.includes(id)
}

export function operationsRouteAllowed(path: string): boolean {
  return !DISABLED_OPERATIONS_ROUTES.includes(path.split(/[?#]/, 1)[0])
}

export function operationsCommandAllowed(command: string): boolean {
  return !profile.desktop.disabledCommands.includes(command.replace(/^\//, ''))
}
