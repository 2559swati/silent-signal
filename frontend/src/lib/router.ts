import { useEffect, useState } from 'react';

// Minimal hash router: #/ #/assets #/asset/CODE #/risk #/explanations
// #/actions #/map #/security #/settings. Zero dependencies, deterministic.

export type Route =
  | { name: 'dashboard' }
  | { name: 'assets' }
  | { name: 'asset'; code: string }
  | { name: 'risk' }
  | { name: 'explanations' }
  | { name: 'actions' }
  | { name: 'map' }
  | { name: 'security' }
  | { name: 'settings' };

export function parseHash(hash: string): Route {
  const clean = hash.replace(/^#/, '') || '/';
  const assetMatch = /^\/asset\/([^/]+)\/?$/.exec(clean);
  if (assetMatch) return { name: 'asset', code: decodeURIComponent(assetMatch[1]) };
  switch (clean) {
    case '/':
      return { name: 'dashboard' };
    case '/assets':
      return { name: 'assets' };
    case '/risk':
      return { name: 'risk' };
    case '/explanations':
      return { name: 'explanations' };
    case '/actions':
      return { name: 'actions' };
    case '/map':
      return { name: 'map' };
    case '/security':
      return { name: 'security' };
    case '/settings':
      return { name: 'settings' };
    default:
      return { name: 'dashboard' };
  }
}

export function routeHref(route: Route): string {
  switch (route.name) {
    case 'dashboard':
      return '#/';
    case 'assets':
      return '#/assets';
    case 'asset':
      return `#/asset/${encodeURIComponent(route.code)}`;
    case 'risk':
      return '#/risk';
    case 'explanations':
      return '#/explanations';
    case 'actions':
      return '#/actions';
    case 'map':
      return '#/map';
    case 'security':
      return '#/security';
    case 'settings':
      return '#/settings';
  }
}

export function navigate(route: Route): void {
  window.location.hash = routeHref(route);
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() =>
    typeof window === 'undefined' ? { name: 'dashboard' } : parseHash(window.location.hash),
  );
  useEffect(() => {
    const onChange = (): void => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}

export function useScrollTopOnRoute(route: Route): void {
  const key = route.name === 'asset' ? `asset-${route.code}` : route.name;
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior });
  }, [key]);
}
