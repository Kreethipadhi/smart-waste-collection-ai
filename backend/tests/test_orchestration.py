from datetime import timedelta
import pytest
from fastapi import HTTPException
from app import api
from app.repository import Repository
from app.agents import WasteOperationsAgent, SmartBinMonitoringAgent
from app.models import ApprovalRequest, Bin, Priority, RouteStatus, SensorReading, utcnow

def test_workflow_runs_all_agents(tmp_path):
    result=WasteOperationsAgent().orchestrate(Repository(str(tmp_path/'test.db'), initialize=True, seed_data=True))
    agents={event.agent for event in result.events}
    assert agents == {
        'Smart Bin Monitoring Agent', 'Waste Generation Forecasting Agent',
        'Collection Priority Agent', 'Vehicle Coordination Agent',
        'Route Optimization Agent', 'Recycling & Waste Segregation Agent',
        'Operations Reviewer / Critic Agent', 'Waste Operations & Action Planning Agent'
    }
    assert result.routes

def test_sensor_jump_requires_verification(tmp_path):
    repo=Repository(str(tmp_path/'test.db'), initialize=True, seed_data=True); context={'workflow_id':'test','repo':repo,'events':[]}
    _, status=SmartBinMonitoringAgent().ingest(context,SensorReading(bin_id='BIN-001',fill_percent=10))
    assert status == 'verification_required'


def test_duplicate_and_out_of_order_sensor_readings_are_not_applied(tmp_path):
    repo = Repository(str(tmp_path/'sensor-quality.db'), initialize=True, seed_data=True)
    context = {'workflow_id':'sensor-quality','repo':repo,'events':[]}
    first = SensorReading(bin_id='BIN-001',fill_percent=80,timestamp=utcnow()+timedelta(minutes=1))
    updated, accepted = SmartBinMonitoringAgent().ingest(context,first)
    duplicate_bin, duplicate = SmartBinMonitoringAgent().ingest(context,first)
    stale = first.model_copy(update={'fill_percent':95,'timestamp':updated.last_seen-timedelta(minutes=1)})
    stale_bin, stale_result = SmartBinMonitoringAgent().ingest(context,stale)

    assert accepted == 'accepted'
    assert duplicate == 'duplicate'
    assert duplicate_bin.fill_percent == 80
    assert stale_result == 'stale_reading'
    assert stale_bin.fill_percent == 80


def test_default_repository_uses_five_bins_and_full_route(tmp_path):
    repo = Repository(str(tmp_path/'test.db'), initialize=True, seed_data=True)
    bins = repo.bins()
    assert len(bins) == 5
    assert {bin.id for bin in bins} == {'BIN-001', 'BIN-003', 'BIN-004', 'BIN-006', 'BIN-008'}

    result = WasteOperationsAgent().orchestrate(repo)
    bins_by_id = {bin.id: bin for bin in bins}
    vehicles_by_id = {vehicle.id: vehicle for vehicle in repo.vehicles()}
    assert result.routes
    assert len({route.vehicle_id for route in result.routes}) == len(result.routes)
    for route in result.routes:
        vehicle = vehicles_by_id[route.vehicle_id]
        assert route.waste_type in vehicle.supported_waste
        assert route.estimated_load_liters <= vehicle.capacity_liters - vehicle.current_load_liters
        assert all(bins_by_id[bin_id].waste_type == route.waste_type for bin_id in route.bin_ids)


def test_route_planning_reports_bins_without_compatible_capacity(tmp_path):
    repo = Repository(str(tmp_path/'test.db'), initialize=True, seed_data=True)
    result = WasteOperationsAgent().orchestrate(repo)
    route_event = next(event for event in result.events if event.stage == 'route_optimization')

    assert route_event.status == 'partial'
    assert route_event.output['unassigned_bin_ids'] == ['BIN-003']


def test_registered_bins_survive_repository_restart(tmp_path):
    database = str(tmp_path/'test.db')
    repo = Repository(database, initialize=True, seed_data=True)
    repo.save_bin(repo.bins()[0].model_copy(update={'id': 'BIN-NEW', 'zone': 'New district'}))

    restarted_repo = Repository(database)

    assert restarted_repo.bin('BIN-NEW').zone == 'New district'
    assert len(restarted_repo.bins()) == 6


def test_bin_registration_api_rejects_duplicate_ids(tmp_path, monkeypatch):
    test_repo = Repository(str(tmp_path/'api.db'), initialize=True, seed_data=True)
    user_id = test_repo.create_user('test-operator', 'test-password-hash', 'admin')
    monkeypatch.setattr(api, 'repo', test_repo)
    bin = Bin(id='BIN-NEW', zone='New district', latitude=19.08, longitude=72.88,
              waste_type='general', capacity_liters=900, fill_percent=20)

    principal = {'id':user_id,'username':'test-operator','role':'admin'}
    assert api.register_bin(bin, principal) == bin
    with pytest.raises(HTTPException) as error:
        api.register_bin(bin, principal)
    assert error.value.status_code == 409


def test_collection_lifecycle_updates_bin_and_vehicle(tmp_path, monkeypatch):
    repo = Repository(str(tmp_path/'lifecycle.db'), initialize=True, seed_data=True)
    monkeypatch.setattr(api, 'repo', repo)
    user_id = repo.create_user('test-manager', 'test-password-hash', 'admin')
    principal = {'id':user_id,'username':'test-manager','role':'admin'}
    workflow = WasteOperationsAgent().orchestrate(repo)
    route = workflow.routes[0]

    api.approve(route.id, ApprovalRequest(approved=True, comment='Test operator approval'), principal)
    assert api.start(route.id, principal).status == RouteStatus.in_progress
    completed = api.complete(route.id, principal)

    assert completed.status == RouteStatus.verified
    assert all(repo.bin(bin_id).fill_percent == 0 for bin_id in route.bin_ids)
    vehicle = next(vehicle for vehicle in repo.vehicles() if vehicle.id == route.vehicle_id)
    assert vehicle.status == 'available'
    assert vehicle.current_load_liters == 0
    event_count = len(repo.events())
    analytics = api.recycling()
    assert analytics['total_collected_liters'] == round(route.estimated_load_liters, 1)
    assert analytics['recycling_rate'] == 0
    assert len(repo.events()) == event_count


def test_92_percent_fill_receives_high_priority(tmp_path):
    repo = Repository(str(tmp_path/'priority.db'), initialize=True, seed_data=True)
    result = WasteOperationsAgent().orchestrate(repo)
    decision = next(item for item in result.priorities if item.bin_id == 'BIN-001')

    assert repo.bin('BIN-001').fill_percent == 92
    assert decision.priority == Priority.high
    assert 'threshold' in decision.explanation


def test_forecast_crossing_threshold_becomes_candidate(tmp_path):
    repo = Repository(str(tmp_path/'forecast.db'), initialize=True, seed_data=True)
    result = WasteOperationsAgent().orchestrate(repo)
    decision = next(item for item in result.priorities if item.bin_id == 'BIN-006')

    assert repo.bin('BIN-006').fill_percent == 78
    assert decision.forecast.predicted_percent >= repo.bin('BIN-006').threshold_percent
    assert decision.priority == Priority.high
    assert repo.forecasts('BIN-006')


def test_new_critical_sensor_value_triggers_replanning(tmp_path):
    repo = Repository(str(tmp_path/'replan.db'), initialize=True, seed_data=True)
    new_bin = Bin(id='BIN-010', zone='South Gate', latitude=19.069, longitude=72.879,
                  waste_type='general', capacity_liters=700, fill_percent=62)
    repo.save_bin(new_bin)
    context = {'workflow_id':'replan','repo':repo,'events':[]}
    updated, validation = SmartBinMonitoringAgent().ingest(
        context, SensorReading(bin_id='BIN-010', fill_percent=95)
    )
    workflow = WasteOperationsAgent().orchestrate(repo)
    decision = next(item for item in workflow.priorities if item.bin_id == 'BIN-010')

    assert validation == 'accepted'
    assert updated.fill_percent == 95
    assert decision.priority == Priority.critical
    assert any('BIN-010' in route.bin_ids for route in workflow.routes)


def test_replanning_supersedes_only_unapproved_routes(tmp_path):
    repo = Repository(str(tmp_path/'supersede.db'), initialize=True, seed_data=True)
    first_plan = WasteOperationsAgent().orchestrate(repo)
    protected_route = first_plan.routes[0]
    protected_route.status = RouteStatus.approved
    repo.save_route(protected_route)

    second_plan = WasteOperationsAgent().orchestrate(repo)

    assert repo.route(protected_route.id).status == RouteStatus.approved
    for route in first_plan.routes[1:]:
        superseded = repo.route(route.id)
        assert superseded.status == RouteStatus.rejected
        assert 'Superseded' in superseded.operator_comment
    assert all(route.status == RouteStatus.planned for route in second_plan.routes)


def test_pdf_report_does_not_replan_or_change_saved_routes(tmp_path, monkeypatch):
    repo = Repository(str(tmp_path/'report.db'), initialize=True, seed_data=True)
    monkeypatch.setattr(api, 'repo', repo)
    user_id = repo.create_user('report-operator', 'test-password-hash', 'admin')
    principal = {'id':user_id,'username':'report-operator','role':'admin'}
    workflow = WasteOperationsAgent().orchestrate(repo)
    expected_routes = {route.id:route.status for route in repo.routes()}
    events_before = len(repo.events())

    response = api.report(principal)

    assert response.media_type == 'application/pdf'
    assert response.body.startswith(b'%PDF')
    assert {route.id:route.status for route in repo.routes()} == expected_routes
    assert len(repo.events()) == events_before
