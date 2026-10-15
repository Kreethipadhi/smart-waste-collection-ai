import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Bell, Bot, Check, ChevronRight, CircleAlert, Clock3, MapPin, Navigation, Play, Recycle, Route, Search, Sparkles, Truck, Waves, X } from 'lucide-react';
import { ApiError, apiJson, apiRequest } from './api';
import './styles.css';

type Bin = {
  id:string;
  zone:string;
  type:'General'|'Recyclable'|'Organic';
  fill:number;
  predicted:number;
  status:'Critical'|'High'|'Watch'|'Normal';
  sensor:string;
  x:number;
  y:number;
  reason:string;
};

type Vehicle = {
  id:string;
  type:string;
  capacity:number;
  load:number;
  status:'Available'|'Active'|'Maintenance';
  location:string;
};

const nav = ['Command center','Smart bins','Live waste map','Collection priority','Forecasting','Vehicle management','Route optimization','Collection tracking','Recycling analytics','Sensor alerts','AI operations center','Reports'];
const agentCatalog = [
 {name:'Smart Bin Monitoring Agent', short:'Sensor validation & bin health', status:'Live', purpose:'Collects smart-bin data, validates readings, flags missing or stale sensors, and maintains the live state of every waste container.', inputs:['Fill %, weight, timestamp, location', 'Waste type, sensor ID, capacity'], outputs:['Healthy / stale / verification_required state', 'Operational bin alerts'], color:'a0'},
 {name:'Waste Generation Forecasting Agent', short:'Predictive fill-level modeling', status:'Forecasting', purpose:'Analyzes historical bin trends and forecasts future overflow risk before the next collection cycle.', inputs:['Historical fill-level readings', 'Recent growth rate and sensor history'], outputs:['Predicted fill %, hours to threshold', 'Overflow-risk explanation'], color:'a1'},
 {name:'Collection Priority Agent', short:'Dynamic prioritization engine', status:'Active', purpose:'Combines current and forecast data to rank bins by urgency and explain why they require action.', inputs:['Live fill %, forecast result', 'Priority threshold and sensor condition'], outputs:['Priority level and rationale', 'Why this bin was selected'], color:'a2'},
 {name:'Vehicle Coordination Agent', short:'Fleet capacity matching', status:'Ready', purpose:'Checks fleet availability, remaining vehicle capacity, and waste compatibility before assignments are approved.', inputs:['Vehicle load, capacity, location', 'Supported waste streams and status'], outputs:['Eligible vehicles list', 'Capacity validation result'], color:'a3'},
 {name:'Route Optimization Agent', short:'Capacity-constrained routing', status:'Optimized', purpose:'Builds efficient collection routes by sequencing stops, respecting capacity and waste restrictions, and minimizing travel distance.', inputs:['Priority bins, coordinates, vehicle location', 'Waste stream and route constraints'], outputs:['Route plan, stop order, distance estimate', 'Alternative route options'], color:'a4'},
 {name:'Recycling & Waste Segregation Agent', short:'Segregation analysis', status:'Tracking', purpose:'Measures recyclable, organic, and general waste streams and detects contamination or poor segregation performance.', inputs:['Collected waste categories and amounts', 'Recycling and contamination records'], outputs:['Recycling rate, contamination rate', 'Segregation insights'], color:'a5'},
 {name:'Operations Reviewer / Critic Agent', short:'Feasibility and safety review', status:'Auditing', purpose:'Validates route feasibility, duplicate assignments, incompatibilities, and unsupported recommendations before human approval.', inputs:['Planned routes and assignments', 'Capacity and compatibility checks'], outputs:['Reviewer feedback and safety flags', 'Route approval readiness'], color:'a6'},
 {name:'Waste Operations & Action Planning Agent', short:'Human-in-the-loop orchestration', status:'Pending approval', purpose:'Coordinates every agent, assembles the operational plan, and prepares the final collection decision for operator review.', inputs:['Priority results, routes, reviewer feedback', 'Fleet and recycling information'], outputs:['Action plan, workflow trace', 'Human-approved dispatch state'], color:'a7'},
];

function clamp(value:number, min:number, max:number){ return Math.min(Math.max(value, min), max); }

function mapPoint(value:number, min:number, max:number, rangeMin:number, rangeMax:number){
  if (!Number.isFinite(value)) return rangeMin;
  const spread = max - min || 1;
  const ratio = (value - min) / spread;
  return clamp(rangeMin + ratio * (rangeMax - rangeMin), rangeMin, rangeMax);
}

function tone(status:string) { return status==='Critical'?'red':status==='High'?'amber':status==='Watch'?'blue':'green'; }

function App(){
  const [bins, setBins] = useState<Bin[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [page, setPage] = useState('Command center');
  const [planning, setPlanning] = useState(false);
  const [toast, setToast] = useState('');
  const [selected, setSelected] = useState<Bin | null>(null);
  const [workflow, setWorkflow] = useState<any>(null);
  const [routes, setRoutes] = useState<any[]>([]);
  const [recycling, setRecycling] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [authUser, setAuthUser] = useState<{username:string;role:string} | null>(null);
  const [loginForm, setLoginForm] = useState({ username:'', password:'' });
  const [loginError, setLoginError] = useState('');
  const [apiError, setApiError] = useState('');
  const [loadingData, setLoadingData] = useState(false);
  const [binForm, setBinForm] = useState({ id:'', zone:'', waste_type:'general', latitude:'19.076', longitude:'72.877', capacity_liters:'1000', fill_percent:'0', threshold_percent:'85', sensor_id:'' });
  const [sensorForm, setSensorForm] = useState({ bin_id:'BIN-001', fill_percent:'' });

  const refreshData = async (token = authToken) => {
    if (!token) return;
    setLoadingData(true);
    setApiError('');
    try {
      const [binsRes, vehiclesRes, routesRes, recyclingRes, eventsRes] = await Promise.all([
        apiJson<any[]>('/api/bins', {}, token),
        apiJson<any[]>('/api/vehicles', {}, token),
        apiJson<any[]>('/api/routes', {}, token),
        apiJson<any>('/api/recycling/analytics', {}, token),
        apiJson<any[]>('/api/events', {}, token)
      ]);
      const presetCoordinates: Record<string, [number, number]> = {
        'BIN-001':[18,28], 'BIN-003':[34,38], 'BIN-004':[72,20], 'BIN-006':[41,68], 'BIN-008':[77,66]
      };
      setBins(binsRes.map((item:any) => {
        const preset = presetCoordinates[item.id];
        const fill = Number(item.fill_percent ?? 0);
        const threshold = Number(item.threshold_percent ?? 85);
        return {
          id:item.id,
          zone:item.zone,
          type:item.waste_type === 'recyclable' ? 'Recyclable' : item.waste_type === 'organic' ? 'Organic' : 'General',
          fill:Math.round(fill),
          predicted:Math.round(fill),
          status:fill >= 95 ? 'Critical' : fill >= threshold ? 'High' : fill >= 70 ? 'Watch' : 'Normal',
          sensor:item.sensor_status === 'healthy' ? 'Healthy' : item.sensor_status,
          x:preset?.[0] ?? mapPoint(Number(item.latitude), 18.9, 19.2, 12, 88),
          y:preset?.[1] ?? mapPoint(Number(item.longitude), 72.5, 73.3, 12, 88),
          reason:'Run route optimization to calculate current forecast and priority.'
        } as Bin;
      }));
      setVehicles(vehiclesRes.map((item:any) => ({
        id:item.id,
        type:Array.isArray(item.supported_waste) ? item.supported_waste.join(' / ') : 'General',
        capacity:item.capacity_liters ?? 0,
        load:item.current_load_liters ?? 0,
        status:item.status === 'maintenance' ? 'Maintenance' : item.status === 'available' ? 'Available' : 'Active',
        location:'Operational zone'
      } as Vehicle)));
      setRoutes(routesRes);
      setRecycling(recyclingRes);
      setEvents(eventsRes);
    } catch (error) {
      setBins([]);
      setVehicles([]);
      setRoutes([]);
      setRecycling(null);
      setEvents([]);
      const message = error instanceof Error ? error.message : 'Could not load application data.';
      setApiError(message);
      if (error instanceof ApiError && error.status === 401) {
        setAuthToken(null);
        setAuthUser(null);
      }
    } finally {
      setLoadingData(false);
    }
  };

  useEffect(() => { if (authToken) void refreshData(authToken); }, [authToken]);

  const candidates = useMemo(() => bins.filter(b => b.status === 'Critical' || b.status === 'High'), [bins]);
  const critical = bins.filter(b => b.status === 'Critical').length;
  const healthySensors = bins.filter(bin => bin.sensor === 'Healthy').length;
  const activeAlerts = bins.filter(bin => bin.sensor !== 'Healthy' || bin.status === 'Critical').length;
  const currentRoutes = workflow?.routes ?? routes;
  const displayedRoute = currentRoutes[0];
  const displayedVehicle = vehicles.find(vehicle => vehicle.id === displayedRoute?.vehicle_id);
  const lastRecordedWorkflowId = events.find(event => event.workflow_id !== 'recycling' && event.workflow_id !== 'report')?.workflow_id;
  const recordedWorkflowEvents = events.filter(event => event.workflow_id === lastRecordedWorkflowId);
  const displayedEvents = workflow?.events?.length ? workflow.events : recordedWorkflowEvents;
  const today = new Intl.DateTimeFormat('en-GB', { weekday:'long', day:'2-digit', month:'long', year:'numeric' }).format(new Date()).toUpperCase();

  const showToast = (message: string) => {
    setToast(message);
    setTimeout(() => setToast(''), 2800);
  };

  const handleApiError = (error:unknown, fallback:string) => {
    if (error instanceof ApiError && error.status === 401) {
      setAuthToken(null);
      setAuthUser(null);
      return;
    }
    showToast(error instanceof Error ? error.message : fallback);
  };

  const submitLogin = async (event:React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoginError('');
    try {
      const result = await apiJson<any>('/api/auth/login', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(loginForm)
      });
      setAuthUser({username:result.username,role:result.role});
      setLoadingData(true);
      setAuthToken(result.access_token);
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Sign-in failed. Check the backend and credentials.');
    }
  };

  const logout = () => {
    setAuthToken(null);
    setAuthUser(null);
    setBins([]);
    setVehicles([]);
    setRoutes([]);
    setEvents([]);
    setRecycling(null);
    setWorkflow(null);
  };

  const plan = async () => {
    setPlanning(true);
    try {
      const result = await apiJson<any>('/api/orchestrate', { method:'POST' }, authToken ?? undefined);
      setWorkflow(result);
      setRoutes(result.routes);
      setBins(current => current.map(bin => {
        const decision = result.priorities.find((item:any) => item.bin_id === bin.id);
        if (!decision) return bin;
        const priority = decision.priority;
        return {
          ...bin,
          predicted:Math.round(decision.forecast.predicted_percent),
          status:priority === 'critical' ? 'Critical' : priority === 'high' ? 'High' : priority === 'watch' ? 'Watch' : 'Normal',
          reason:decision.explanation
        };
      }));
      const routeEvent = result.events.find((event:any) => event.stage === 'route_optimization');
      const unassigned = routeEvent?.output?.unassigned_bin_ids ?? [];
      showToast(`${result.routes.length} route(s) planned${unassigned.length ? `; ${unassigned.length} bin(s) lack a feasible vehicle` : ''}`);
    } catch (error) {
      handleApiError(error, 'Route planning failed. Confirm the backend is running, then retry.');
    } finally {
      setPlanning(false);
    }
  };

  const approveRoute = async (routeId:string) => {
    try {
      await apiJson(`/api/routes/${routeId}/approval`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ approved:true, comment:'Approved from operations dashboard' })
      }, authToken ?? undefined);
      const dispatchBody = await apiJson<any>(`/api/routes/${routeId}/start`, { method:'POST' }, authToken ?? undefined);
      setRoutes(current => current.map(route => route.id === routeId ? dispatchBody : route));
      setWorkflow((current:any) => current ? {...current,routes:current.routes.map((route:any) => route.id === routeId ? dispatchBody : route)} : current);
      await refreshData();
      showToast(`${routeId} approved and dispatched`);
    } catch (error) {
      handleApiError(error, 'Route approval failed');
    }
  };

  const rejectRoute = async (routeId:string) => {
    try {
      const result = await apiJson<any>(`/api/routes/${routeId}/approval`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ approved:false, comment:'Rejected from operations dashboard' })
      }, authToken ?? undefined);
      setRoutes(current => current.map(route => route.id === routeId ? result.route : route));
      await refreshData();
      showToast(`${routeId} rejected; no vehicle was dispatched`);
    } catch (error) {
      handleApiError(error, 'Route rejection failed');
    }
  };

  const completeRoute = async (routeId:string) => {
    try {
      const body = await apiJson<any>(`/api/routes/${routeId}/complete`, { method:'POST' }, authToken ?? undefined);
      setRoutes(current => current.map(route => route.id === routeId ? body : route));
      setWorkflow((current:any) => current ? {...current,routes:current.routes.map((route:any) => route.id === routeId ? body : route)} : current);
      await refreshData();
      showToast(`${routeId} completed; bins and fleet status updated`);
    } catch (error) {
      handleApiError(error, 'Collection completion failed');
    }
  };

  const downloadReport = async () => {
    try {
      const response = await apiRequest('/api/reports/current.pdf', { method:'POST' }, authToken ?? undefined);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = 'ecoroute-report.pdf';
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      handleApiError(error, 'Could not generate report. Confirm the backend is running.');
    }
  };

  const registerBin = async (event:React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const payload = {
      ...binForm,
      latitude:Number(binForm.latitude), longitude:Number(binForm.longitude),
      capacity_liters:Number(binForm.capacity_liters), fill_percent:Number(binForm.fill_percent),
      threshold_percent:Number(binForm.threshold_percent), sensor_id:binForm.sensor_id || `S-${binForm.id}`
    };
    try {
      await apiJson('/api/bins', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) }, authToken ?? undefined);
      await refreshData();
      setBinForm({ id:'', zone:'', waste_type:'general', latitude:'19.076', longitude:'72.877', capacity_liters:'1000', fill_percent:'0', threshold_percent:'85', sensor_id:'' });
      showToast(`${payload.id} registered and saved`);
    } catch (error) {
      handleApiError(error, 'Bin registration failed');
    }
  };

  const submitSensorReading = async (event:React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      const body = await apiJson<any>('/api/sensors/ingest', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ bin_id:sensorForm.bin_id, fill_percent:Number(sensorForm.fill_percent), timestamp:new Date().toISOString() })
      }, authToken ?? undefined);
      await refreshData();
      showToast(body.validation === 'accepted' ? 'Reading accepted; live bin values updated' : 'Large jump flagged for sensor verification; fill was not changed');
    } catch (error) {
      handleApiError(error, 'Sensor reading failed');
    }
  };

  const renderPage = () => {
    switch (page) {
      case 'Smart bins':
        return (
          <section className="detail-page">
            <div className="card detail-card">
              <div className="card-head"><div><h2>Smart bins</h2><p>Live bin inventory and operational status</p></div><span className="live"><i/> {bins.length} ACTIVE</span></div>
              <form className="entry-form" onSubmit={registerBin}>
                <input aria-label="Bin ID" placeholder="Bin ID" required value={binForm.id} onChange={event => setBinForm({...binForm,id:event.target.value})}/>
                <input aria-label="Location or zone" placeholder="Location / zone" required value={binForm.zone} onChange={event => setBinForm({...binForm,zone:event.target.value})}/>
                <select aria-label="Waste type" value={binForm.waste_type} onChange={event => setBinForm({...binForm,waste_type:event.target.value})}><option value="general">General</option><option value="recyclable">Recyclable</option><option value="organic">Organic</option></select>
                <input aria-label="Capacity in liters" type="number" min="1" placeholder="Capacity (L)" required value={binForm.capacity_liters} onChange={event => setBinForm({...binForm,capacity_liters:event.target.value})}/>
                <input aria-label="Initial fill percent" type="number" min="0" max="100" placeholder="Fill %" required value={binForm.fill_percent} onChange={event => setBinForm({...binForm,fill_percent:event.target.value})}/>
                <input aria-label="Collection threshold percent" type="number" min="1" max="100" placeholder="Threshold %" required value={binForm.threshold_percent} onChange={event => setBinForm({...binForm,threshold_percent:event.target.value})}/>
                <input aria-label="Latitude" type="number" step="any" placeholder="Latitude" required value={binForm.latitude} onChange={event => setBinForm({...binForm,latitude:event.target.value})}/>
                <input aria-label="Longitude" type="number" step="any" placeholder="Longitude" required value={binForm.longitude} onChange={event => setBinForm({...binForm,longitude:event.target.value})}/>
                <input aria-label="Sensor ID" placeholder="Sensor ID (optional)" value={binForm.sensor_id} onChange={event => setBinForm({...binForm,sensor_id:event.target.value})}/>
                <button className="primary" type="submit">Register bin</button>
              </form>
              <div className="smart-bins-table">
                <div className="table-row header">
                  <span>Bin</span>
                  <span>Location</span>
                  <span>Waste</span>
                  <span>Fill</span>
                  <span>Sensor</span>
                  <span>Status</span>
                </div>
                {bins.map(bin => (
                  <div className="table-row" key={bin.id}>
                    <span>{bin.id}</span>
                    <span>{bin.zone}</span>
                    <span>{bin.type}</span>
                    <span>{bin.fill}%</span>
                    <span>{bin.sensor}</span>
                    <span className={'badge ' + tone(bin.status)}>{bin.status}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        );
      case 'Live waste map':
        return (
          <section className="detail-page">
            <div className="card detail-card map-detail">
              <div className="card-head"><div><h2>Live waste map</h2><p>Geospatial view of bins, critical zones, and active routes.</p></div><span className="live"><i/> LIVE</span></div>
              <div className="map large-map">
                <div className="road r1"/><div className="road r2"/><div className="road r3"/><div className="route-line"/><div className="depot"><Truck size={14}/> Depot</div>
                {bins.map(bin => <button key={bin.id} onClick={() => setSelected(bin)} className={'pin ' + tone(bin.status)} style={{ left: bin.x + '%', top: bin.y + '%' }}><span>{bin.fill}</span></button>)}
                <div className="map-legend"><span><i className="dot red"/>Critical</span><span><i className="dot amber"/>High</span><span><i className="dot blue"/>Watch</span></div>
              </div>
            </div>
            <div className="detail-grid">
              <div className="card detail-card">
                <div className="card-head"><div><h2>Bin status</h2><p>Current operational visibility</p></div></div>
                <div className="status-list">{bins.map(bin => <div className="status-row" key={bin.id}><div><b>{bin.id}</b><small>{bin.zone}</small></div><span className={'badge ' + tone(bin.status)}>{bin.status}</span><strong>{bin.fill}%</strong></div>)}</div>
              </div>
              <div className="card detail-card">
                <div className="card-head"><div><h2>Map insight</h2><p>Operational summary</p></div></div>
                <ul className="bullet-list"><li>Critical collection clusters are concentrated in Civic Square and North Campus.</li><li>Riverside Park is trending toward overflow before the next collection cycle.</li><li>One stale sensor is flagged for verification on Station Road.</li></ul>
              </div>
            </div>
          </section>
        );
      case 'Collection priority':
        return (
          <section className="detail-page">
            <div className="card detail-card">
              <div className="card-head"><div><h2>Collection priority</h2><p>Bins ranked by current fill and predictive overflow risk.</p></div></div>
              <div className="priority-list">{bins.map(bin => <div className="priority-row" key={bin.id}><div className="row-head"><span className={'badge ' + tone(bin.status)}>{bin.status}</span><b>{bin.id}</b></div><div className="priority-body"><div><label>Zone</label><p>{bin.zone}</p></div><div><label>Current</label><p>{bin.fill}%</p></div><div><label>Forecast</label><p>{bin.predicted}%</p></div><div><label>Reason</label><p>{bin.reason}</p></div></div></div>)}</div>
            </div>
          </section>
        );
      case 'Forecasting':
        return (
          <section className="detail-page">
            <div className="card detail-card">
              <div className="card-head"><div><h2>Fill-level forecasting</h2><p>Model-driven prediction of threshold crossings.</p></div><span className="live"><i/> ML</span></div>
              <div className="forecast-table">
                <div className="forecast-row header"><span>Bin</span><span>Now</span><span>Forecast</span><span>Trend</span><span>Risk</span></div>
                {bins.map(bin => <div className="forecast-row" key={bin.id}><span>{bin.id}</span><span>{bin.fill}%</span><span>{bin.predicted}%</span><span>{Math.max(0, bin.predicted - bin.fill)} pts</span><span className={'badge ' + tone(bin.status)}>{bin.status}</span></div>)}
              </div>
            </div>
          </section>
        );
      case 'Vehicle management':
        return (
          <section className="detail-page">
            <div className="detail-grid">
              <div className="card detail-card">
                <div className="card-head"><div><h2>Fleet availability</h2><p>Vehicle readiness and capacity profile.</p></div></div>
                <div className="vehicle-list">{vehicles.map(vehicle => <div className="vehicle-row" key={vehicle.id}><div className="row-head"><b>{vehicle.id}</b><span className={vehicle.status === 'Available' ? 'badge green' : vehicle.status === 'Active' ? 'badge amber' : 'badge blue'}>{vehicle.status}</span></div><div className="vehicle-meta"><span>{vehicle.type}</span><span>{vehicle.location}</span><span>{vehicle.load} / {vehicle.capacity} L</span></div></div>)}</div>
              </div>
              <div className="card detail-card">
                <div className="card-head"><div><h2>Capacity checks</h2><p>Safety validation reminders</p></div></div>
                <ul className="bullet-list"><li>TRUCK-01 remains feasible for general and recyclable waste after the current route estimate.</li><li>TRUCK-02 is reserved for organic waste collection only.</li><li>TRUCK-03 is under maintenance and excluded from active dispatch.</li></ul>
              </div>
            </div>
          </section>
        );
      case 'Route optimization':
        return (
          <section className="detail-page">
            <div className="detail-grid">
              <div className="card detail-card">
                    <div className="card-head"><div><h2>Optimized routes</h2><p>Live plans grouped by compatible waste stream.</p></div></div>
                    {currentRoutes.length ? currentRoutes.map((route:any) => <div className="route-summary" key={route.id}>
                      <div className="summary-item"><label>Route / stream</label><strong>{route.id} · {route.waste_type}</strong></div>
                      <div className="summary-item"><label>Vehicle</label><strong>{route.vehicle_id}</strong></div>
                      <div className="summary-item"><label>Distance</label><strong>{route.estimated_distance_km} km</strong></div>
                      <div className="summary-item"><label>Stops / status</label><strong>{route.bin_ids.length} · {route.status}</strong></div>
                      {route.status === 'planned' && <><button className="primary" onClick={() => approveRoute(route.id)}><Check size={16}/> Approve & dispatch</button><button className="secondary" onClick={() => rejectRoute(route.id)}>Reject</button></>}
                    </div>) : <p>No route has been generated yet. Select Optimize routes to run the agents.</p>}
              </div>
              <div className="card detail-card">
                <div className="card-head"><div><h2>Route logic</h2><p>Priority, capacity and compatibility</p></div></div>
                    <ul className="bullet-list"><li>Each route contains one waste stream.</li><li>Stops are sequenced by nearest-neighbour distance from the assigned vehicle.</li><li>Insufficient capacity or incompatible vehicle types are reported as unassigned bins.</li></ul>
              </div>
            </div>
          </section>
        );
      case 'Collection tracking':
        return (
          <section className="detail-page">
            <div className="card detail-card">
              <div className="card-head"><div><h2>Collection tracking</h2><p>Operational lifecycle updates</p></div><span className="live"><i/> TRACKING</span></div>
              {routes.length ? <div className="track-list">{routes.map((route:any) => <div className="track-row" key={route.id}><span>{route.status}</span><strong>{route.id} · {route.vehicle_id} · {route.bin_ids.join(', ')}</strong>{route.status === 'planned' && <><button className="secondary" onClick={() => approveRoute(route.id)}>Approve & dispatch</button><button className="secondary" onClick={() => rejectRoute(route.id)}>Reject</button></>}{route.status === 'in_progress' && <button className="primary" onClick={() => completeRoute(route.id)}>Mark collection complete</button>}</div>)}</div> : <p>No saved routes yet. Generate a route plan first.</p>}
            </div>
          </section>
        );
      case 'Recycling analytics':
        return (
          <section className="detail-page">
            <div className="detail-grid">
              <div className="card detail-card">
                <div className="card-head"><div><h2>Recycling performance</h2><p>Deterministic KPI summary.</p></div></div>
                <div className="kpi-grid">
                  <div className="kpi-box"><span>Total collected volume</span><strong>{recycling?.total_collected_liters ?? 0} L</strong></div>
                  <div className="kpi-box"><span>Recyclable</span><strong>{recycling?.recyclable_liters ?? 0} L</strong></div>
                  <div className="kpi-box"><span>Organic</span><strong>{recycling?.organic_liters ?? 0} L</strong></div>
                  <div className="kpi-box"><span>General</span><strong>{recycling?.general_liters ?? 0} L</strong></div>
                  <div className="kpi-box large"><span>Recycling rate</span><strong>{recycling?.recycling_rate ?? 0}%</strong></div>
                </div>
              </div>
              <div className="card detail-card">
                <div className="card-head"><div><h2>Insights</h2><p>Segregation observation</p></div></div>
                <ul className="bullet-list"><li>{recycling?.insight ?? 'Recycling analytics are unavailable until the backend is connected.'}</li><li>Volumes are estimated from bin fill and capacity; measured waste weight is not recorded.</li><li>Contamination cannot be calculated without segregation inspection data.</li></ul>
              </div>
            </div>
          </section>
        );
      case 'Sensor alerts':
        return (
          <section className="detail-page">
            <div className="card detail-card">
              <div className="card-head"><div><h2>Sensor alerts</h2><p>Health status and anomaly tracking.</p></div><span className="live"><i/> {bins.filter(bin => bin.sensor !== 'Healthy' || bin.status === 'Critical').length} ACTIVE</span></div>
              <form className="entry-form sensor-form" onSubmit={submitSensorReading}>
                <select aria-label="Bin to update" value={sensorForm.bin_id} onChange={event => setSensorForm({...sensorForm,bin_id:event.target.value})}>{bins.map(bin => <option key={bin.id} value={bin.id}>{bin.id} · {bin.zone}</option>)}</select>
                <input aria-label="New sensor fill percentage" type="number" min="0" max="100" required placeholder="New fill %" value={sensorForm.fill_percent} onChange={event => setSensorForm({...sensorForm,fill_percent:event.target.value})}/>
                <button className="primary" type="submit">Submit reading</button>
              </form>
              <div className="alert-list">{bins.filter(bin => bin.sensor !== 'Healthy' || bin.status === 'Critical').map(bin => <div className="alert-row" key={bin.id}><div><b>{bin.id}</b><small>{bin.zone}</small></div><span className={'badge ' + (bin.sensor === 'Healthy' ? tone(bin.status) : 'red')}>{bin.sensor === 'Healthy' ? bin.status : bin.sensor.replaceAll('_',' ')}</span><strong>{bin.fill}%</strong></div>)}</div>
            </div>
          </section>
        );
      case 'AI operations center':
        return (
          <section className="agent-page">
            <div className="card agent-overview">
              <div className="card-head"><div><h2>AI operations center</h2><p>Multi-agent orchestration and execution visibility.</p></div><span className="live"><i/> 8 AGENTS</span></div>
              <div className="agent-grid">{agentCatalog.map(agent => <div className="agent-detail" key={agent.name}><div className="agent-header-row"><div className={'agent-icon ' + agent.color}><Bot size={15}/></div><div className="agent-title-wrap"><b>{agent.name}</b><small>{agent.short}</small></div><span className="agent-status">{agent.status}</span></div><p className="agent-purpose">{agent.purpose}</p><div className="agent-meta"><div><label>Inputs</label><ul>{agent.inputs.map(item => <li key={item}>{item}</li>)}</ul></div><div><label>Outputs</label><ul>{agent.outputs.map(item => <li key={item}>{item}</li>)}</ul></div></div></div>)}</div>
            </div>
            <div className="card detail-card">
              <div className="card-head"><div><h2>Latest agent execution evidence</h2><p>Inputs, outputs, and explanations from persisted runs.</p></div></div>
              {events.length ? events.map((event:any) => <details className="execution-event" key={event.id}><summary><b>{event.agent}</b> · {event.stage} · {event.status}</summary><p>{event.explanation}</p><pre>{JSON.stringify({input:event.input,output:event.output}, null, 2)}</pre></details>) : <p>No agent run has been recorded yet.</p>}
            </div>
          </section>
        );
      case 'Reports':
        return (
          <section className="detail-page">
            <div className="detail-grid">
              <div className="card detail-card">
                <div className="card-head"><div><h2>Operational report</h2><p>Structured operational snapshot.</p></div><button className="primary" onClick={downloadReport}>Download PDF</button></div>
                <div className="report-sections"><div className="report-item"><label>Reporting period</label><strong>{new Date().toLocaleDateString()}</strong></div><div className="report-item"><label>Smart-bin status</label><strong>{bins.length} registered · {critical} critical</strong></div><div className="report-item"><label>Vehicle utilization</label><strong>{vehicles.filter(v => v.status === 'Available').length} / {vehicles.length} available</strong></div><div className="report-item"><label>Recommendations</label><strong>{candidates.length ? candidates.map(bin => bin.id).join(', ') : 'No current collection candidates'}</strong></div></div>
              </div>
              <div className="card detail-card">
                <div className="card-head"><div><h2>Human-approved actions</h2><p>Current dispatch status.</p></div></div>
                {routes.length ? <ul className="bullet-list">{routes.map((route:any) => <li key={route.id}>{route.id} · {route.vehicle_id} · {route.status}{route.operator_comment ? ` · ${route.operator_comment}` : ''}</li>)}</ul> : <p>No human-reviewed route actions have been recorded.</p>}
              </div>
            </div>
          </section>
        );
      default:
        return (
          <section className="detail-page">
            <div className="card detail-card"><div className="card-head"><div><h2>Operations dashboard</h2><p>Overview of city-wide waste collection activity.</p></div></div></div>
          </section>
        );
    }
  };

  if (!authToken) {
    return (
      <main className="auth-screen">
        <form className="auth-panel" onSubmit={submitLogin}>
          <div className="brand-mark"><Recycle size={20}/></div>
          <p className="eyebrow">ECOROUTE OPERATIONS</p>
          <h1>Sign in</h1>
          <label>Username<input autoComplete="username" required value={loginForm.username} onChange={event => setLoginForm({...loginForm,username:event.target.value})}/></label>
          <label>Password<input type="password" autoComplete="current-password" required value={loginForm.password} onChange={event => setLoginForm({...loginForm,password:event.target.value})}/></label>
          {loginError && <p className="auth-error" role="alert">{loginError}</p>}
          <button className="primary" type="submit">Sign in to operations</button>
        </form>
      </main>
    );
  }

  return (
    <div className="shell">
      <aside>
        <div className="brand"><div className="brand-mark"><Recycle size={21}/></div><span>ecoroute</span></div>
        <div className="workspace"><span>OPERATIONS WORKSPACE</span><strong>Metro City <ChevronRight size={14}/></strong></div>
        <nav>{nav.map((n, i) => <button key={n} onClick={() => setPage(n)} className={page === n ? 'active' : ''}>{[<Waves />, <MapPin />, <CircleAlert />, <Sparkles />, <Truck />, <Recycle />, <Bell />, <Bot />, <Route />, <Route />, <Bot />, <Route />][i]}<span>{n}</span>{n === 'Sensor alerts' && <em>{activeAlerts}</em>}</button>)}</nav>
        <div className="side-bottom"><div className="user">{authUser?.username.slice(0,2).toUpperCase()}</div><div><b>{authUser?.username}</b><small>{authUser?.role}</small></div><button className="logout-btn" onClick={logout} aria-label="Sign out" title="Sign out"><X size={15}/></button></div>
      </aside>

      <main>
        <header>
          <div>
            <p className="eyebrow">{today}</p>
            <h1>{page}</h1>
            <p className="sub">A real-time view of city-wide collection operations.</p>
          </div>
          <div className="header-actions">
            <button className="icon"><Search size={19}/></button>
            <button className="icon notice"><Bell size={19}/><i/></button>
            <button className="simulate" onClick={() => setPage('Sensor alerts')}><Waves size={16}/> Submit sensor reading</button>
            <button className="primary" onClick={plan}>{planning ? <span className="spinner"/> : <Play size={16}/>} Optimize routes</button>
          </div>
        </header>

        {toast && <div className="toast"><Check size={17}/>{toast}</div>}
        {apiError && <div className="api-error" role="alert"><span>{apiError}</span><button className="secondary" onClick={() => void refreshData()}>Retry</button></div>}
        {loadingData && <p className="loading-state" role="status">Loading operational data...</p>}

        <section className="stats">
          <Stat label="Smart bins online" value={String(bins.length)} note={`${healthySensors} sensors reporting healthy`} icon={<Waves />} up />
          <Stat label="Require collection" value={String(candidates.length)} note={`${critical} require immediate action`} icon={<CircleAlert />} danger />
          <Stat label="Fleet available" value={`${vehicles.filter(v => v.status === 'Available').length} / ${vehicles.length}`} note={`${vehicles.filter(v => v.status === 'Active').length} active · ${vehicles.filter(v => v.status === 'Maintenance').length} maintenance`} icon={<Truck />} />
          <Stat label="Recycling rate" value={`${recycling?.recycling_rate ?? 0}%`} note={`${recycling?.total_collected_liters ?? 0} L recorded`} icon={<Recycle />} up />
        </section>

        {page === 'Command center' ? (
          <>
            <section className="grid">
              <div className="card map-card">
                <div className="card-head"><div><h2>Live collection map</h2><p>Priority bins, fleet positions & optimized routes</p></div><button className="text-btn" onClick={() => setPage('Live waste map')}>Open full map <ChevronRight size={15}/></button></div>
                <div className="map">
                  <div className="road r1"/><div className="road r2"/><div className="road r3"/><div className="route-line"/><div className="depot"><Truck size={14}/> Depot</div>
                  {bins.map(bin => <button key={bin.id} onClick={() => setSelected(bin)} className={'pin ' + tone(bin.status)} style={{ left: bin.x + '%', top: bin.y + '%' }}><span>{bin.fill}</span></button>)}
                  <div className="map-legend"><span><i className="dot red"/>Critical</span><span><i className="dot amber"/>High</span><span><i className="dot blue"/>Watch</span></div>
                </div>
              </div>

              <div className="card action-card">
                <div className="card-head"><div><h2>Action queue</h2><p>Requires operator review</p></div><span className="count">{candidates.length}</span></div>
                <div className="queue">{candidates.slice(0, 4).map(bin => <button onClick={() => setSelected(bin)} key={bin.id} className="queue-row"><span className={'severity ' + tone(bin.status)}></span><div><b>{bin.id}</b><small>{bin.zone} · {bin.type}</small></div><strong>{bin.fill}%</strong><ChevronRight size={17}/></button>)}</div>
                <button className="full-btn" onClick={() => setPage('Collection priority')}>Review all collection priorities</button>
              </div>
            </section>

            <section className="lower">
              <div className="card route-card">
                <div className="card-head"><div><h2>Proposed route <span className="route-id">{displayedRoute?.id || 'Not generated'}</span></h2><p>{displayedRoute ? `${displayedRoute.waste_type} stream · ${displayedRoute.estimated_distance_km} km · ~${displayedRoute.estimated_minutes} min` : 'Run route optimization to create a plan.'}</p></div><span className={displayedRoute?.status === 'in_progress' || displayedRoute?.status === 'verified' ? 'approved' : 'pending'}>{displayedRoute?.status || 'No plan'}</span></div>
                <div className="route-stops">{(displayedRoute?.bin_ids ?? []).map((id: string, index: number) => {
                  const bin = bins.find(item => item.id === id);
                  return <React.Fragment key={id}><div className="stop"><span>{index + 1}</span><div><b>{id}</b><small>{bin?.zone || 'Registered bin'}</small></div><strong>{bin?.fill ?? '—'}%</strong></div>{index < (displayedRoute?.bin_ids ?? []).length - 1 && <i className="connector" />}</React.Fragment>;
                })}{displayedRoute && <div className="stop truck-stop"><Truck size={18}/><div><b>{displayedRoute.vehicle_id}</b><small>Assigned vehicle · {displayedVehicle?.capacity ?? '—'} L capacity</small></div></div>}</div>
                <div className="route-footer"><div><span>Projected load</span><b>{displayedRoute?.estimated_load_liters ?? '—'} / {displayedVehicle?.capacity ?? '—'} L</b></div><div><span>Agent evidence</span><b className="green-text">{displayedEvents.length} workflow events</b></div>{displayedRoute?.status === 'planned' && <button className="primary" onClick={() => approveRoute(displayedRoute.id)}><Check size={16}/> Approve & dispatch</button>}{displayedRoute?.status === 'in_progress' && <button className="secondary" onClick={() => setPage('Collection tracking')}>Track route <Navigation size={15}/></button>}</div>
              </div>

              <div className="card agents">
                <div className="card-head"><div><h2>Agent activity</h2><p>Multi-agent workflow trace</p></div><span className="live"><i/> LIVE</span></div>
                {(workflow?.events?.length ? displayedEvents.slice(-4).reverse() : displayedEvents.slice(0,4)).map((event:any, index:number) => <div className="agent" key={event.id}><div className={'agent-icon a' + index}><Bot size={15}/></div><div><b>{event.agent}</b><small>{event.explanation}</small></div><time>{event.status}</time></div>)}
                {!displayedEvents.length && <p className="empty-state">Run route optimization to view agent execution evidence.</p>}
                <button className="full-btn" onClick={() => setPage('AI operations center')}>View agent execution log</button>
              </div>
            </section>
          </>
        ) : renderPage()}
      </main>

      {selected && <div className="drawer"><button className="close" onClick={() => setSelected(null)}><X size={18}/></button><p className="eyebrow">SMART BIN DETAIL</p><h2>{selected.id}</h2><span className={'badge ' + tone(selected.status)}>{selected.status} priority</span><div className="gauge"><b>{selected.fill}%</b><span>current fill level</span></div><dl><div><dt>Forecast (48h)</dt><dd>{selected.predicted}% <small>ML prediction</small></dd></div><div><dt>Waste stream</dt><dd>{selected.type}</dd></div><div><dt>Sensor health</dt><dd>{selected.sensor}</dd></div><div><dt>Why prioritized</dt><dd>{selected.reason}</dd></div></dl><button className="primary wide" onClick={() => { showToast(`${selected.id} added to route review`); setSelected(null); }}>Add to route review</button></div>}
    </div>
  );
}

function Stat({ label, value, note, icon, up, danger }: { label:string; value:string; note:string; icon:React.ReactNode; up?:boolean; danger?:boolean }) {
  return <div className="stat card"><div className={'stat-icon ' + (danger ? 'danger' : '')}>{icon}</div><p>{label}</p><h2>{value}</h2><small className={up ? 'positive' : danger ? 'negative' : ''}>{note}</small></div>;
}

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Missing root element');
const root = createRoot(rootElement);
root.render(<App />);
if (import.meta.hot) import.meta.hot.dispose(() => root.unmount());

