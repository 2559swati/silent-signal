import { useState } from 'react';
import Shell from './components/Shell';
import Dashboard from './pages/Dashboard';
import Assets from './pages/Assets';
import AssetDetail from './pages/AssetDetail';
import RiskMonitor from './pages/RiskMonitor';
import Explanations from './pages/Explanations';
import Actions from './pages/Actions';
import Map from './pages/Map';
import Security from './pages/Security';
import Settings from './pages/Settings';
import { FleetProvider } from './state';
import { navigate, useRoute, useScrollTopOnRoute } from './lib/router';

function App(): React.JSX.Element {
  const route = useRoute();
  const [search, setSearch] = useState('');
  useScrollTopOnRoute(route);

  const handleSearch = (value: string): void => {
    setSearch(value);
    if (route.name !== 'assets' && route.name !== 'asset') {
      navigate({ name: 'assets' });
    }
  };

  return (
    <FleetProvider>
      <Shell route={route} onSearch={handleSearch} searchValue={search}>
        {route.name === 'dashboard' ? <Dashboard /> : null}
        {route.name === 'assets' ? <Assets query={search} /> : null}
        {route.name === 'asset' ? <AssetDetail code={route.code} /> : null}
        {route.name === 'risk' ? <RiskMonitor /> : null}
        {route.name === 'explanations' ? <Explanations /> : null}
        {route.name === 'actions' ? <Actions /> : null}
        {route.name === 'map' ? <Map /> : null}
        {route.name === 'security' ? <Security /> : null}
        {route.name === 'settings' ? <Settings /> : null}
      </Shell>
    </FleetProvider>
  );
}

export default App;
