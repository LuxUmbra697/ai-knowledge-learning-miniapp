export function syncCompanionRoute(character: 'pink' | 'orange') {
  const url = new URL(window.location.href)
  url.searchParams.set('character', character)
  window.history.replaceState(window.history.state, '', url)
}
