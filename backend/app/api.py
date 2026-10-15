from contextlib import asynccontextmanager
import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from .config import Settings
from .models import ApprovalRequest, Bin, LoginRequest, PriorityDecision, RouteStatus, SensorReading, WorkflowResult, utcnow
from .repository import Repository
from .agents import SmartBinMonitoringAgent, WasteOperationsAgent, RecyclingSegregationAgent
from .reporting import build_report
from .security import ACCESS_TOKEN_TTL, DUMMY_PASSWORD_HASH, TOKEN_ISSUER, create_access_token, verify_password

settings = Settings.from_environment()
repo = Repository(settings.database_url)
bearer = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        if settings.environment != 'production':
            repo.initialize_schema()
            if settings.seed_development_data:
                repo.seed()
            repo.check_connection()
        else:
            repo.check_connection(require_migrations=True)
    except Exception:
        raise RuntimeError('Database startup/readiness failed. Check DATABASE_URL connectivity and applied migrations; connection details are redacted.') from None
    try:
        yield
    finally:
        repo.dispose()


app=FastAPI(title='EcoRoute Multi-Agent Operations API',version='2.1.0',description='Auditable smart-waste orchestration service.',lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_origins),
    allow_credentials=False,
    allow_methods=['GET', 'POST', 'OPTIONS'],
    allow_headers=['Authorization', 'Content-Type'],
)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required', headers={'WWW-Authenticate': 'Bearer'})
    if not credentials:
        raise unauthorized
    try:
        claims = jwt.decode(credentials.credentials, settings.authentication_secret, algorithms=['HS256'], issuer=TOKEN_ISSUER)
        user_id = int(claims['sub'])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise unauthorized
    user = repo.user_by_id(user_id)
    if not user or not user['active']:
        raise unauthorized
    return user


def require_operator(user: dict = Depends(get_current_user)):
    if user['role'] not in {'admin', 'operator'}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Operator role required')
    return user

@app.get('/health')
def health(): return {'status':'healthy','agent_count':8,'api_version':app.version}
@app.get('/ready')
def readiness():
    try:
        repo.check_connection(require_migrations=settings.environment == 'production')
    except Exception:
        raise HTTPException(503, 'Database unavailable or schema migrations pending.') from None
    return {'status':'ready'}
@app.post('/api/auth/login')
def login(request: LoginRequest):
    user=repo.user(request.username.strip().lower())
    password_hash=user['password_hash'] if user else DUMMY_PASSWORD_HASH
    password_valid=verify_password(request.password,password_hash)
    if not user or not user['active'] or not password_valid:
        raise HTTPException(401, 'Invalid username or password', headers={'WWW-Authenticate': 'Bearer'})
    return {'access_token':create_access_token(user['id'], user['role'], settings),'token_type':'bearer','expires_in':int(ACCESS_TOKEN_TTL.total_seconds()),'username':user['username'],'role':user['role']}
@app.get('/api/auth/me')
def current_user(user: dict = Depends(get_current_user)):
    return {'id':user['id'],'username':user['username'],'role':user['role']}
@app.get('/api/bins')
def bins(_user: dict = Depends(get_current_user)): return repo.bins()
@app.post('/api/bins', status_code=201)
def register_bin(bin: Bin, user: dict = Depends(require_operator)):
    if repo.bin(bin.id): raise HTTPException(409, 'A bin with this ID is already registered')
    repo.save_bin(bin)
    repo.save_audit(user['id'], 'bin_registered', 'bin', bin.id, {'zone':bin.zone,'waste_type':bin.waste_type.value})
    return bin
@app.get('/api/vehicles')
def vehicles(_user: dict = Depends(get_current_user)): return repo.vehicles()
@app.get('/api/routes')
def routes(_user: dict = Depends(get_current_user)): return repo.routes()
@app.get('/api/events')
def events(_user: dict = Depends(get_current_user)): return repo.events()
@app.post('/api/sensors/ingest')
def ingest(reading: SensorReading, user: dict = Depends(require_operator)):
    context={'workflow_id':f'sensor-{reading.bin_id}','repo':repo,'events':[]}
    try: bin, verdict=SmartBinMonitoringAgent().ingest(context,reading)
    except ValueError as exc: raise HTTPException(404,str(exc))
    repo.save_audit(user['id'], 'sensor_reading_ingested', 'bin', bin.id, {'validation':verdict,'fill_percent':reading.fill_percent})
    return {'validation':verdict,'bin':bin,'events':context['events']}
@app.post('/api/orchestrate')
def orchestrate(user: dict = Depends(require_operator)):
    result=WasteOperationsAgent().orchestrate(repo)
    repo.save_audit(user['id'], 'workflow_orchestrated', 'workflow', result.workflow_id, {'route_count':len(result.routes)})
    return result
@app.post('/api/routes/{route_id}/approval')
def approve(route_id: str, request: ApprovalRequest, user: dict = Depends(require_operator)):
    route=repo.route(route_id)
    if not route: raise HTTPException(404,'Route not found')
    if route.status != RouteStatus.planned: raise HTTPException(409,'Only planned routes can be reviewed')
    route.status=RouteStatus.approved if request.approved else RouteStatus.rejected
    route.operator_comment=f"{user['username']}: {request.comment}"
    repo.save_route(route)
    decision='approved' if request.approved else 'rejected'
    repo.save_approval(route_id,user['id'],decision,request.comment)
    repo.save_audit(user['id'], f'route_{decision}', 'route', route_id, {'comment':request.comment})
    return {'route':route,'audit':{'operator':user['username'],'decision':decision,'comment':request.comment}}
@app.post('/api/routes/{route_id}/start')
def start(route_id: str, user: dict = Depends(require_operator)):
    route=repo.route(route_id)
    if not route: raise HTTPException(404,'Route not found')
    if route.status != RouteStatus.approved: raise HTTPException(409,'Route must be approved before starting')
    vehicle=next((vehicle for vehicle in repo.vehicles() if vehicle.id == route.vehicle_id), None)
    if not vehicle or vehicle.status != 'available': raise HTTPException(409,'Assigned vehicle is not available')
    vehicle.status='active'; repo.save_vehicle(vehicle)
    route.status=RouteStatus.in_progress; repo.save_route(route)
    repo.save_audit(user['id'],'route_started','route',route_id,{'vehicle_id':vehicle.id})
    return route
@app.post('/api/routes/{route_id}/complete')
def complete(route_id: str, user: dict = Depends(require_operator)):
    route=repo.route(route_id)
    if not route: raise HTTPException(404,'Route not found')
    if route.status != RouteStatus.in_progress: raise HTTPException(409,'Route must be in progress before completion')
    for bin_id in route.bin_ids:
        bin=repo.bin(bin_id)
        if bin:
            volume_liters=bin.capacity_liters * bin.fill_percent / 100
            repo.record_collection(route.id, bin.id, bin.waste_type.value, volume_liters)
            bin.fill_percent=0
            bin.last_collection=utcnow()
            repo.save_bin(bin)
    vehicle=next((vehicle for vehicle in repo.vehicles() if vehicle.id == route.vehicle_id), None)
    if vehicle:
        vehicle.current_load_liters=0
        vehicle.status='available'
        repo.save_vehicle(vehicle)
    route.status=RouteStatus.verified; repo.save_route(route)
    repo.save_audit(user['id'],'route_completed','route',route_id,{'bin_ids':route.bin_ids})
    return route
@app.get('/api/recycling/analytics')
def recycling(_user: dict = Depends(get_current_user)):
    context={'workflow_id':'recycling','repo':repo,'events':[],'record_events':False}; return RecyclingSegregationAgent().analyze(context)
@app.post('/api/reports/current.pdf')
def report(user: dict = Depends(require_operator)):
    history=repo.events()
    plan_event=next((event for event in history if event.stage == 'action_plan'),None)
    workflow_id=plan_event.workflow_id if plan_event else 'report-snapshot'
    workflow_events=[event for event in history if event.workflow_id == workflow_id]
    priorities=[]
    reviewer_feedback=[]
    if plan_event:
        priorities=[PriorityDecision.model_validate(event.output) for event in workflow_events if event.stage == 'prioritization']
        review_event=next((event for event in workflow_events if event.stage == 'feasibility_review'),None)
        reviewer_feedback=review_event.output.get('feedback',[]) if review_event else []
        planned_ids=plan_event.output.get('route_ids',[])
        routes_by_id={route.id:route for route in repo.routes()}
        report_routes=[routes_by_id[route_id] for route_id in planned_ids if route_id in routes_by_id]
        workflow_status=plan_event.status
    else:
        report_routes=[]
        workflow_status='no_plan'
    workflow=WorkflowResult(workflow_id=workflow_id,status=workflow_status,priorities=priorities,routes=report_routes,reviewer_feedback=reviewer_feedback,events=workflow_events)
    context={'workflow_id':'report','repo':repo,'events':[],'record_events':False}
    recycling=RecyclingSegregationAgent().analyze(context)
    repo.save_audit(user['id'],'report_generated','report',workflow.workflow_id,{'route_count':len(workflow.routes)})
    return Response(build_report(repo.bins(),workflow,recycling),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename=ecoroute-report.pdf'})
