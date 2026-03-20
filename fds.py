import numpy as np

from stairs_fds import setup_landings
from controls import generate_door_controls, extract_controls_fds, Control_ID_Apartment, Control_ID_Stair, Control_ID_Extract

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

def sim_header(chid='model', sim_end_time=300):
    """Generate HEAD, TIME, DUMP, COMB lines."""
    return [
        f"&HEAD CHID='{chid}'/",
        f"&TIME T_END={sim_end_time}/",
        "&DUMP DT_RESTART=300.0, DT_SL3D=0.25/",
        "&COMB SUPPRESSION=.FALSE./",
    ]


header = "\n".join([
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
      ])

def points_to_fds_wall_lines(points, wall_thickness, px_per_m, comments, z, wall_height,is_stair=False, transparency=None):
    array = []
    walls_list = points_to_fds_wall_points(points, wall_thickness, px_per_m, comments, z, wall_height=wall_height,is_stair=False)

    for i in np.round(walls_list,2):
        x1,x2,y1,y2,z1,z2 = i
        transparency_str = ""
        if transparency is not None and transparency > 0:
            transparency_str = f", RGB=255,255,255, TRANSPARENCY={round(transparency, 6)}"
        array.append(f"&OBST ID='{obstruction_name_obj[comments]}', XB={x1},{x2},{y1},{y2},{z1},{z2}, SURF_ID='Plasterboard'{transparency_str}/")
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
    return line


def create_mesh(comments, elements, cell_size, px_per_m, z, fds_array, wall_height=3.5):
    meshes = [ f for f in elements if f["comments"] == comments]
    for idx, mesh in enumerate(meshes):
        points = mesh["points"]
        line = create_fds_mesh_lines(points, cell_size, z, z + wall_height, px_per_m, comments, idx, fds_array, is_stair=False)
        fds_array.append(line)
    return fds_array

def add_rows_to_fds_array(fds_array, *args):
    for element in (args):
        fds_array.append(element)
    return fds_array

def add_array_to_fds_array(array, fds_array):
    fds_array = add_rows_to_fds_array(fds_array, *array)
    return fds_array


def array_to_str(array):
    array = [str(f) for f in array if f is not None and str(f).strip() != '']
    return "\n".join(array)

ROLE_TO_CTRL_ID = {
    "apartment": Control_ID_Apartment,
    "stair": Control_ID_Stair,
}

def add_door_holes_to_fds(elements, z, wall_height, wall_thickness, fds_array, door_height=2.1, scenario_type="MOE", door_roles=None):
    if door_roles is None:
        door_roles = {}
    doors = [ f for f in elements if "door" in f["comments"]]

    depth = 0.4
    line_array = []
    for idx, door in enumerate(doors):
        points = door["points"]
        door_id = str(door.get("id", idx))
        deltaX = abs(points[1]["x"] - points[0]["x"])
        deltaY = abs(points[1]["y"] - points[0]["y"])
        z1 = z
        z2 = z + door_height
        x1 = min(points[0]["x"], points[0]["x"])
        x2 = max(points[1]["x"], points[1]["x"])
        y1 = min(points[0]["y"], points[0]["y"])
        y2 = max(points[1]["y"], points[1]["y"])
        if deltaX < deltaY:
            x1 -= depth
            x2 += depth
        else:
            y1 -= depth
            y2 += depth

        # Use door role to determine CTRL_ID
        role = door_roles.get(door_id, "")
        ctrl_suffix = ""
        if scenario_type != "none" and role in ROLE_TO_CTRL_ID:
            ctrl_suffix = f", CTRL_ID='{ROLE_TO_CTRL_ID[role]}'"

        role_label = role.capitalize() if role else f"door{idx}"
        fds_line = f"&HOLE ID='{role_label} Door Hole', XB ={x1},{x2},{y1},{y2},{z1},{z2}{ctrl_suffix}/"
        line_array.append(fds_line)
    return line_array


def add_obstruction_to_fds(comments, elements, z, wall_height, wall_thickness, stair_enclosure_roof_z, px_per_m, fds_array, transparency=None):
    # print("elements: ", elements)
    try:
        output = [ f for f in elements if f.comments == comments]
        if output:
            output = output
            dev = True
            # points = output.points
        else:
            # Handle the case where no elements match
            print("no elements match")
            return fds_array
    except:
        filtered_elements = [f for f in elements if f["comments"] == comments]
        if filtered_elements:
            output = filtered_elements
            dev = False
            # points = output["points"]
        else:
            # Handle the case where no elements match
            print("no elements match")
            return fds_array

    # TODO: walls to go from level zero to max stair enclosure height
    if comments == "stairObstruction":
        z = 0
        wall_height = stair_enclosure_roof_z
    for f in output:
        if dev:
            points = f.points
        else:
            points = f["points"]
        obstruction_list = points_to_fds_wall_lines(points=points, wall_thickness=wall_thickness, px_per_m=px_per_m, comments=comments, z=z,wall_height=wall_height,is_stair=False, transparency=transparency)
        add_array_to_fds_array(obstruction_list, fds_array)
    return fds_array

def _get_attr(obj, key):
    """Access attribute by key, supporting both dicts and Pydantic objects."""
    try:
        return obj[key]
    except (TypeError, KeyError):
        return getattr(obj, key)


def returnOrigin(elements):
    min_x = float('inf')
    min_y = float('inf')
    for element in elements:
        points = _get_attr(element, 'points')
        for point in points:
            x = _get_attr(point, 'x')
            y = _get_attr(point, 'y')
            if x < min_x:
                min_x = x
            if y < min_y:
                min_y = y
    return min_x, min_y

def makeElementsRelativeToOrigin(elements, origin):
    new_elements = []
    for element in elements:
        new_points = []
        points = _get_attr(element, 'points')
        for point in points:
            new_points.append({
                'x': _get_attr(point, 'x') - origin[0],
                'y': _get_attr(point, 'y') - origin[1],
            })
        new_elements.append({
            'comments': _get_attr(element, 'comments'),
            'id': _get_attr(element, 'id'),
            'points': new_points,
            'type': _get_attr(element, 'type')
        })
    return new_elements

def convertElPointsToCoords(elements, px_per_m):
    for element in elements:
        points = element['points']
        element['points'] = convert_canvas_points_to_fds(points, px_per_m)
    return elements

def fire_surface(hrr_kw, fire_area, is_steady_state=False):
    if not is_steady_state:
        array = ["&SURF ID='Fire',",
        "      COLOR='RED',",
        f"      HRRPUA={hrr_kw/fire_area}",
        "      RAMP_Q='Fire_RAMP_Q'",
        "      TMP_FRONT=300.0/"]
    else: # steady_state fire
        array = ["&SURF ID='Fire',",
        "      COLOR='RED',",
        f"      HRRPUA={hrr_kw/fire_area}", 
        "      TMP_FRONT=300.0/"]
    return array

def fuel_reaction(Soot_Yield, Heat_of_Combustion):
    return [
        "&REAC ID='POLYURETHANE',",
        "      FYI='NFPA Babrauskas',",
        "      FUEL = 'REAC_FUEL',",
        "      C=6.3,",
        "      H=7.1,",
        "      O=2.1,",
        "      N=1.0,",
        f"      SOOT_YIELD = {Soot_Yield},",
        f"      HEAT_OF_COMBUSTION = {Heat_of_Combustion}/",
    ]

def find_fire_obstruction(elements, z):
    fires = [ f for f in elements if f["comments"] == "fire"]
    array = []
    for fire in fires:
        points = fire['points'][0]
        fire_x = points["x"]
        fire_y = points["y"]
        fire_D = 2
        fire_H = 0.2
        fire_B = 0.1
        array.append('/n'.join(Fire_Obstruction(fire_D, fire_H, fire_B, fire_x, fire_y, z)))
    return array

def Fire_Obstruction(Fire_D, Fire_H, Fire_B, fire_x, fire_y, z):## Create a Function that generates the fire obstruction 
    # TODO: add sprinklers using calcs
    fire_Co = np.round([fire_x - Fire_D/2, fire_x + Fire_D/2, fire_y - Fire_D/2, fire_y+ Fire_D/2, z+Fire_B, z+Fire_H],2) 
    fire_x1 = round(fire_x - Fire_D/2, 2)
    fire_x2 = round(fire_x + Fire_D/2, 2)
    fire_y1 = round(fire_y - Fire_D/2, 2)
    fire_y2 = round(fire_y + Fire_D/2, 2)
    fire_z1 = round(z+Fire_B, 2)
    fire_z2 = round(z+Fire_H, 2)
    return [f"&OBST ID='Fire', XB = {fire_x1},{fire_x2},{fire_y1},{fire_y2},{fire_z1},{fire_z2}, SURF_IDS='Fire','Plasterboard','Plasterboard'/"]

def create_stair_roof(elements, stair_enclosure_roof_z, transparency=None):
    """Create a roof slab over the stair enclosure bounding box."""
    stair_obs = [f for f in elements if f["comments"] == "stairObstruction"]
    if not stair_obs:
        return []

    all_x = []
    all_y = []
    for obs in stair_obs:
        for p in obs["points"]:
            all_x.append(p["x"])
            all_y.append(p["y"])

    x_min = round(min(all_x), 2)
    x_max = round(max(all_x), 2)
    y_min = round(min(all_y), 2)
    y_max = round(max(all_y), 2)
    z1 = round(stair_enclosure_roof_z - 0.2, 2)
    z2 = round(stair_enclosure_roof_z, 2)

    transparency_str = ""
    if transparency is not None and transparency > 0:
        transparency_str = f", RGB=255,255,255, TRANSPARENCY={round(transparency, 6)}"

    return [f"&OBST ID='Stair Roof', XB={x_min},{x_max},{y_min},{y_max},{z1},{z2}, SURF_ID='Plasterboard'{transparency_str}/"]


def create_stair_aov(elements, stair_enclosure_roof_z, aov_mode="always_open", cell_size=0.2):
    """Create a 1m x 1m roof vent hole centred on the landing midpoint."""
    landings = [f for f in elements if f["comments"] == "landing"]
    if not landings:
        return []

    centres_x = []
    centres_y = []
    for landing in landings:
        xs = [p["x"] for p in landing["points"]]
        ys = [p["y"] for p in landing["points"]]
        centres_x.append((min(xs) + max(xs)) / 2)
        centres_y.append((min(ys) + max(ys)) / 2)

    mid_x = sum(centres_x) / len(centres_x)
    mid_y = sum(centres_y) / len(centres_y)

    def snap(val):
        return round(round(val / cell_size) * cell_size, 2)

    cx = snap(mid_x)
    cy = snap(mid_y)
    x1 = round(cx - 0.5, 2)
    x2 = round(cx + 0.5, 2)
    y1 = round(cy - 0.5, 2)
    y2 = round(cy + 0.5, 2)
    z1 = round(stair_enclosure_roof_z - 0.4, 2)
    z2 = round(stair_enclosure_roof_z + 0.4, 2)

    ctrl_suffix = ""
    if aov_mode in ("timed", "sprinkler"):
        ctrl_id = f'{Control_ID_Extract}1'
        ctrl_suffix = f", CTRL_ID='{ctrl_id}'"

    return [f"&HOLE ID='AOV', XB = {x1}, {x2}, {y1}, {y2}, {z1}, {z2}{ctrl_suffix}/"]


def create_aov_sprinkler_devc(elements, stair_enclosure_roof_z):
    """Create a sprinkler DEVC at the AOV location that triggers the AOV opening."""
    landings = [f for f in elements if f["comments"] == "landing"]
    if not landings:
        return []

    centres_x = []
    centres_y = []
    for landing in landings:
        xs = [p["x"] for p in landing["points"]]
        ys = [p["y"] for p in landing["points"]]
        centres_x.append((min(xs) + max(xs)) / 2)
        centres_y.append((min(ys) + max(ys)) / 2)

    mid_x = round(sum(centres_x) / len(centres_x), 2)
    mid_y = round(sum(centres_y) / len(centres_y), 2)
    z = round(stair_enclosure_roof_z - 0.3, 2)

    ctrl_id = f'{Control_ID_Extract}1'
    return [
        f"&DEVC ID='AOV Sprinkler', PROP_ID='AOV Link', XYZ={mid_x},{mid_y},{z}/",
        f"&PROP ID='AOV Link', QUANTITY='LINK TEMPERATURE', RTI=50, ACTIVATION_TEMPERATURE=68.0/",
        f"&CTRL ID='{ctrl_id}', INPUT_ID='AOV Sprinkler', FUNCTION_TYPE='ALL'/",
    ]


def testFunction(elements, z, wall_height, wall_thickness, stair_height, px_per_m, fire_floor, total_floors, stair_enclosure_roof_z,
                 scenario_type="MOE", sim_end_time=300, door_openings=None, door_leakages_enabled=False, door_leakage_config=None, door_roles=None,
                 landing_roles=None, landing_up_side=None, obstruction_transparency=None,
                 aov_mode="always_open", aov_activation_time=None, stair_style="overlapping"):
    if door_openings is None:
        door_openings = {}
    if door_leakage_config is None:
        door_leakage_config = {}
    if door_roles is None:
        door_roles = {}
    if obstruction_transparency is None:
        obstruction_transparency = {}

    # 1. Simulation header
    header_lines = sim_header(chid='model', sim_end_time=sim_end_time)

    # 2. Materials/Surfaces
    fds_array = header_lines + [header]

    cell_size = 0.1

    # find bottom left point as origin and change all points to be relative to that
    origin = returnOrigin(elements)
    elements = makeElementsRelativeToOrigin(elements, origin)
    elements = convertElPointsToCoords(elements, px_per_m)

    # 3. Meshes
    fds_array = create_mesh(comments='mesh', elements=elements, cell_size=cell_size, px_per_m=px_per_m, z=z, fds_array=fds_array)
    fds_array = create_mesh(comments='stairMesh', elements=elements, cell_size=cell_size, px_per_m=px_per_m, z=z, fds_array=fds_array)

    # 4. Obstructions
    fire_wall_transparency = obstruction_transparency.get("fireFloorWalls", 0.0)
    stair_wall_transparency = obstruction_transparency.get("stairWalls", 0.25)
    stair_roof_transparency = obstruction_transparency.get("stairRoof", 0.25)

    fds_array = add_obstruction_to_fds(comments='obstruction', elements=elements, z=z, wall_height=wall_height, wall_thickness=wall_thickness, stair_enclosure_roof_z=stair_enclosure_roof_z, px_per_m=px_per_m, fds_array=fds_array, transparency=fire_wall_transparency)
    fds_array = add_obstruction_to_fds(comments='stairObstruction', elements=elements, z=z, wall_height=wall_height, wall_thickness=wall_thickness, stair_enclosure_roof_z=stair_enclosure_roof_z, px_per_m=px_per_m, fds_array=fds_array, transparency=stair_wall_transparency)

    # 5. Door controls based on scenario_type
    if scenario_type:
        control_lines = generate_door_controls(scenario_type, door_openings)
        fds_array = add_array_to_fds_array(control_lines, fds_array)

    # 6. Door holes (with CTRL_ID when scenario_type is set)
    door_scenario = scenario_type if scenario_type else "none"
    door_array = add_door_holes_to_fds(elements, z, wall_height, wall_thickness, fds_array, door_height=2.1, scenario_type=door_scenario, door_roles=door_roles)
    fds_array = add_array_to_fds_array(door_array, fds_array)

    # 7. Fire obstruction & surface
    fire_surface_array = fire_surface(hrr_kw=1000, fire_area=10, is_steady_state=False)
    fds_array = add_array_to_fds_array(find_fire_obstruction(elements, z), fds_array)
    fds_array = add_array_to_fds_array(fire_surface_array, fds_array)

    # 8. Reaction chemistry
    reaction_array = fuel_reaction(0.07, 25000)
    fds_array = add_array_to_fds_array(reaction_array, fds_array)

    # 9. Stair landings/steps
    stair_list = setup_landings(comments="landing", fire_floor=fire_floor, total_floors=total_floors, elements=elements, px_per_m=px_per_m, z=z, stair_enclosure_roof_z=stair_enclosure_roof_z, landing_roles=landing_roles, landing_up_side=landing_up_side, stair_style=stair_style)
    fds_array = add_array_to_fds_array(stair_list, fds_array)

    # 9a. Stair roof slab
    roof_lines = create_stair_roof(elements, stair_enclosure_roof_z, transparency=stair_roof_transparency)
    fds_array = add_array_to_fds_array(roof_lines, fds_array)

    # 9b. AOV (roof vent hole)
    aov_lines = create_stair_aov(elements, stair_enclosure_roof_z, aov_mode=aov_mode)
    fds_array = add_array_to_fds_array(aov_lines, fds_array)

    # 9c. AOV controls (only when mode is timed or sprinkler)
    if aov_mode == "timed":
        activation_time = float(aov_activation_time) if aov_activation_time is not None else float(door_openings.get("apartment_open", 30)) + 10
        extract_lines = extract_controls_fds(activation_time, number=1)
        fds_array = add_array_to_fds_array(extract_lines, fds_array)
    elif aov_mode == "sprinkler":
        sprinkler_lines = create_aov_sprinkler_devc(elements, stair_enclosure_roof_z)
        fds_array = add_array_to_fds_array(sprinkler_lines, fds_array)

    # 10. TAIL
    fds_array.append("&TAIL/")

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

