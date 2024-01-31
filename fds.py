import numpy as np

from stairs_fds import setup_landings

'''
    fds walls - done?
    TODO:
        floorplate
        stair landings
        steps between landings 
        

'''
obstruction_name_obj = { # LATER: send in via api
    "obstruction" : "Fire Floor Walls",
    "stairObstruction": "Stair Walls",
}

mesh_name_obj = { # LATER: send in via api
    "mesh": "Mesh",
    "stairMesh": "Stair Mesh"
}

header = [
        "&SURF ID='Plasterboard',",
        "      COLOR='GRAY 80',",
        "      DEFAULT=.TRUE.,",
        "      BACKING='VOID',",
        "      MATL_ID(1,1)='GYPSUM PLASTER',",
        "      MATL_MASS_FRACTION(1,1)=1.0,",
        "      THICKNESS(1)=0.05/",
        "&MATL ID='GYPSUM PLASTER',",
        "      FYI='Quintiere, Fire Behavior - NIST NRC Validation',",
        "      SPECIFIC_HEAT=0.84,",
        "      CONDUCTIVITY=0.48,",
        "      DENSITY=1440.0/"
      ]

def points_to_fds_wall_lines(points, wall_thickness, px_per_m, comments, z, wall_height,is_stair=False):
    array = []
    walls_list = points_to_fds_wall_points(points, wall_thickness, px_per_m, comments, z, wall_height=wall_height,is_stair=False)

    for i in np.round(walls_list,2):
        x1,x2,y1,y2,z1,z2 = i
        array.append(f"&OBST ID='{obstruction_name_obj[comments]}' XB = {x1},{x2},{y1},{y2},{z1},{z2}, SURF_ID='Plasterboard'/")
    return array

def convert_points_to_dict(points):
    return [{"x": point.x, "y": point.y} for point in points]

def convert_canvas_points_to_fds(points, px_per_m):
    # TODO: incorporate scale before sending co-ordinates
    points = [{"x": p["x"]/px_per_m, "y":p["y"]/px_per_m} for p in points]
    return points

def points_to_fds_wall_points(points, wall_thickness, px_per_m, comments, z, wall_height,is_stair=False):
    # TODO: points to be zero-ed at bottom-leftmost point
    walls_list = []
    points = convert_canvas_points_to_fds(points, px_per_m)
    
    if is_stair:
        z1 = 0
        z2 = stair_height
    else:
        z1 = z
        z2 = z + wall_height

    # check if orthogonal if not create non ortho wall
    for i in range(len(points) - 1):
        j = i + 1

        p1 = points[i]
        p2 = points[j]
        
        if p1["x"] == p2["x"]:
            # draw vertical wall

            x1 = min(p1["x"], p1["x"]+wall_thickness, p2["x"], p2["x"]+wall_thickness)
            x2 = max(p1["x"], p1["x"]+wall_thickness, p2["x"], p2["x"]+wall_thickness)            
            # extends in y
            if p2["y"] > p1["y"]:
                # extends in pos y
                y1 = min(p1["y"] - wall_thickness, p2["y"])
                y2 = max(p1["y"] - wall_thickness, p2["y"])

            else:
                y1 = min(p2["y"]-wall_thickness, p1["y"]-wall_thickness)
                y2 = max(p2["y"]-wall_thickness, p1["y"]-wall_thickness)                
            pass
        elif p1["y"] == p2["y"]:
            y1 = min(p2["y"]-wall_thickness, p1["y"], p1["y"]-wall_thickness, p2["y"])
            y2 = max(p2["y"]-wall_thickness, p1["y"], p1["y"]-wall_thickness, p2["y"])
            if p2["x"] < p1["x"]:
                x1 = min(p2["x"], p1["x"])
                x2 = max(p2["x"], p1["x"])
                # wall extends right to left (negative x direction)
            
            else:
                x1 = min(p1["x"], p2["x"]+wall_thickness)
                x2 = max(p1["x"], p2["x"]+wall_thickness)
        walls_list.append([x1, x2, y1, y2, z1, z2])
    
    return walls_list

def create_fds_mesh_lines(points, cell_size, z1, z2, px_per_m, comments, idx, fds_array, is_stair=False):
    # LATER: mesh vents 
    # TODO: STAIR MESHES
    current_cell_size = cell_size # changes for stair upper and lower!!!
    points = convert_canvas_points_to_fds(points, px_per_m)
    x_points = [p['x'] for p in points]
    y_points = [p['y'] for p in points]
    x1 = min(x_points)
    x2 = max(x_points)
    y1 = min(y_points)
    y2 = max(y_points)
    z1 = min(z1, z2)
    z2 = max(z1, z2)
    mesh_deltaY = round(y2 - y1, 3)
    mesh_deltaZ = round(z2 - z1, 3)
    mesh_deltaX = round(x2 - x1, 3)
    id = mesh_name_obj[comments] # should be mesh1 etc
    # mesh_width = x2 - x1
    # k_num = z2 - z1
    first = f"&MESH ID='{id}{idx}', IJK={round(mesh_deltaX / current_cell_size)},"
    second = f"{round(mesh_deltaY / current_cell_size)},{round((mesh_deltaZ / current_cell_size))}, XB="
    third = f"{round((x1),1)},"
    fourth= f"{round((x2),1)},"
    fifth = f"{round((y1),1)},"
    sixth = f"{round((y2),1)},{z1},{z2}/"
    line = first + second + third + fourth + fifth + sixth
    fds_array.append(line)


def create_mesh(comments, elements, cell_size, px_per_m, z, fds_array, wall_height=3.5):
    meshes = [ f for f in elements if f["comments"] == comments]
    for idx, mesh in enumerate(meshes):
        points = mesh["points"]
        # pass index?
        create_fds_mesh_lines(points, cell_size, z, z + wall_height, px_per_m, comments, idx, fds_array, is_stair=False)


def add_rows_to_fds_array(fds_array, *args):
    for element in (args):
        fds_array.append(element)

def add_array_to_fds_array(array, fds_array):
    add_rows_to_fds_array(fds_array, *array)


def array_to_str(array):
    array = [ f for f in array if len(f)!= 0]
    return "\n".join(array)

def add_obstruction_to_fds(comments, elements, z, wall_height, wall_thickness, stair_enclosure_roof_z, px_per_m, fds_array):
    # print("elements: ", elements)
    try:
        output = [ f for f in elements if f.comments == comments]
        if output:
            output = output[0]
            points = output.points
        else:
            # Handle the case where no elements match
            # For example, return an empty list or raise an exception
            print("no elements match")
            return []
    except:
        filtered_elements = [f for f in elements if f["comments"] == comments]
        if filtered_elements:
            output = filtered_elements[0]
            points = output["points"]
        else:
            # Handle the case where no elements match
            # For example, return an empty list or raise an exception
            print("no elements match")
            return []

    # TODO: walls to go from level zero to max stair enclosure height
    if comments == "stairObstruction":
        z = 0
        wall_height = stair_enclosure_roof_z
    obstruction_list = points_to_fds_wall_lines(points=points, wall_thickness=wall_thickness, px_per_m=px_per_m, comments=comments, z=z,wall_height=wall_height,is_stair=False)
    add_array_to_fds_array(obstruction_list, fds_array)

def returnOrigin(elements):
    min_x = float('inf')  # Start with a very large number
    min_y = float('inf')
    for element in elements:
        if __name__ != '__main__':
            points = element.points
        else:
            points = element['points']
        for point in points:
            if __name__ != '__main__':
                pointX = point.x
                pointY = point.y
            else:
                pointX = point['x']
                pointY = point['y']
            x = pointX  # Assuming each point is a tuple or list (x, y)
            y = pointY
            if x < min_x:
                min_x = x
            if y < min_y:
                min_y = y
    return min_x, min_y

def makeElementsRelativeToOrigin(elements, origin):
    new_elements = []
    for element in elements:
        new_points = []
        if __name__ != '__main__':
            points = element.points
        else:
            points = element['points']
        for point in points:
            if __name__ != '__main__':
                pointX = point.x
                pointY = point.y
            else:
                pointX = point['x']
                pointY = point['y']
            new_points.append({
                'x': pointX - origin[0],
                'y': pointY - origin[1]
            })
        if __name__ != '__main__':
            new_elements.append({
                'comments': element.comments,
                'id': element.id,
                'points': new_points,
                'type': element.type
            })
        else:
            new_elements.append({
                'comments': element['comments'],
                'id': element['id'],
                'points': new_points,
                'type': element['type']
            })
    return new_elements

def testFunction(elements, z, wall_height, wall_thickness, stair_height, px_per_m, fire_floor, total_floors, stair_enclosure_roof_z):
    # turn obstructions into fds code and send back
    fds_array = header.copy()  # Initialize fds_array here
    obstruction_list = []
    stair_obstruction_list = []
    cell_size = 0.1
    # TODO: test on not including all different elements
    # TODO: find bottom left point as origin and change all points to be relative to that
    origin = returnOrigin(elements)
    elements = makeElementsRelativeToOrigin(elements, origin)
    add_obstruction_to_fds(comments='obstruction', elements=elements, z=z, wall_height=wall_height, wall_thickness=wall_thickness, stair_enclosure_roof_z=stair_enclosure_roof_z, px_per_m=px_per_m, fds_array=fds_array)
    add_obstruction_to_fds(comments='stairObstruction', elements=elements, z=z, wall_height=wall_height, wall_thickness=wall_thickness, stair_enclosure_roof_z=stair_enclosure_roof_z, px_per_m=px_per_m, fds_array=fds_array)
    create_mesh(comments='mesh', elements=elements, cell_size=cell_size, px_per_m=px_per_m, z=z, fds_array=fds_array)
    create_mesh(comments='stairMesh', elements=elements, cell_size=cell_size, px_per_m=px_per_m, z=z, fds_array=fds_array)
    stair_list = setup_landings(comments="landing", fire_floor=fire_floor, total_floors=total_floors, elements=elements, px_per_m=px_per_m, z=z, stair_enclosure_roof_z=stair_enclosure_roof_z)
    # for stair_row in stair_list:
    add_array_to_fds_array(stair_list, fds_array)
    final = array_to_str(fds_array)
    return final



if __name__ == '__main__':
    # points = [{"x":234.58699702156903,"y":1418.6927915113936},{"x":497.1010174980868,"y":1418.6927915113936},{"x":497.1010174980868,"y":1329.3263164555578},{"x":234.58699702156903,"y":1329.3263164555578},{"x":234.58699702156903,"y":1418.6927915113936}]
    # comments = "obstruction"
    z = 10
    wall_height = 2.5 
    wall_thickness = 0.2 
    stair_height = 30  
    px_per_m = 33.600380950221385  
    # array = points_to_fds_wall_lines(points, wall_thickness, px_per_m, comments, is_stair=False)
    # add_array_to_fds_array(array)
    # joined = array_to_str(fds_array)
    comments = 'mesh'
    from mockData import stairElements
    cell_size = 0.1
    final = testFunction(stairElements, z, wall_height, wall_thickness, stair_height, px_per_m, fire_floor=2, total_floors=7, stair_enclosure_roof_z=40) 
    # landing_array = setup_landings(
    #                 comments="landing", 
    #                 fire_floor=2, 
    #                 total_floors=7, 
    #                 elements=stairElements, 
    #                 px_per_m=px_per_m,
    #                 z=10, 
    #                 stair_enclosure_roof_z=50
    #                 )
    # for line in landing_array:
    #     fds_array.append(line)
    # # TODO: add steps
    # pass

