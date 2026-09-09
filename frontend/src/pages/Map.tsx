import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { MapContainer, Marker, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Card, EmptyState, ErrorState } from '../components/ui';
import { api } from '../lib/api';
import { navigate, routeHref } from '../lib/router';
import type { MapAsset } from '../lib/types';
import {
  RADII_KM,
  RISK_BANDS,
  areaSummary,
  bandOf,
  haversineKm,
  nearbyAssets,
  searchLocations,
  type GeocodeResult,
  type RiskBand,
} from '../lib/geo';

// Status colors: the exact UI V1 fusion conventions (NetworkGrid/badges).
// Legend labels follow the fleet status vocabulary (Healthy/Watch/
// Emerging/Critical); marker color prefers the live fusion status and
// falls back to the Phase 2 asset status when fusion data is absent.
const STATUS_COLOR: Record<string, string> = {
  NORMAL: '#22c55e',
  healthy: '#22c55e',
  WATCH: '#eab308',
  watch: '#eab308',
  EMERGING: '#f97316',
  emerging: '#f97316',
  CRITICAL: '#f04452',
  critical: '#f04452',
};

const LEGEND: { label: string; color: string }[] = [
  { label: 'Healthy', color: '#22c55e' },
  { label: 'Watch', color: '#eab308' },
  { label: 'Emerging', color: '#f97316' },
  { label: 'Critical', color: '#f04452' },
];

// Demo focus asset: used ONLY to frame the initial view and highlight one
// marker. It is located dynamically from the API response -- its
// coordinates are never hardcoded, and framing falls back gracefully.
const FOCUS_CODE = 'SL-1042';

function colorFor(asset: MapAsset): string {
  const key = asset.fusion_status ?? asset.status;
  return STATUS_COLOR[key] ?? '#94a3b8';
}

function validAssets(assets: MapAsset[]): MapAsset[] {
  return assets.filter(
    (a) =>
      typeof a.latitude === 'number' &&
      typeof a.longitude === 'number' &&
      Number.isFinite(a.latitude) &&
      Number.isFinite(a.longitude),
  );
}

function FitBounds({ assets }: { assets: MapAsset[] }): null {
  const map = useMap();
  useEffect(() => {
    const pts = validAssets(assets);
    if (pts.length === 0) return;
    map.fitBounds(
      L.latLngBounds(pts.map((a) => [a.latitude as number, a.longitude as number])),
      { padding: [32, 32] },
    );
  }, [assets, map]);
  return null;
}

function Recenter({ point }: { point: { lat: number; lon: number } | null }): null {
  const map = useMap();
  const last = useRef<string | null>(null);
  useEffect(() => {
    if (!point) return;
    const key = `${point.lat},${point.lon}`;
    if (last.current === key) return;
    last.current = key;
    map.flyTo([point.lat, point.lon], Math.max(map.getZoom(), 13), { duration: 0.8 });
  }, [point, map]);
  return null;
}

function pinIcon(kind: 'search' | 'me'): L.DivIcon {
  return L.divIcon({
    className: '',
    html: `<div class="${kind === 'search' ? 'search-pin' : 'geo-pin'}" role="img" aria-label="${
      kind === 'search' ? 'Searched location' : 'Current location'
    }"></div>`,
    iconSize: [30, 42],
    iconAnchor: [15, 40],
    popupAnchor: [0, -36],
  });
}

export interface SelectedPoint {
  name: string;
  displayName: string;
  lat: number;
  lon: number;
  mine: boolean;
}

const ALL_BANDS: Record<RiskBand, boolean> = { CRITICAL: true, HIGH: true, MEDIUM: true, LOW: true };

export default function Map(): ReactNode {
  const [assets, setAssets] = useState<MapAsset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const focusRef = useRef<L.CircleMarker | null>(null);

  // Phase 11 location intelligence (all client-side, no stored user data).
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedPoint | null>(null);
  const [radiusKm, setRadiusKm] = useState<number | null>(10);
  const [bands, setBands] = useState<Record<RiskBand, boolean>>({ ...ALL_BANDS });
  const [geoError, setGeoError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const searchSeq = useRef(0);

  useEffect(() => {
    let cancelled = false;
    api
      .map()
      .then((res) => {
        if (!cancelled) setAssets(res.assets);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load map data');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Debounced autocomplete (polite Nominatim usage: >=3 chars, 400ms).
  useEffect(() => {
    const q = query.trim();
    if (q.length < 3) {
      setResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    setSearchError(null);
    const id = window.setTimeout(() => {
      const seq = ++searchSeq.current;
      const controller = new AbortController();
      searchLocations(q, controller.signal)
        .then((res) => {
          if (searchSeq.current !== seq) return;
          setResults(res);
          setShowResults(true);
          setSearching(false);
        })
        .catch((err: unknown) => {
          if (searchSeq.current !== seq) return;
          if (err instanceof DOMException && err.name === 'AbortError') return;
          setSearching(false);
          setSearchError('Unable to search location. Please try again.');
        });
    }, 400);
    return () => window.clearTimeout(id);
  }, [query]);

  const plotted = useMemo(() => (assets ? validAssets(assets) : []), [assets]);
  const focus = useMemo(
    () => plotted.find((a) => a.external_code === FOCUS_CODE) ?? null,
    [plotted],
  );
  const initialCenter = useMemo<[number, number]>(() => {
    if (focus && focus.latitude !== null && focus.longitude !== null) {
      return [focus.latitude, focus.longitude];
    }
    if (plotted.length > 0) {
      const lat = plotted.reduce((s, a) => s + (a.latitude as number), 0) / plotted.length;
      const lon = plotted.reduce((s, a) => s + (a.longitude as number), 0) / plotted.length;
      return [lat, lon];
    }
    return [12.9716, 77.5946];
  }, [focus, plotted]);

  // Open the focus marker popup once the map is ready (demo discoverability).
  useEffect(() => {
    if (focus && !selected) {
      const t = window.setTimeout(() => focusRef.current?.openPopup(), 600);
      return () => window.clearTimeout(t);
    }
  }, [focus, selected]);

  function selectResult(r: GeocodeResult, mine = false): void {
    setSelected({ name: r.name, displayName: r.displayName, lat: r.lat, lon: r.lon, mine });
    setShowResults(false);
    setSearchError(null);
    setGeoError(null);
  }

  function submitSearch(): void {
    const q = query.trim();
    if (q.length < 3) return;
    setSearching(true);
    searchLocations(q)
      .then((res) => {
        setSearching(false);
        if (res.length === 0) {
          setResults([]);
          setShowResults(false);
          setSearchError('No location found. Try another search.');
        } else {
          selectResult(res[0]);
        }
      })
      .catch(() => {
        setSearching(false);
        setSearchError('Unable to search location. Please try again.');
      });
  }

  function useMyLocation(): void {
    setGeoError(null);
    if (!('geolocation' in navigator)) {
      setGeoError('Geolocation is not supported by this browser. You can search for a location manually.');
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        // Coordinates stay in memory only: centered, never stored or logged.
        selectResult(
          {
            name: 'My location',
            displayName: 'Current position (browser geolocation)',
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
          },
          true,
        );
      },
      (err) => {
        setLocating(false);
        setGeoError(
          err.code === err.PERMISSION_DENIED
            ? 'Location access was denied. You can search for a location manually.'
            : 'Current location is unavailable. You can search for a location manually.',
        );
      },
      { timeout: 10000, maximumAge: 60000 },
    );
  }

  function clearAll(): void {
    setQuery('');
    setResults([]);
    setShowResults(false);
    setSearchError(null);
    setSelected(null);
    setRadiusKm(10);
    setBands({ ...ALL_BANDS });
    setGeoError(null);
  }

  // Nearby intelligence: real haversine over API coordinates, memoized.
  const distances = useMemo(() => {
    const map = new globalThis.Map<string, number>();
    if (!selected || !assets) return map;
    for (const a of assets) {
      if (typeof a.latitude !== 'number' || typeof a.longitude !== 'number') continue;
      map.set(a.asset_id, haversineKm(selected.lat, selected.lon, a.latitude, a.longitude));
    }
    return map;
  }, [selected, assets]);

  const inRadius = useMemo(() => {
    const set = new globalThis.Set<string>();
    if (!selected || !assets) return set;
    for (const n of nearbyAssets(validAssets(assets), selected.lat, selected.lon, radiusKm)) {
      set.add(n.asset.asset_id);
    }
    return set;
  }, [selected, assets, radiusKm]);

  const summary = useMemo(
    () =>
      selected && assets
        ? areaSummary(nearbyAssets(validAssets(assets), selected.lat, selected.lon, radiusKm))
        : null,
    [selected, assets, radiusKm],
  );

  const searchPin = useMemo(() => pinIcon('search'), []);
  const mePin = useMemo(() => pinIcon('me'), []);

  if (error) {
    return (
      <div className="space-y-4 animate-rise">
        <MapHeading count={0} />
        <ErrorState message={error} onRetry={() => window.location.reload()} />
      </div>
    );
  }

  if (!assets) {
    return (
      <div className="space-y-4 animate-rise">
        <MapHeading count={0} />
        <div className="skeleton h-[560px] w-full rounded-2xl" aria-label="Loading map" />
      </div>
    );
  }

  if (plotted.length === 0) {
    return (
      <div className="space-y-4 animate-rise">
        <MapHeading count={assets.length} />
        <EmptyState message="No mappable assets returned by the API." />
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-rise">
      <MapHeading count={plotted.length} />

      {/* Location search */}
      <Card className="p-4">
        <form
          role="search"
          aria-label="Location search"
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            submitSearch();
          }}
        >
          <div className="relative min-w-0 flex-1">
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setShowResults(true);
              }}
              onFocus={() => results.length > 0 && setShowResults(true)}
              placeholder="Search location..."
              aria-label="Search location"
              autoComplete="off"
              className="w-full rounded-xl border border-edge bg-panel-2 px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-500 focus:border-sky-500/60 focus:outline-none"
            />
            {showResults && (results.length > 0 || searching) ? (
              <ul
                role="listbox"
                aria-label="Matching locations"
                className="absolute inset-x-0 top-full z-[600] mt-1 max-h-56 overflow-y-auto scroll-thin rounded-xl border border-edge bg-panel py-1 shadow-xl"
              >
                {searching ? (
                  <li className="px-4 py-2.5 text-sm text-slate-500" aria-label="Searching">
                    Searching...
                  </li>
                ) : null}
                {results.map((r, i) => (
                  <li key={`${r.lat},${r.lon},${i}`}>
                    <button
                      type="button"
                      role="option"
                      aria-selected="false"
                      onClick={() => selectResult(r)}
                      className="block w-full truncate px-4 py-2.5 text-left text-sm text-slate-900 transition hover:bg-slate-900/[0.04]"
                      title={r.displayName}
                    >
                      {r.displayName}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <div className="flex shrink-0 gap-2">
            <button
              type="submit"
              disabled={query.trim().length < 3 || searching}
              className="rounded-xl bg-sky-600 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {searching ? 'Searching...' : 'Search'}
            </button>
            <button
              type="button"
              onClick={useMyLocation}
              disabled={locating}
              className="rounded-xl border border-edge bg-panel-2 px-4 py-2.5 text-sm font-bold text-slate-900 transition hover:border-sky-500/50 disabled:opacity-50"
            >
              {locating ? 'Locating...' : 'Use my location'}
            </button>
            {selected ? (
              <button
                type="button"
                onClick={clearAll}
                className="rounded-xl border border-edge bg-panel-2 px-4 py-2.5 text-sm font-bold text-slate-600 transition hover:text-slate-900"
              >
                Clear
              </button>
            ) : null}
          </div>
        </form>
        {searchError ? (
          <p role="alert" className="mt-2 text-sm font-semibold text-red-600">
            {searchError}
          </p>
        ) : null}
        {geoError ? (
          <p role="alert" className="mt-2 text-sm font-semibold text-amber-700">
            {geoError}
          </p>
        ) : null}
        <p className="mt-2 text-[11px] text-slate-500">
          Location search by OpenStreetMap Nominatim. Fleet coordinates are the documented
          schematic demo layout, so nearby results are meaningful around the fleet area.
        </p>
      </Card>

      <div className="grid gap-4 xl:grid-cols-4">
      <Card className="map-enter overflow-hidden p-0 xl:col-span-3">
        <div className="relative">
          <MapContainer
            center={initialCenter}
            zoom={15}
            scrollWheelZoom
            style={{ height: 560, width: '100%' }}
            aria-label="Infrastructure fleet map"
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <FitBounds assets={plotted} />
            <Recenter point={selected} />
            {selected ? (
              <Marker
                position={[selected.lat, selected.lon]}
                icon={selected.mine ? mePin : searchPin}
                aria-label={selected.mine ? 'Current location' : 'Searched location'}
              >
                <Popup>
                  <div style={{ minWidth: 180 }}>
                    <strong>{selected.mine ? '📍 Current location' : `📍 ${selected.name}`}</strong>
                    <br />
                    <span style={{ fontSize: 12 }}>{selected.displayName}</span>
                    <br />
                    <span style={{ fontSize: 12 }}>
                      {selected.lat.toFixed(5)}, {selected.lon.toFixed(5)}
                    </span>
                    <br />
                    <span style={{ fontSize: 12 }}>
                      {summary ? `${summary.total} SilentSignal assets nearby` : 'No nearby assets'}
                    </span>
                  </div>
                </Popup>
              </Marker>
            ) : null}
            {plotted.map((a) => {
              const isFocus = !selected && focus !== null && a.external_code === focus.external_code;
              const band = bandOf(a);
              const outOfRadius = selected !== null && radiusKm !== null && !inRadius.has(a.asset_id);
              const filteredOut = !bands[band];
              const dimmed = outOfRadius || filteredOut;
              const distance = distances.get(a.asset_id);
              return (
                <CircleMarker
                  key={a.asset_id}
                  center={[a.latitude as number, a.longitude as number]}
                  radius={isFocus ? 11 : dimmed ? 5 : 7}
                  pathOptions={{
                    color: isFocus ? '#ffffff' : colorFor(a),
                    weight: isFocus ? 3 : 1.5,
                    fillColor: colorFor(a),
                    fillOpacity: dimmed ? 0.12 : 0.9,
                  }}
                  ref={isFocus ? focusRef : undefined}
                >
                  <Popup>
                    <div style={{ minWidth: 160 }}>
                      <strong style={{ fontFamily: 'monospace' }}>{a.external_code}</strong>
                      <br />
                      Status: {a.fusion_status ?? a.status}
                      {a.risk_level ? (
                        <>
                          <br />
                          Risk: {a.risk_level}
                          {typeof a.risk_score === 'number' ? ` (${(a.risk_score * 100).toFixed(1)}%)` : ''}
                        </>
                      ) : null}
                      {selected && typeof distance === 'number' ? (
                        <>
                          <br />
                          {distance.toFixed(1)} km from selected location
                        </>
                      ) : null}
                      <br />
                      <a href={routeHref({ name: 'asset', code: a.external_code })}>View Risk Details →</a>
                    </div>
                  </Popup>
                </CircleMarker>
              );
            })}
          </MapContainer>
          {/* Fixed legend */}
          <div
            className="absolute bottom-4 left-4 z-[500] rounded-xl border border-edge bg-panel/95 px-3 py-2 shadow-xl backdrop-blur"
            aria-label="Map legend"
          >
            <ul className="space-y-1">
              {LEGEND.map((item) => (
                <li key={item.label} className="flex items-center gap-2 text-[11px] font-bold text-slate-600">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ background: item.color }}
                    aria-hidden
                  />
                  {item.label}
                </li>
              ))}
            </ul>
          </div>
          {/* Focus badge */}
          {focus && !selected ? (
            <button
              type="button"
              onClick={() => navigate({ name: 'asset', code: focus.external_code })}
              className="attention-ring absolute right-4 top-4 z-[500] rounded-xl border border-sky-500/40 bg-panel/95 px-3 py-2 text-left text-sky-600 shadow-xl backdrop-blur transition hover:border-sky-400"
              aria-label={`Open focus asset ${focus.external_code}`}
            >
              <span className="block text-[10px] font-bold tracking-widest text-sky-600">FOCUS ASSET</span>
              <span className="block font-mono text-sm font-extrabold text-slate-900">{focus.external_code}</span>
            </button>
          ) : null}
        </div>
      </Card>

      {/* Area intelligence panel */}
      <Card className="p-4 xl:col-span-1">
        <h3 className="text-sm font-extrabold tracking-tight text-slate-900">Nearby assets</h3>
        <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Search radius">
          {RADII_KM.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRadiusKm(r)}
              aria-pressed={radiusKm === r}
              className={`rounded-full border px-2.5 py-1 text-xs font-bold transition ${
                radiusKm === r
                  ? 'border-sky-500/60 bg-sky-500/15 text-slate-900'
                  : 'border-edge bg-panel text-slate-500 hover:text-slate-900'
              }`}
            >
              {r} km
            </button>
          ))}
          <button
            type="button"
            onClick={() => setRadiusKm(null)}
            aria-pressed={radiusKm === null}
            className={`rounded-full border px-2.5 py-1 text-xs font-bold transition ${
              radiusKm === null
                ? 'border-sky-500/60 bg-sky-500/15 text-slate-900'
                : 'border-edge bg-panel text-slate-500 hover:text-slate-900'
            }`}
          >
            All
          </button>
        </div>

        <h3 className="mt-4 text-sm font-extrabold tracking-tight text-slate-900">Risk Level</h3>
        <div className="mt-2 space-y-1.5" role="group" aria-label="Risk level filter">
          {RISK_BANDS.map((b) => (
            <label key={b} className="flex cursor-pointer items-center gap-2 text-xs font-semibold text-slate-600">
              <input
                type="checkbox"
                checked={bands[b]}
                onChange={() => setBands((prev) => ({ ...prev, [b]: !prev[b] }))}
                className="h-3.5 w-3.5 accent-sky-600"
              />
              {b.charAt(0) + b.slice(1).toLowerCase()}
            </label>
          ))}
        </div>

        <h3 className="mt-4 text-sm font-extrabold tracking-tight text-slate-900">Area summary</h3>
        {!selected ? (
          <p className="mt-2 text-xs leading-relaxed text-slate-500">
            Search a location or use your current position to see nearby-asset intelligence.
          </p>
        ) : !summary || summary.total === 0 ? (
          <p className="mt-2 text-xs leading-relaxed text-slate-500" role="status">
            No SilentSignal assets found within the selected radius.
          </p>
        ) : (
          <div className="mt-2" role="status" aria-label={`Area risk summary for ${selected.name}`}>
            <p className="text-[11px] font-bold tracking-widest text-slate-500 uppercase">{selected.name}</p>
            <dl className="mt-1 space-y-1 text-xs">
              <div className="flex justify-between">
                <dt className="text-slate-500">Assets nearby</dt>
                <dd className="tnum font-extrabold text-slate-900">{summary.total}</dd>
              </div>
              {(Object.keys(summary.byBand) as RiskBand[]).map((b) => (
                <div key={b} className="flex justify-between">
                  <dt className="text-slate-500">{b.charAt(0) + b.slice(1).toLowerCase()}</dt>
                  <dd className="tnum font-bold text-slate-900">{summary.byBand[b]}</dd>
                </div>
              ))}
              <div className="flex justify-between border-t border-edge-soft pt-1">
                <dt className="font-bold text-slate-600">Overall risk</dt>
                <dd className="font-extrabold text-slate-900">{summary.overall}</dd>
              </div>
              {summary.score !== null ? (
                <div className="flex justify-between">
                  <dt className="font-bold text-slate-600">Risk score</dt>
                  <dd className="tnum font-extrabold text-slate-900">{summary.score} / 100</dd>
                </div>
              ) : null}
            </dl>
          </div>
        )}
      </Card>
      </div>
      <p className="text-xs text-slate-600">
        {plotted.length} of {assets.length} assets plotted · coordinates from the documented
        municipal street grid (schematic ward layout, OpenStreetMap context) · click any marker for details.
      </p>
    </div>
  );
}

function MapHeading({ count }: { count: number }): ReactNode {
  return (
    <div>
      <p className="text-[11px] font-bold tracking-[0.22em] text-sky-600">FLEET GEOGRAPHY</p>
      <h2 className="mt-1 text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
        Infrastructure Map
      </h2>
      <p className="mt-1 max-w-2xl text-sm text-slate-500">
        {count > 0
          ? `${count} streetlights plotted live from GET /api/map — colored by live fusion status.`
          : 'Streetlights plotted live from GET /api/map — colored by live fusion status.'}
      </p>
    </div>
  );
}
