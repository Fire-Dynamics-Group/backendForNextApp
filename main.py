from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pydantic import BaseModel

from script import testFunction
from time_eq import compute_time_eq

app = FastAPI() # create instance

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)
# aims:
# host this app 
# bring in all data from next js app
# use to run python scripts
class Point(BaseModel):
    x: float
    y: float

class Element(BaseModel):
    type: str
    points: List[Point]
    comments: str

class ConvertedElement(BaseModel):
    finalPoints: List[Point]
    comments: str

@app.get("/items/{item_id}")
async def read_item(item_id):
    return {"item_id": item_id}

@app.get("/users")
async def read_users():
    return ["Rick", "Morty"]

@app.post("/test")
async def read_elements(elements: List[Element]):
    # run simple script
    # later will have floor heights etc
    # print(elements[0].points[0].x)

    # # below to be obtained from post request
    # return elements
    z = 10
    wall_height = 2.5 
    wall_thickness = 0.2 
    stair_height = 30
    px_per_m = 33.6 

    output = testFunction(elements, z, wall_height, wall_thickness, stair_height, px_per_m)
    return output

mockConvertedPoints = [ConvertedElement(finalPoints=[Point(x=0.2, y=0.0), Point(x=0.2, y=5.2), Point(x=0.0, y=5.2), Point(x=0.0, y=5.8), Point(x=9.7, y=5.8), Point(x=9.7, y=5.6), Point(x=10.0, y=5.6), Point(x=10.0, y=2.4), Point(x=10.4, y=2.4), Point(x=10.4, y=0.1), Point(x=7.3, y=0.1), Point(x=7.3, y=0.0), Point(x=0.2, y=0.0)], comments='obstruction'), ConvertedElement(finalPoints=[Point(x=10.0, y=5.5), Point(x=10.0, y=4.2)], comments='opening'), ConvertedElement(finalPoints=[Point(x=10.4, y=2.4), Point(x=10.4, y=0.1)], comments='opening')]
@app.post("/timeEq")
# use == office; value = 511 i.e. 80% fractal
# material type: reinforced concrete = 1742
# possibly just access here?
async def read_timeEq_elements(
    convertedPoints: List[ConvertedElement], 
    # wallMaterials: List, 
    # roomUse: str, 
    # floorMaterial: str, 
    # ceilingMaterial: str
    ):
    compute_time_eq(convertedPoints)
    print(convertedPoints)
    return convertedPoints
