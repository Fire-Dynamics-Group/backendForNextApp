from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from fds import testFunction
try:
    from time_eq import compute_time_eq
    from radiation import fillWordDoc
except ImportError as e:
    print(f"Warning: Optional modules not loaded: {e}")
from routers.fee_proposal import router as fee_proposal_router
from routers.efs import router as efs_router

app = FastAPI() # create instance

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
    stair_style: Optional[str] = "overlapping"
    extract_config: Optional[dict] = {}
    inlet_config: Optional[dict] = {}
    zone_config: Optional[dict] = {}

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
    # LATER: should each obstruction and mesh -> send in cell_size and z1 & z2 
    print("body: ",body)
    elements = body.elementList
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
    door_leakages_enabled = body.door_leakages_enabled
    door_leakage_config = body.door_leakage_config
    door_openings = body.door_openings
    door_roles = body.door_roles
    landing_roles = body.landing_roles
    landing_up_side = body.landing_up_side
    obstruction_transparency = body.obstruction_transparency
    aov_mode = body.aov_mode
    aov_activation_time = body.aov_activation_time
    stair_style = body.stair_style
    extract_config = body.extract_config
    inlet_config = body.inlet_config
    zone_config = body.zone_config
    is_sprinklered = body.is_sprinklered

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
                            stair_style=stair_style,
                            extract_config=extract_config,
                            inlet_config=inlet_config,
                            zone_config=zone_config,
                            is_sprinklered=is_sprinklered,
                            include_sensors=include_sensors,
                            corridor_sensor_heights=corridor_sensor_heights,
                            stair_sensor_heights=stair_sensor_heights,
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