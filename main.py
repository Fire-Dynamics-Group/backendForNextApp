import contextlib

from fastapi import FastAPI, Response, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from fds import testFunction
try:
    from time_eq import compute_time_eq, derive_geometry, get_b_value
    from radiation import fillWordDoc
except ImportError as e:
    print(f"Warning: Optional modules not loaded: {e}")
try:
    from teq_reliability import compute_reliability, export_udf_batch, SteelParams, tlim_hours_for
except ImportError as e:
    print(f"Warning: teq_reliability not loaded: {e}")
from routers.fee_proposal import router as fee_proposal_router
from routers.efs import router as efs_router
from routers.cfd_dashboard import router as cfd_dashboard_router
from routers.smoke_layer import router as smoke_layer_router

_MCP_IMPORT_ERROR = None
try:
    from routers.mcp_server import build_mcp_asgi_app, mcp_lifespan
    _MCP_AVAILABLE = True
    print("MCP: loaded OK")
except Exception as e:  # noqa: BLE001 — want all import-time failures, not just ImportError
    import traceback
    _MCP_IMPORT_ERROR = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    print(f"MCP: import FAILED -> {_MCP_IMPORT_ERROR}")
    _MCP_AVAILABLE = False


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    if _MCP_AVAILABLE:
        async with mcp_lifespan(app):
            yield
    else:
        yield


app = FastAPI(lifespan=_lifespan) # create instance

if _MCP_AVAILABLE:
    app.mount("/mcp", build_mcp_asgi_app())


@app.get("/mcp-status")
def mcp_status():
    return {"available": _MCP_AVAILABLE, "import_error": _MCP_IMPORT_ERROR}


@app.get("/health")
async def health():
    """Deep health: API, Postgres, required tables, and the S3/MinIO bucket.

    Read by the daily sweep in ops/daily.py. `/docs` answering 200 says nothing
    about the database or the bucket, and every FD tool posts here - so this
    endpoint exists to make a dependency outage visible to monitoring instead
    of to users.

    Always returns 200 with a status field. A health check that 500s when a
    dependency is down cannot report *which* dependency is down.
    """
    from sqlalchemy import inspect, text

    from database import engine
    from services.health_service import REQUIRED_TABLES, build_health
    from services.s3_service import storage_available

    database = False
    database_error = None
    tables: dict[str, bool] = {}

    if engine is None:
        database_error = "DATABASE_URL is not configured"
    else:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                database = True
                names = set(
                    await conn.run_sync(
                        lambda sync_conn: inspect(sync_conn).get_table_names()
                    )
                )
                tables = {name: name in names for name in REQUIRED_TABLES}
        except Exception as e:  # noqa: BLE001 - report it, never raise it
            database_error = f"{type(e).__name__}: {e}"

    # storage_available() is documented never to raise.
    return build_health(
        database=database,
        tables=tables,
        storage=storage_available(),
        database_error=database_error,
        storage_error=None,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
    expose_headers=["Content-Disposition"],  # Allow frontend to read filename
)

app.include_router(fee_proposal_router, prefix="/fee-proposals", tags=["Fee Proposals"])
app.include_router(efs_router, prefix="/efs", tags=["External Fire Spread"])
app.include_router(cfd_dashboard_router, prefix="/cfd-dashboard", tags=["CFD Dashboard"])
app.include_router(smoke_layer_router, prefix="/smoke-layer", tags=["Warehouse Smoke Layer"])

try:
    from routers.projects import router as projects_router
    from routers.floors import router as floors_router
    app.include_router(projects_router, prefix="/projects", tags=["Projects"])
    app.include_router(floors_router, prefix="/projects", tags=["Floors"])
except (ImportError, ValueError) as e:
    print(f"Warning: Project/floor routers not loaded: {e}")
# aims:
# host this app 
# bring in all data from next js app
# use to run python scripts
class Point(BaseModel):
    x: float
    y: float

class Element(BaseModel):
    comments: str
    id: int
    points: List[Point]
    type: str
    zoneName: Optional[str] = None
    fsaDistance: Optional[float] = None

class ElementsData(BaseModel):
    elementList: List[Element]
    z: float
    wall_height: float
    wall_thickness: float
    stair_height: float
    px_per_m: float
    fire_floor: int
    total_floors: int
    stair_enclosure_roof_z: float
    scenario_type: Optional[str] = None
    sim_end_time: Optional[int] = 300
    include_sensors: Optional[bool] = True
    corridor_sensor_heights: Optional[List[float]] = [2.0]
    stair_sensor_heights: Optional[List[float]] = [0.5, 1.0, 1.5, 2.0]
    fsa_sensor_heights: Optional[List[float]] = [1.5]
    is_sprinklered: Optional[bool] = True
    door_leakages_enabled: Optional[bool] = True
    door_leakage_config: Optional[dict] = {}
    door_openings: Optional[dict] = {}
    door_roles: Optional[dict] = {}
    landing_roles: Optional[dict] = {}
    landing_up_side: Optional[str] = None
    obstruction_transparency: Optional[dict] = {}
    aov_mode: Optional[str] = "always_open"
    aov_activation_time: Optional[float] = None
    aov_type: Optional[str] = "hole"
    stair_style: Optional[str] = "overlapping"
    extract_config: Optional[dict] = {}
    inlet_config: Optional[dict] = {}
    zone_config: Optional[dict] = {}
    fire_hrr: Optional[float] = 1000.0
    fire_dimension: Optional[float] = 1.4
    fire_height_above_floor: Optional[float] = 0.5
    fire_base: Optional[float] = 0.0
    fire_type: Optional[str] = "growing"  # "growing" or "steady_state"
    fire_growth_rate: Optional[str] = "medium"  # "slow", "medium", "fast", "ultra_fast", "custom"
    fire_custom_alpha: Optional[float] = None
    slice_z_height: Optional[float] = 2.0

class ConvertedElement(BaseModel):
    id: int
    finalPoints: List[Point]
    comments: str

class TimeEqData(BaseModel):
    convertedPoints: List[ConvertedElement]
    roomComposition: List[str]
    openingHeights: List[float]
    isSprinklered: bool
    fireLoadDensity: float
    compartmentHeight: float
    tLim: float  
    fireResistancePeriod: float  



@app.get("/items/{item_id}")
async def read_item(item_id):
    return {"item_id": item_id}

@app.get("/users")
async def read_users():
    return ["Rick", "Morty"]
# TODO: change route from test
@app.post("/fds")
# async def read_elements(elements: List[Element]):
async def read_elements(body: ElementsData):
    import traceback
    try:
        return _read_elements_impl(body)
    except Exception as e:
        traceback.print_exc()
        raise

def _read_elements_impl(body: ElementsData):
    # LATER: should each obstruction and mesh -> send in cell_size and z1 & z2
    print("body: ",body)
    elements = [el.model_dump() for el in body.elementList]
    sensor_els = [e for e in elements if e.get("comments") == "sensorTree"]
    print(f"[FDS] sensorTree count: {len(sensor_els)}")
    for s in sensor_els[:3]:
        print(f"[FDS]   zoneName={s.get('zoneName')} keys={list(s.keys())}")
    z = body.z
    wall_height = body.wall_height 
    wall_thickness = body.wall_thickness # left as 0.2 for now
    stair_height = body.stair_height
    px_per_m = body.px_per_m
    fire_floor = body.fire_floor
    total_floors = body.total_floors
    stair_enclosure_roof_z = body.stair_enclosure_roof_z
    scenario_type = body.scenario_type
    sim_end_time = body.sim_end_time
    include_sensors = body.include_sensors
    corridor_sensor_heights = body.corridor_sensor_heights
    stair_sensor_heights = body.stair_sensor_heights
    fsa_sensor_heights = body.fsa_sensor_heights
    door_leakages_enabled = body.door_leakages_enabled
    door_leakage_config = body.door_leakage_config
    door_openings = body.door_openings
    door_roles = body.door_roles
    landing_roles = body.landing_roles
    landing_up_side = body.landing_up_side
    obstruction_transparency = body.obstruction_transparency
    aov_mode = body.aov_mode
    aov_activation_time = body.aov_activation_time
    aov_type = body.aov_type
    stair_style = body.stair_style
    extract_config = body.extract_config
    inlet_config = body.inlet_config
    zone_config = body.zone_config
    is_sprinklered = body.is_sprinklered
    fire_hrr = body.fire_hrr
    fire_dimension = body.fire_dimension
    fire_height_above_floor = body.fire_height_above_floor
    fire_base = body.fire_base
    fire_type = body.fire_type
    fire_growth_rate = body.fire_growth_rate
    fire_custom_alpha = body.fire_custom_alpha

    output = testFunction(
                            elements,
                            z,
                            wall_height,
                            wall_thickness,
                            stair_height,
                            px_per_m,
                            fire_floor,
                            total_floors,
                            stair_enclosure_roof_z,
                            scenario_type=scenario_type,
                            sim_end_time=sim_end_time,
                            door_openings=door_openings,
                            door_leakages_enabled=door_leakages_enabled,
                            door_leakage_config=door_leakage_config,
                            door_roles=door_roles,
                            landing_roles=landing_roles,
                            landing_up_side=landing_up_side,
                            obstruction_transparency=obstruction_transparency,
                            aov_mode=aov_mode,
                            aov_activation_time=aov_activation_time,
                            aov_type=aov_type,
                            stair_style=stair_style,
                            extract_config=extract_config,
                            inlet_config=inlet_config,
                            zone_config=zone_config,
                            is_sprinklered=is_sprinklered,
                            include_sensors=include_sensors,
                            corridor_sensor_heights=corridor_sensor_heights,
                            stair_sensor_heights=stair_sensor_heights,
                            fsa_sensor_heights=fsa_sensor_heights,
                            fire_hrr=fire_hrr,
                            fire_dimension=fire_dimension,
                            fire_height_above_floor=fire_height_above_floor,
                            fire_base=fire_base,
                            fire_type=fire_type,
                            fire_growth_rate=fire_growth_rate,
                            fire_custom_alpha=fire_custom_alpha,
                            slice_z_height=body.slice_z_height,
                            )
    print("output: ", output)
    return output

# mockConvertedPoints = [ConvertedElement(finalPoints=[Point(x=0.2, y=0.0), Point(x=0.2, y=5.2), Point(x=0.0, y=5.2), Point(x=0.0, y=5.8), Point(x=9.7, y=5.8), Point(x=9.7, y=5.6), Point(x=10.0, y=5.6), Point(x=10.0, y=2.4), Point(x=10.4, y=2.4), Point(x=10.4, y=0.1), Point(x=7.3, y=0.1), Point(x=7.3, y=0.0), Point(x=0.2, y=0.0)], comments='obstruction'), ConvertedElement(finalPoints=[Point(x=10.0, y=5.5), Point(x=10.0, y=4.2)], comments='opening'), ConvertedElement(finalPoints=[Point(x=10.4, y=2.4), Point(x=10.4, y=0.1)], comments='opening')]
mockConvertedPoints = [ConvertedElement(id=0, finalPoints=[Point(x=0.2, y=0.0), Point(x=0.2, y=5.2), Point(x=0.0, y=5.2), Point(x=0.0, y=5.8), Point(x=9.7, y=5.8), Point(x=9.7, y=5.6), Point(x=10.0, y=5.6), Point(x=10.0, y=2.4), Point(x=10.4, y=2.4), Point(x=10.4, y=0.1), Point(x=7.3, y=0.1), Point(x=7.3, y=0.0), Point(x=0.2, y=0.0)], comments='obstruction'), ConvertedElement(id=1, finalPoints=[Point(x=10.0, y=5.5), Point(x=10.0, y=4.2)], comments='opening'), ConvertedElement(id=2, finalPoints=[Point(x=10.4, y=2.4), Point(x=10.4, y=0.1)], comments='opening')]
@app.post("/timeEq",
    responses = {
        200: {
            "content": {"image/jpeg": {}}
        }
    },
    response_class=Response
          )
async def read_timeEq_elements(data: TimeEqData):
    
    convertedPoints = data.convertedPoints
    roomComposition = data.roomComposition
    openingHeights = data.openingHeights
    isSprinklered = data.isSprinklered
    fireLoadDensity = data.fireLoadDensity
    compartmentHeight = data.compartmentHeight
    tLim = data.tLim / 60
    fireResistancePeriod = data.fireResistancePeriod

    img_data = compute_time_eq(
        data=convertedPoints, 
        opening_heights=openingHeights, 
        room_composition=roomComposition, 
        is_sprinklered=isSprinklered, 
        fld=fireLoadDensity, 
        compartment_height=compartmentHeight, 
        t_lim=tLim,
        fire_resistance_period=fireResistancePeriod
        )

    return Response(content=img_data, media_type="image/jpeg")


class TimeEqReliabilityData(BaseModel):
    convertedPoints: List[ConvertedElement]
    occupancy: str
    compartmentHeight: float
    fireResistancePeriod: Optional[float] = None
    isSprinklered: bool = False
    # 10,000 sims: reliability repeatable to +/-0.5% (min-max envelope of repeat
    # runs) per the convergence study (scripts/convergence_out/), worst case across
    # occupancies; the cap matches — larger runs need job-based execution, not a
    # longer synchronous request.
    nSim: int = 10000
    # per-wall openable width (party/fire walls = 0); defaults to full wall lengths if omitted
    openableWidths: Optional[List[float]] = None
    roomComposition: Optional[List[str]] = None  # for derived b-value
    # overridable constants (None => default / derived)
    bValue: Optional[float] = None
    sectionFactor: Optional[float] = None
    criticalTemp: Optional[float] = None
    tLimMinutes: Optional[float] = None          # growth-rate override; default derives from occupancy (tlim_hours_for)
    combustionFactor: float = 0.8
    sprinklerFactor: float = 0.65
    # True: skip protection sizing; bare-steel EC3 heat transfer vs critical temp.
    unprotected: bool = False
    seed: Optional[int] = None
    # Charts endpoint only: include the per-sample QA table (one row per
    # simulation: fuel load, glazing breakage, opening factor, peak steel temp,
    # pass/fail) — the time-eq analogue of the full MACS+ report table.
    includeSamples: bool = False


@app.post("/timeEqReliability")
async def read_timeEq_reliability(data: TimeEqReliabilityData):
    """Monte Carlo time-equivalence reliability: probability that a steel member
    survives a realistic fire in this compartment. Protected mode (default) sizes
    insulation to the FR rating; unprotected mode steps bare-steel heat transfer
    against a member-specific critical temperature. Returns JSON."""
    from services.teq_reliability_run import (
        derived_geometry_echo,
        reliability_http_body,
        run_reliability_from_payload,
    )

    try:
        result = await run_in_threadpool(
            run_reliability_from_payload, data.model_dump(), n_sim_cap=10000,
        )
    except ValueError as e:  # e.g. unknown occupancy — client error, not server fault
        raise HTTPException(status_code=400, detail=str(e))
    body = reliability_http_body(result, unprotected=data.unprotected)
    body["derived"] = derived_geometry_echo(data.model_dump())
    return body


@app.post("/timeEqReliabilityCharts")
async def read_timeEq_reliability_charts(data: TimeEqReliabilityData):
    """The reliability run plus its two report charts (steel time-temperature
    spaghetti with the critical-temperature line, and the pass/fail scatter),
    PNG base64 in JSON. Send the ``seed`` echoed by /timeEqReliability to chart
    the exact run the user was shown; the numbers are recomputed from it."""
    import base64

    from services.teq_reliability_charts import render_reliability_charts
    from services.teq_reliability_run import (
        derived_geometry_echo,
        reliability_http_body,
        run_reliability_details_from_payload,
        samples_for_qa,
    )

    try:
        details = await run_in_threadpool(
            run_reliability_details_from_payload, data.model_dump(), n_sim_cap=10000,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    charts = await run_in_threadpool(render_reliability_charts, details)
    body = reliability_http_body(details.result, unprotected=data.unprotected)
    body["charts"] = {name: base64.b64encode(png).decode("ascii")
                      for name, png in charts.items()}
    body["derived"] = derived_geometry_echo(data.model_dump())
    if data.includeSamples:
        body["samples"] = samples_for_qa(details)
    return body


class TimeEqFireCurveData(BaseModel):
    convertedPoints: List[ConvertedElement]
    occupancy: str
    compartmentHeight: float
    isSprinklered: bool = False
    nSim: int = 10000
    openableWidths: Optional[List[float]] = None
    roomComposition: Optional[List[str]] = None
    bValue: Optional[float] = None
    tLimMinutes: Optional[float] = None
    combustionFactor: float = 0.8
    sprinklerFactor: float = 0.65
    seed: Optional[int] = None


@app.post("/timeEqFireCurves")
async def export_timeEq_fire_curves(data: TimeEqFireCurveData):
    """Sample N EC1 parametric fires (same path as /timeEqReliability) and return
    a zip of MACS+ AnalyseUDF curves plus a provenance manifest."""
    geo = derive_geometry(data.convertedPoints, data.compartmentHeight)
    vent_widths = data.openableWidths if data.openableWidths is not None else geo.wall_lengths
    vent_heights = [data.compartmentHeight] * len(vent_widths)

    params = SteelParams(t_lim_hours=tlim_hours_for(data.occupancy))
    if data.tLimMinutes is not None:
        params.t_lim_hours = data.tLimMinutes / 60.0
    if data.bValue is not None:
        params.thermal_inertia = data.bValue
    elif data.roomComposition:
        params.thermal_inertia = get_b_value(
            room_composition=data.roomComposition,
            room_dimensions=geo.room_dimensions, At=geo.At)

    try:
        zip_bytes = await run_in_threadpool(
            export_udf_batch,
            occupancy=data.occupancy, total_area=geo.At, floor_area=geo.floor_area,
            vent_widths=vent_widths, vent_heights=vent_heights,
            n_sim=min(max(data.nSim, 1), 10000),
            is_sprinklered=data.isSprinklered, combustion_factor=data.combustionFactor,
            sprinkler_factor=data.sprinklerFactor, params=params, seed=data.seed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=teq-udf-curves.zip"},
    )

    # roomUse: str,
    # floorMaterial: str,
    # ceilingMaterial: str
# class
class RadiationData(BaseModel):
    timeArray: List[float]
    accumulatedDistanceList: List[float]
    hobDistanceList: List[float]
    qList: List[float]
    timestepFEDList: List[float]
    accumulatedFEDList: List[float]
    totalHeatFlux: float
    walkingSpeed: float
    doorOpeningDuration: Optional[float] = None 
    docName: str

from fastapi.responses import StreamingResponse
@app.post("/radiation")
async def radiation_appendix(
    data: RadiationData
):
    timeArray = data.timeArray
    accumulatedDistanceList = data.accumulatedDistanceList
    hobDistanceList = data.hobDistanceList
    qList = data.qList
    timestepFEDList = data.timestepFEDList
    accumulatedFEDList = data.accumulatedFEDList
    totalHeatFlux = data.totalHeatFlux
    walkingSpeed = data.walkingSpeed
    doorOpeningDuration = data.doorOpeningDuration
    docName = data.docName

    output_filename = docName    
    print("output_filename: ", output_filename)
    bytes_io = fillWordDoc(
                            timeArray, 
                            accumulatedDistanceList, 
                            hobDistanceList, 
                            qList, 
                            timestepFEDList, 
                            accumulatedFEDList,
                            totalHeatFlux,
                            walkingSpeed,
                            doorOpeningDuration, # need to send null/undefined if not applicable
                            output_filename=output_filename         
                        )
  
    try:
        response = StreamingResponse(bytes_io, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        response.headers['Content-Disposition'] = f'attachment; filename="{output_filename}"'
        return response
        # return FileResponse(path=output_filename, media_type='application/octet-stream',filename=output_filename)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Could not read file")