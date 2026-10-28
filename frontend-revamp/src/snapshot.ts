export async function loadSnapshotRoutes(
  routes: Record<string, string>,
  fetchRoute: (route: string) => Promise<unknown>,
  publish: (key: string, value: unknown, error: boolean) => void,
): Promise<void> {
  await Promise.all(Object.entries(routes).map(async ([key, route]) => {
    try {
      publish(key, await fetchRoute(route), false);
    } catch {
      publish(key, undefined, true);
    }
  }));
}
