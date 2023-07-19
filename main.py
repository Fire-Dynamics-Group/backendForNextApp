from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pydantic import BaseModel

from fds import testFunction
from time_eq import compute_time_eq, time_eq_test
# from radiation import fillWordDoc

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
from fastapi.responses import StreamingResponse
@app.post("/radiation",
    # responses = {
    #     200: {
    #         "content": {"image/jpeg": {}}
    #     }
    # },
    # response_class=Response
          )
async def radiation_appendix(
    timeArray: List[float], 
    accumulatedDistanceList: List[float], 
    hobDistanceList: List[float], 
    qList: List[float],
    timestepFEDList: List[float],
    accumulatedFEDList: List[float]
):
    import io
    from pathlib import Path
    from docxtpl import DocxTemplate
    from fastapi.responses import FileResponse


    document_name = "Oil Pan Fire Appendix - Template.docx"
    document_path = Path(__file__).parent /"Word Templates"/document_name
    doc = DocxTemplate(document_path)
    bytes_io = fillWordDoc()
    output_filename = "chart.docx"
    def fillWordDoc(CHIP_PAN_ALLOWED=True, HAS_CUSTOM_FIRE_SIZE=False):
        context = {
            "CHIP_PAN_ALLOWED": CHIP_PAN_ALLOWED,
            "HAS_CUSTOM_FIRE_SIZE": HAS_CUSTOM_FIRE_SIZE
        }

        doc.render(context)

        # if __name__ == '__main__':
        doc.save(output_filename)

        bytes_io = io.BytesIO()
        doc.save(bytes_io)

        bytes_io.seek(0)    
        return bytes_io

    # response = StreamingResponse(bytes_io, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    # response.headers['Content-Disposition'] = f'attachment; filename="{output_filename}"'
    # return response
    try:
        return FileResponse(media_type='application/octet-stream',filename=output_filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not read file")