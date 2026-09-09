import { createContext, useContext, type ReactNode } from 'react';
import { computeFleetStats, useFleet, type FleetState, type FleetStats } from './lib/fleet';

export const FleetContext = createContext<(FleetState & { stats: FleetStats }) | null>(null);

export function FleetProvider({ children }: { children: ReactNode }): ReactNode {
  const fleet = useFleet();
  const stats = computeFleetStats(fleet.entries, fleet.total);
  return <FleetContext.Provider value={{ ...fleet, stats }}>{children}</FleetContext.Provider>;
}

export function useFleetContext(): FleetState & { stats: FleetStats } {
  const ctx = useContext(FleetContext);
  if (!ctx) throw new Error('useFleetContext must be used inside FleetProvider');
  return ctx;
}
