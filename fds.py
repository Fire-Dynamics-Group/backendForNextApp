import numpy as np

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
        # array.append(convert_print_to_string(("&OBST ID='Corridor Walls'", 'XB =', list_to_comma_str(i), ", SURF_ID='Plasterboard'/")))
    return array
def convert_points_to_dict(points):
    return [{"x": point.x, "y": point.y} for point in points]

def convert_canvas_points_to_fds(points, px_per_m):
    if __name__ != '__main__':
        points = convert_points_to_dict(points)
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
        # # i and j
        # if i == len(points) - 1:
        #     j = 0
        # else:
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

def create_fds_mesh_lines(points, cell_size, z1, z2, px_per_m, comments, idx, is_stair=False):
    # LATER: mesh vents 
    # TODO: STAIR MESHES
    mesh_height = z2 - z1
    current_cell_size = cell_size # changes for stair upper and lower!!!
    points = convert_canvas_points_to_fds(points, px_per_m)
    x_points = [p['x'] for p in points]
    y_points = [p['y'] for p in points]
    x1 = min(x_points)
    x2 = max(x_points)
    y1 = min(y_points)
    y2 = max(y_points)
    id = mesh_name_obj[comments] # should be mesh1 etc
    mesh_width = x2 - x1
    k_num = z2 - z1
    first = f"&MESH ID='{id}{idx}', IJK={round(mesh_width / current_cell_size)},"
    second = f"{round(mesh_height / current_cell_size)},{round((k_num / current_cell_size))}, XB="
    third = f"{round((x1),1)},"
    fourth= f"{round((x2),1)},"
    fifth = f"{round((y1),1)},"
    sixth = f"{round((y2),1)},{z1},{z2}/"
    line = first + second + third + fourth + fifth + sixth
    fds_array.append(line)


def create_mesh(comments, elements, cell_size, px_per_m, z, wall_height=3.5):
    if __name__ != '__main__':
        meshes = [ f for f in elements if f.comments == comments]
    else:
        meshes = [ f for f in elements if f["comments"] == comments]
    for idx, mesh in enumerate(meshes):
        print("mesh: ", mesh)
        if __name__ != '__main__':
            points = mesh.points
        else:
            points = mesh["points"]
        # pass index?
        create_fds_mesh_lines(points, cell_size, z, z + wall_height, px_per_m, comments, idx, is_stair=False)
        # x1 = min([p["x"] for p in points])
        # x2 = max([p["x"] for p in points])
        # y1 = min([p["y"] for p in points])
        # y2 = max([p["y"] for p in points])
        # z1 = 0
        # z2 = 0
        # # create fds lines array


        # add_array_to_fds_array(obstruction_list)
    # is it required to snap mesh to each other? 
    # should not be required as points already snap to nearest 0.1m 

    # check if stair or normal mesh
    # LATER: should be use agnostic -> send in cell_size and mesh z1 and z2 
    pass

fds_array = header

def add_rows_to_fds_array(fds_array, *args):
    for element in (args):
        fds_array.append(element)

def add_array_to_fds_array(array, fds_array=fds_array):
    add_rows_to_fds_array(fds_array, *array)


def array_to_str(array):
    array = [ f for f in array if len(f)!= 0]
    return "\n".join(array)

def add_obstruction_to_fds(comments, elements, z, wall_height, wall_thickness, stair_height, px_per_m):
    output = [ f for f in elements if f.comments == comments][0] 
    obstruction_list = points_to_fds_wall_lines(points=output.points, wall_thickness=wall_thickness, px_per_m=px_per_m, comments=comments, z=z,wall_height=wall_height,is_stair=False)
    add_array_to_fds_array(obstruction_list)

def testFunction(elements, z, wall_height, wall_thickness, stair_height, px_per_m):
    # turn obstructions into fds code and send back
    obstruction_list = []
    stair_obstruction_list = []
    cell_size = 0.1


    add_obstruction_to_fds(comments='obstruction', elements=elements, z=z, wall_height=wall_height, wall_thickness=wall_thickness, stair_height=stair_height, px_per_m=px_per_m)
    add_obstruction_to_fds(comments='stairObstruction', elements=elements, z=z, wall_height=wall_height, wall_thickness=wall_thickness, stair_height=stair_height, px_per_m=px_per_m)
    create_mesh(comments='mesh', elements=elements, cell_size=cell_size, px_per_m=px_per_m, z=z)
    create_mesh(comments='stairMesh', elements=elements, cell_size=cell_size, px_per_m=px_per_m, z=z)
    final = array_to_str(fds_array)

    return final


if __name__ == '__main__':
    # points = [{"x":234.58699702156903,"y":1418.6927915113936},{"x":497.1010174980868,"y":1418.6927915113936},{"x":497.1010174980868,"y":1329.3263164555578},{"x":234.58699702156903,"y":1329.3263164555578},{"x":234.58699702156903,"y":1418.6927915113936}]
    # comments = "obstruction"
    # z = 10
    # wall_height = 2.5 
    # wall_thickness = 0.2 
    # stair_height = 30  
    px_per_m = 33.600380950221385  
    # array = points_to_fds_wall_lines(points, wall_thickness, px_per_m, comments, is_stair=False)
    # add_array_to_fds_array(array)
    # joined = array_to_str(fds_array)
    comments = 'mesh'
    elements = [
    {
        "type": "polyline",
        "points": [
            {
                "x": 434.8527476376342,
                "y": 832.0410840625599
            },
            {
                "x": 551.2700186587331,
                "y": 832.0410840625599
            },
            {
                "x": 551.2700186587331,
                "y": 780.6805233179574
            },
            {
                "x": 606.0546167863091,
                "y": 780.6805233179574
            }
        ],
        "comments": "obstruction",
        "id": 0
    },
    {
        "type": "polyline",
        "points": [
            {
                "x": 606.0546167863091,
                "y": 832.0410840625599
            },
            {
                "x": 671.1113270628056,
                "y": 832.0410840625599
            },
            {
                "x": 671.1113270628056,
                "y": 886.8256821901359
            },
            {
                "x": 606.0546167863091,
                "y": 886.8256821901359
            },
            {
                "x": 606.0546167863091,
                "y": 832.0410840625599
            }
        ],
        "comments": "obstruction",
        "id": 1
    },
    {
        "type": "polyline",
        "points": [
            {
                "x": 609.4786541692825,
                "y": 1099.1159999344927
            },
            {
                "x": 691.6555513606465,
                "y": 1099.1159999344927
            },
            {
                "x": 691.6555513606465,
                "y": 897.0977943390563
            },
            {
                "x": 664.2632522968586,
                "y": 897.0977943390563
            },
            {
                "x": 664.2632522968586,
                "y": 917.6420186368973
            },
            {
                "x": 609.4786541692825,
                "y": 917.6420186368973
            },
            {
                "x": 609.4786541692825,
                "y": 1099.1159999344927
            }
        ],
        "comments": "stairObstruction",
        "id": 2
    },
    {
        "type": "polyline",
        "points": [
            {
                "x": 571.814242956574,
                "y": 1109.3881120834133
            },
            {
                "x": 506.75753268007765,
                "y": 883.4016448071624
            },
            {
                "x": 400.6123738078992,
                "y": 883.4016448071624
            },
            {
                "x": 400.6123738078992,
                "y": 1109.3881120834133
            },
            {
                "x": 571.814242956574,
                "y": 1109.3881120834133
            }
        ],
        "comments": "stairObstruction",
        "id": 3
    },
    {
        "type": "rect",
        "points": [
            {
                "x": 575.2382803395476,
                "y": 883.4016448071624
            },
            {
                "x": 708.775738275514,
                "y": 1109.3881120834133
            }
        ],
        "comments": "mesh",
        "id": 4
    }
]
    cell_size = 0.1
    create_mesh(comments, elements, cell_size, px_per_m, z=10)
    pass

