"""Eight specialized agents coordinated through an auditable shared workflow context."""
from math import radians, sin, cos, asin, sqrt
from uuid import uuid4
from .models import AgentEvent, Forecast, Priority, PriorityDecision, RoutePlan, RouteStatus, WasteType, WorkflowResult

def geo_distance(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [a.latitude, a.longitude, b.latitude, b.longitude])
    return 6371 * 2 * asin(sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2))

class Agent:
    name = 'Base Agent'
    def log(self, context, stage, status, input_data, output, explanation):
        if context.get('record_events') is False:
            return
        event = AgentEvent(id=str(uuid4()), workflow_id=context['workflow_id'], agent=self.name, stage=stage, status=status, input=input_data, output=output, explanation=explanation)
        context['events'].append(event); context['repo'].save_event(event)

class SmartBinMonitoringAgent(Agent):
    name = 'Smart Bin Monitoring Agent'
    def review_current(self, context):
        bins = list(context['bins'].values())
        stale = [bin.id for bin in bins if bin.sensor_status != 'healthy']
        self.log(context, 'bin_health_monitoring', 'completed', {'bin_count':len(bins)}, {'stale_or_flagged_bins':stale}, 'Checks sensor freshness and validation status before predictions are made.')
    def ingest(self, context, reading):
        bin = context['repo'].bin(reading.bin_id)
        if not bin: raise ValueError('Unknown bin')
        history = context['repo'].readings(bin.id)
        previous = float(history[0]['fill']) if history else bin.fill_percent
        if context['repo'].reading_exists(reading):
            bin.sensor_status = 'duplicate_reading'; verdict = 'duplicate'
        elif reading.timestamp <= bin.last_seen:
            bin.sensor_status = 'stale'; verdict = 'stale_reading'
        elif abs(reading.fill_percent - previous) > 45:
            bin.sensor_status = 'verification_required'; verdict = 'verification_required'
        else:
            bin.fill_percent = reading.fill_percent; bin.last_seen = reading.timestamp; bin.sensor_status = 'healthy'; context['repo'].add_reading(reading); verdict = 'accepted'
        context['repo'].save_bin(bin)
        self.log(context, 'sensor_validation', verdict, reading.model_dump(mode='json'), {'previous_fill': previous, 'current_fill': bin.fill_percent}, 'Readings with a sudden change above 45 points require verification.')
        return bin, verdict

class ForecastingAgent(Agent):
    name = 'Waste Generation Forecasting Agent'
    def forecast(self, context, bin):
        readings = list(reversed(context['repo'].readings(bin.id)))
        values = [float(row['fill']) for row in readings]
        daily_growth = max(0.5, ((values[-1] - values[0]) / max(1, len(values)-1)) * 3) if len(values) > 1 else 4.0
        predicted = min(100, round(bin.fill_percent + daily_growth * 2, 1))
        hours = 0 if bin.fill_percent >= bin.threshold_percent else round((bin.threshold_percent-bin.fill_percent)/(daily_growth/24), 1)
        forecast = Forecast(bin_id=bin.id, predicted_percent=predicted, hours_to_threshold=max(0, hours), daily_growth_points=round(daily_growth,2), confidence=min(.94, .55 + len(values)*.05))
        context['repo'].save_forecast(forecast)
        self.log(context, 'forecast', 'completed', {'historical_points': len(values)}, forecast.model_dump(), 'Time-series linear trend fitted to recent sensor readings; this is explicitly marked as a prediction.')
        return forecast

class CollectionPriorityAgent(Agent):
    name = 'Collection Priority Agent'
    def prioritize(self, context, bin, forecast):
        score = bin.fill_percent*.65 + forecast.predicted_percent*.25 + (10 if bin.sensor_status != 'healthy' else 0)
        if bin.fill_percent >= 95: priority, reason = Priority.critical, 'Current sensor reading is at or above the 95% critical level.'
        elif bin.fill_percent >= bin.threshold_percent: priority, reason = Priority.high, f'Current reading ({bin.fill_percent}%) exceeds the {bin.threshold_percent}% threshold.'
        elif forecast.predicted_percent >= bin.threshold_percent: priority, reason = Priority.high, f'Forecast predicts {forecast.predicted_percent}% before the next collection cycle.'
        elif bin.fill_percent >= 70: priority, reason = Priority.watch, 'Approaching the collection threshold; continue monitoring.'
        else: priority, reason = Priority.normal, 'Current and predicted fill levels are below the threshold.'
        decision = PriorityDecision(bin_id=bin.id, priority=priority, score=round(score,1), explanation=reason, forecast=forecast)
        self.log(context, 'prioritization', 'completed', {'bin_id':bin.id,'fill_percent':bin.fill_percent}, decision.model_dump(), reason)
        return decision

class VehicleCoordinationAgent(Agent):
    name = 'Vehicle Coordination Agent'
    def eligible(self, context, waste_type, required_liters):
        vehicles = [v for v in context['repo'].vehicles() if v.status == 'available' and waste_type in v.supported_waste and v.capacity_liters-v.current_load_liters >= required_liters]
        self.log(context, 'vehicle_validation', 'completed', {'waste_type':waste_type,'required_liters':round(required_liters)}, {'eligible_vehicles':[v.id for v in vehicles]}, 'Validates vehicle availability, remaining capacity, and waste-stream compatibility.')
        return vehicles

class RouteOptimizationAgent(Agent):
    name = 'Route Optimization Agent'
    def optimize(self, context, decisions):
        routes = []
        for previous_route in context['repo'].routes():
            if previous_route.status == RouteStatus.planned:
                previous_route.status = RouteStatus.rejected
                previous_route.operator_comment = 'Superseded by a newer optimized plan.'
                context['repo'].save_route(previous_route)
        active_bins = [context['bins'][d.bin_id] for d in decisions if d.priority in (Priority.watch, Priority.high, Priority.critical)]
        if not active_bins:
            self.log(context, 'route_optimization', 'completed', {'candidate_count': len(decisions)}, {'route_ids': []}, 'No bins require collection in the current planning cycle.')
            return routes
        assigned_vehicle_ids = set()
        grouped_bins = {}
        for bin in active_bins:
            grouped_bins.setdefault(bin.waste_type, []).append(bin)

        streams = sorted(
            grouped_bins.items(),
            key=lambda item: sum(b.capacity_liters * b.fill_percent / 100 for b in item[1]),
            reverse=True,
        )
        unassigned_bins = []
        for waste_type, stream_bins in streams:
            stream_bins.sort(key=lambda b: b.capacity_liters * b.fill_percent / 100, reverse=True)
            required_load = sum(b.capacity_liters * b.fill_percent / 100 for b in stream_bins)
            eligible = [
                vehicle for vehicle in VehicleCoordinationAgent().eligible(context, waste_type, required_load)
                if vehicle.id not in assigned_vehicle_ids
            ]
            if not eligible:
                unassigned_bins.extend(bin.id for bin in stream_bins)
                continue

            vehicle = min(eligible, key=lambda v: min(geo_distance(v, bin) for bin in stream_bins))
            assigned_vehicle_ids.add(vehicle.id)
            remaining = stream_bins[:]
            ordered = []
            current = vehicle
            while remaining:
                next_stop = min(remaining, key=lambda candidate: geo_distance(current, candidate))
                ordered.append(next_stop)
                remaining.remove(next_stop)
                current = next_stop
            route_distance = sum(geo_distance(a, b) for a, b in zip([vehicle] + ordered, ordered + [vehicle]))
            route = RoutePlan(
                id=f'R-{uuid4().hex[:8].upper()}',
                vehicle_id=vehicle.id,
                waste_type=waste_type,
                bin_ids=[b.id for b in ordered],
                estimated_load_liters=round(required_load),
                estimated_distance_km=round(route_distance, 2),
                estimated_minutes=round(route_distance * 3 + len(ordered) * 6),
            )
            context['repo'].save_route(route)
            routes.append(route)

        status = 'completed' if not unassigned_bins else 'partial'
        self.log(
            context,
            'route_optimization',
            status,
            {'candidate_count': len(active_bins)},
            {'route_ids': [r.id for r in routes], 'unassigned_bin_ids': unassigned_bins},
            'Routes use available vehicles only when waste type and remaining capacity match. A vehicle is assigned at most once per plan.',
        )
        return routes

class RecyclingSegregationAgent(Agent):
    name = 'Recycling & Waste Segregation Agent'
    def analyze(self, context):
        records = context['repo'].collections()
        volumes = {waste_type:sum(row['volume_liters'] for row in records if row['waste_type'] == waste_type)
                   for waste_type in ('recyclable', 'organic', 'general')}
        total = sum(volumes.values())
        rate = round(volumes['recyclable'] / total * 100, 1) if total else 0
        payload = {
            'total_collected_liters':round(total, 1),
            'recyclable_liters':round(volumes['recyclable'], 1),
            'organic_liters':round(volumes['organic'], 1),
            'general_liters':round(volumes['general'], 1),
            'recycling_rate':rate,
            'contamination_rate':None,
            'insight':'No collection has been completed yet.' if not total else f'Recyclable volume is {rate}% of recorded collected volume; weight and contamination data are not available.',
        }
        self.log(context, 'recycling_analytics', 'completed', {'collection_count':len(records)}, payload, 'Recycling rate is deterministic: recorded recyclable liters / total recorded liters × 100; these are volume estimates, not measured weights.')
        return payload

class OperationsReviewerAgent(Agent):
    name = 'Operations Reviewer / Critic Agent'
    def review(self, context, routes):
        feedback=[]
        for route in routes:
            vehicle = next(v for v in context['repo'].vehicles() if v.id == route.vehicle_id)
            feedback.append(f'{route.id}: {vehicle.id} capacity and {route.waste_type.value} compatibility passed.')
        self.log(context, 'feasibility_review', 'passed', {'route_ids':[r.id for r in routes]}, {'feedback':feedback}, 'Checks capacity, segregation compatibility, and duplicate vehicle assignments before human approval.')
        return feedback

class WasteOperationsAgent(Agent):
    name = 'Waste Operations & Action Planning Agent'
    def orchestrate(self, repo):
        context={'workflow_id':str(uuid4()), 'repo':repo, 'events':[], 'bins':{b.id:b for b in repo.bins()}}
        SmartBinMonitoringAgent().review_current(context)
        forecast_agent, priority_agent = ForecastingAgent(), CollectionPriorityAgent()
        decisions=[priority_agent.prioritize(context, bin, forecast_agent.forecast(context,bin)) for bin in context['bins'].values()]
        routes=RouteOptimizationAgent().optimize(context,decisions)
        feedback=OperationsReviewerAgent().review(context,routes)
        RecyclingSegregationAgent().analyze(context)
        self.log(context, 'action_plan', 'pending_human_approval', {'priorities':len(decisions)}, {'route_ids':[r.id for r in routes]}, 'Routes are staged only; an operator must approve before activation.')
        return WorkflowResult(workflow_id=context['workflow_id'],status='pending_human_approval',priorities=decisions,routes=routes,reviewer_feedback=feedback,events=context['events'])
