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
    current_cell_size = cell_size

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
    id = mesh_name_obj[comments]
    first = f"&MESH ID='{id}{idx}', IJK={round(mesh_deltaX / current_cell_size)},"
    second = f"{round(mesh_deltaY / current_cell_size)},{round((mesh_deltaZ / current_cell_size))}, XB="
    third = f"{round((x1),1)},"
    fourth= f"{round((x2),1)},"
    fifth = f"{round((y1),1)},"
    sixth = f"{round((y2),1)},{z1},{z2}/"
    line = first + second + third + fourth + fifth + sixth
    return line


def create_mesh(comments, elements, cell_size, px_per_m, z, fds_array, wall_height=3.5, z2_override=None, inlets=None, inlet_config=None):
    meshes = [ f for f in elements if f["comments"] == comments]
    z_top = z2_override if z2_override is not None else z + wall_height

    for idx, mesh in enumerate(meshes):
        points = mesh["points"]

        # Determine pushbacks only for inlets that touch THIS mesh
        mesh_pushbacks = []
        if inlets:
            for inlet in inlets:
                pb = find_inlet_mesh_pushback(points, inlet["points"])
                # Only apply if the inlet is actually on this mesh's face
                # (i.e. the inlet midpoint is within or very close to the mesh bounds)
                inp = inlet["points"]
                inlet_mid_x = (inp[0]["x"] + inp[1]["x"]) / 2
                inlet_mid_y = (inp[0]["y"] + inp[1]["y"]) / 2
                xs = [p["x"] for p in points]
                ys = [p["y"] for p in points]
                mx1, mx2 = min(xs), max(xs)
                my1, my2 = min(ys), max(ys)
                tolerance = 2.0  # metres tolerance for matching inlet to mesh
                if (mx1 - tolerance <= inlet_mid_x <= mx2 + tolerance and
                    my1 - tolerance <= inlet_mid_y <= my2 + tolerance):
                    # Attach per-inlet config so we know if it's mechanical
                    inlet_id = str(inlet.get("id", ""))
                    pb["inlet_config"] = inlet_config.get(inlet_id, {}) if inlet_config else {}
                    pb["inlet_number"] = len(mesh_pushbacks) + 1
                    mesh_pushbacks.append(pb)

        # Apply pushback to a copy of the points
        if mesh_pushbacks:
            xs = [p["x"] for p in points]
            ys = [p["y"] for p in points]
            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)

            for pb in mesh_pushbacks:
                face = pb["face"]
                dist = pb["distance"]
                if face == "xmin":
                    xmin -= dist
                elif face == "xmax":
                    xmax += dist
                elif face == "ymin":
                    ymin -= dist
                elif face == "ymax":
                    ymax += dist

            points = [{"x": xmin, "y": ymin}, {"x": xmax, "y": ymax}]

        line = create_fds_mesh_lines(points, cell_size, z, z_top, px_per_m, comments, idx, fds_array, is_stair=False)
        fds_array.append(line)

        # Create OPEN vents on pushed-back faces
        if mesh_pushbacks:
            xs = [p["x"] for p in points]
            ys = [p["y"] for p in points]
            x1, x2 = round(min(xs), 1), round(max(xs), 1)
            y1, y2 = round(min(ys), 1), round(max(ys), 1)

            for pb_idx, pb in enumerate(mesh_pushbacks):
                face = pb["face"]
                if face == "xmin":
                    vent_xb = f"{x1},{x1},{y1},{y2},{z},{z_top}"
                elif face == "xmax":
                    vent_xb = f"{x2},{x2},{y1},{y2},{z},{z_top}"
                elif face == "ymin":
                    vent_xb = f"{x1},{x2},{y1},{y1},{z},{z_top}"
                elif face == "ymax":
                    vent_xb = f"{x1},{x2},{y2},{y2},{z},{z_top}"

                icfg = pb.get("inlet_config", {})
                inlet_type = icfg.get("type", "natural")
                inlet_num = pb.get("inlet_number", pb_idx + 1)

                if inlet_type == "mechanical":
                    flow_rate = icfg.get("flowRate", 3.0)
                    tau_v = icfg.get("tauV", None)
                    tau_v_str = f", TAU_V={tau_v}" if tau_v is not None else ""
                    supply_surf_id = f"Supply_{inlet_num}"
                    fds_array.append(f"&SURF ID='{supply_surf_id}', VOLUME_FLOW=-{flow_rate}{tau_v_str}, RGB=26,204,26/")
                    fds_array.append(f"&VENT ID='Supply Vent {inlet_num}', SURF_ID='{supply_surf_id}', XB={vent_xb}/")
                else:
                    fds_array.append(f"&VENT ID='Inlet Mesh Vent {pb_idx + 1}', SURF_ID='OPEN', XB={vent_xb}/")

    return fds_array


def snap_to_grid(val, grid=0.2):
    """Snap a value to the nearest grid multiple."""
    return round(round(val / grid) * grid, 1)


def create_stair_meshes(elements, cell_size, px_per_m, z, wall_height, stair_enclosure_roof_z, fds_array):
    """Create up to 3 stair meshes: Lower (0.2m), Middle/fire floor (0.1m), Upper (0.2m).

    - Lower: 0 to z (below fire floor) — skipped if fire floor is at ground level
    - Middle: z to z+wall_height (fire floor) — 0.1m cell size
    - Upper: z+wall_height to stair_enclosure_roof_z+0.4 — skipped if not enough height (<=2m)
    """
    stair_meshes = [f for f in elements if f["comments"] == "stairMesh"]
    coarse_cell = 2 * cell_size  # 0.2m

    for idx, mesh in enumerate(stair_meshes):
        points = mesh["points"]
        x_points = [p['x'] for p in points]
        y_points = [p['y'] for p in points]
        x1 = round(min(x_points), 1)
        x2 = round(max(x_points), 1)
        y1 = round(min(y_points), 1)
        y2 = round(max(y_points), 1)
        dx = round(x2 - x1, 3)
        dy = round(y2 - y1, 3)

        # Lower mesh: 0 to z (below fire floor)
        lower_z1 = snap_to_grid(0)
        lower_z2 = snap_to_grid(z)
        if lower_z2 > lower_z1:
            dz = round(lower_z2 - lower_z1, 3)
            fds_array.append(
                f"&MESH ID='Stair Mesh_Lower{idx}', IJK={round(dx/coarse_cell)},{round(dy/coarse_cell)},{round(dz/coarse_cell)}, XB={x1},{x2},{y1},{y2},{lower_z1},{lower_z2}/"
            )

        # Middle mesh: z to z+wall_height (fire floor — fine 0.1m mesh)
        mid_z1 = snap_to_grid(z)
        mid_z2 = snap_to_grid(z + wall_height)
        upper_z_top = snap_to_grid(stair_enclosure_roof_z + 0.4)
        has_upper = (upper_z_top - mid_z2) > 2

        if not has_upper:
            # No upper mesh — extend middle to the top
            mid_z2 = upper_z_top

        dz = round(mid_z2 - mid_z1, 3)
        fds_array.append(
            f"&MESH ID='Stair Mesh_Middle{idx}', IJK={round(dx/cell_size)},{round(dy/cell_size)},{round(dz/cell_size)}, XB={x1},{x2},{y1},{y2},{mid_z1},{mid_z2}/"
        )

        # Upper mesh: z+wall_height to stair_enclosure_roof_z+0.4 (coarse 0.2m)
        if has_upper:
            upper_z1 = mid_z2
            dz = round(upper_z_top - upper_z1, 3)
            fds_array.append(
                f"&MESH ID='Stair Mesh_Upper{idx}', IJK={round(dx/coarse_cell)},{round(dy/coarse_cell)},{round(dz/coarse_cell)}, XB={x1},{x2},{y1},{y2},{upper_z1},{upper_z_top}/"
            )

        # Mesh vent at ZMAX of the topmost stair mesh
        top_z = upper_z_top if has_upper else mid_z2
        top_label = "Upper" if has_upper else "Middle"
        fds_array.append(
            f"&VENT ID='Mesh Vent: Stair Mesh_{top_label}{idx} [ZMAX]', SURF_ID='OPEN', XB={x1},{x2},{y1},{y2},{top_z},{top_z}/"
        )

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

        # Skip leakage-only doors — they don't get holes
        role = door_roles.get(door_id, "")
        if role == "leakage":
            continue

        deltaX = abs(points[1]["x"] - points[0]["x"])
        deltaY = abs(points[1]["y"] - points[0]["y"])
        z1 = z - 0.001  # offset from mesh ZMIN boundary
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
        ctrl_suffix = ""
        if scenario_type != "none" and role in ROLE_TO_CTRL_ID:
            ctrl_suffix = f", CTRL_ID='{ROLE_TO_CTRL_ID[role]}'"

        role_label = "Always Open" if role == "always_open" else (role.capitalize() if role else f"door{idx}")
        fds_line = f"&HOLE ID='{role_label} Door Hole', XB ={x1},{x2},{y1},{y2},{z1},{z2}{ctrl_suffix}/"
        line_array.append(fds_line)
    return line_array


def generate_door_leakage_vents(door, door_index, z, door_height=2.1, cell_size=0.1, seal_type="non-smoke-sealed", wall_thickness=0.2):
    """Generate &VENT + &HVAC LEAK lines for a leakage-only door.

    Follows the original Python exe logic from door_leakages.py:
    - 4 pairs of vents (top, bottom, left, right) on each face of the wall
    - Vent 1 on one face, Vent 2 on the opposite face (offset by wall_thickness)
    - Connected by HVAC LEAK lines
    - Gap sizes depend on seal type
    """
    points = door["points"]
    x1 = points[0]["x"]
    x2 = points[1]["x"]
    y1 = points[0]["y"]
    y2 = points[1]["y"]
    z1 = z
    z2 = z + door_height

    x_delta = abs(x2 - x1)
    y_delta = abs(y2 - y1)
    door_width = round(max(x_delta, y_delta), 5)

    if seal_type == "smoke-sealed":
        bottom_gap = 0.003
        other_gaps = 0.00035
        prefix = "smoke_sealed"
    else:
        bottom_gap = 0.01
        other_gaps = 0.004
        prefix = "nonsmoke_sealed"

    door_name = f"{prefix}_door{door_index}"
    is_smoke_sealed = seal_type == "smoke-sealed"
    wt = wall_thickness

    # Determine vent positions based on door orientation
    # Vent 1 sits on the door line face, Vent 2 is offset by wall_thickness to the other face
    if x_delta > y_delta:
        # Door extends in X — wall is thin in Y, vents on Y faces
        # Wall extends negative Y: from y1-wt to y1. Vent 1 at y1, Vent 2 at y1 - wt
        y1_v2 = round(y1 - wt, 5)
        top_coords_1 = f"{x1},{x2},{y1},{y1},{round(z1 + door_height - cell_size, 5)},{z2}"
        top_coords_2 = f"{x1},{x2},{y1_v2},{y1_v2},{round(z1 + door_height - cell_size, 5)},{z2}"
        bottom_coords_1 = f"{x1},{x2},{y1},{y1},{z1},{round(z1 + cell_size, 5)}"
        bottom_coords_2 = f"{x1},{x2},{y1_v2},{y1_v2},{z1},{round(z1 + cell_size, 5)}"
        left_coords_1 = f"{x1},{round(x1 + cell_size, 5)},{y1},{y1},{round(z1 + cell_size, 5)},{round(z1 + door_height - cell_size, 5)}"
        left_coords_2 = f"{x1},{round(x1 + cell_size, 5)},{y1_v2},{y1_v2},{round(z1 + cell_size, 5)},{round(z1 + door_height - cell_size, 5)}"
        right_coords_1 = f"{round(x2 - cell_size, 5)},{x2},{y1},{y1},{round(z1 + cell_size, 5)},{round(z1 + door_height - cell_size, 5)}"
        right_coords_2 = f"{round(x2 - cell_size, 5)},{x2},{y1_v2},{y1_v2},{round(z1 + cell_size, 5)},{round(z1 + door_height - cell_size, 5)}"
    else:
        # Door extends in Y — wall is thin in X, vents on X faces
        # Vent 1 at x1, Vent 2 at x1 + wt (opposite face)
        x1_v2 = round(x1 + wt, 5)
        top_coords_1 = f"{x1},{x1},{y1},{y2},{round(z1 + door_height - cell_size, 5)},{z2}"
        top_coords_2 = f"{x1_v2},{x1_v2},{y1},{y2},{round(z1 + door_height - cell_size, 5)},{z2}"
        bottom_coords_1 = f"{x1},{x1},{y1},{y2},{z1},{round(z1 + cell_size, 5)}"
        bottom_coords_2 = f"{x1_v2},{x1_v2},{y1},{y2},{z1},{round(z1 + cell_size, 5)}"
        left_coords_1 = f"{x1},{x1},{y1},{round(y1 + cell_size, 5)},{round(z1 + cell_size, 5)},{round(z1 + door_height - cell_size, 5)}"
        left_coords_2 = f"{x1_v2},{x1_v2},{y1},{round(y1 + cell_size, 5)},{round(z1 + cell_size, 5)},{round(z1 + door_height - cell_size, 5)}"
        right_coords_1 = f"{x1},{x1},{round(y2 - cell_size, 5)},{y2},{round(z1 + cell_size, 5)},{round(z1 + door_height - cell_size, 5)}"
        right_coords_2 = f"{x1_v2},{x1_v2},{round(y2 - cell_size, 5)},{y2},{round(z1 + cell_size, 5)},{round(z1 + door_height - cell_size, 5)}"

    lines = []
    sides = [
        ("Top", top_coords_1, top_coords_2, round(door_width * other_gaps, 6)),
        ("Bottom", bottom_coords_1, bottom_coords_2, round(door_width * bottom_gap, 6)),
        ("Left", left_coords_1, left_coords_2, round(door_height * other_gaps, 6)),
        ("Right", right_coords_1, right_coords_2, round(door_height * other_gaps, 6)),
    ]

    for side_name, coords_1, coords_2, area in sides:
        vent1_id = f"Door_{door_name}_{side_name.lower()} vent 1"
        vent2_id = f"Door_{door_name}_{side_name.lower()} vent 2"

        lines.append(f"&VENT ID='{vent1_id}', SURF_ID='INERT', XB={coords_1}, RGB=200,200,200 / {door_name}, {side_name} Vent 1")

        if not is_smoke_sealed:
            lines.append(f"&VENT ID='{vent2_id}', SURF_ID='INERT', XB={coords_2}, RGB=200,200,200 / {door_name}, {side_name} Vent 2")

        hvac_vent2 = "AMBIENT" if is_smoke_sealed else f"Door_{door_name}_{side_name.lower()} vent 2"
        lines.append(f"&HVAC ID='Door_{door_name}_{side_name.lower()} leak', TYPE_ID='LEAK', VENT_ID='{vent1_id}', VENT2_ID='{hvac_vent2}', AREA={area}, LEAK_ENTHALPY=.TRUE. / {door_name} {side_name.lower()} leak")
        lines.append("")

    return lines


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

def fire_ramp(growth_rate_name="medium", custom_alpha=None, hrr_kw=1000.0, sim_end_time=300):
    """Generate t-squared fire ramp lines.

    Growth rate alpha values (kW/s^2):
    - slow: 0.00293
    - medium: 0.01172
    - fast: 0.04689
    - ultra_fast: 0.1876
    """
    alpha_map = {
        "slow": 0.00293,
        "medium": 0.01172,
        "fast": 0.04689,
        "ultra_fast": 0.1876,
    }
    alpha = custom_alpha if custom_alpha else alpha_map.get(growth_rate_name, 0.01172)

    # Time to reach max HRR: Q = alpha * t^2, so t = sqrt(Q/alpha)
    import math
    t_max = math.sqrt(hrr_kw / alpha)

    # Generate ramp points: t-squared growth from 0 to t_max
    ramp_lines = []
    # Start at t=0, F=0
    ramp_lines.append(f"&RAMP ID='Fire_RAMP_Q', T=0.0, F=0.0/")

    # Generate intermediate points every 10 seconds during growth
    t = 10.0
    while t < t_max:
        f_val = round((alpha * t * t) / hrr_kw, 4)
        ramp_lines.append(f"&RAMP ID='Fire_RAMP_Q', T={round(t, 1)}, F={f_val}/")
        t += 10.0

    # At t_max, F=1.0 (full power)
    ramp_lines.append(f"&RAMP ID='Fire_RAMP_Q', T={round(t_max, 1)}, F=1.0/")
    # Maintain full power until end
    ramp_lines.append(f"&RAMP ID='Fire_RAMP_Q', T={round(float(sim_end_time), 1)}, F=1.0/")

    return ramp_lines

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

def find_fire_obstruction(elements, z, fire_dimension=1.4, fire_height_above_floor=0.5, fire_base=0.0):
    fires = [ f for f in elements if f["comments"] == "fire"]
    array = []
    for fire in fires:
        points = fire['points'][0]
        fire_x = points["x"]
        fire_y = points["y"]
        array.append('/n'.join(Fire_Obstruction(fire_dimension, fire_height_above_floor, fire_base, fire_x, fire_y, z)))
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


def find_inlet_mesh_pushback(mesh_points, inlet_points, pushback_distance=1.0):
    """Determine which mesh face to push back for an inlet opening.

    Matches the exe logic: determines inlet orientation (which axis it spans),
    then only considers mesh faces perpendicular to the inlet. Pushes back
    the nearest perpendicular face by pushback_distance.

    Args:
        mesh_points: two corner points of the mesh rect [{"x","y"}, {"x","y"}]
        inlet_points: two points of the inlet line [{"x","y"}, {"x","y"}]
        pushback_distance: how far to push back the mesh face (default 1.0m)

    Returns:
        dict with "face" (xmin/xmax/ymin/ymax) and "distance"
    """
    xs = [p["x"] for p in mesh_points]
    ys = [p["y"] for p in mesh_points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)

    inlet_mid_x = (inlet_points[0]["x"] + inlet_points[1]["x"]) / 2
    inlet_mid_y = (inlet_points[0]["y"] + inlet_points[1]["y"]) / 2

    # Determine inlet orientation: which axis does it span?
    inlet_dx = abs(inlet_points[1]["x"] - inlet_points[0]["x"])
    inlet_dy = abs(inlet_points[1]["y"] - inlet_points[0]["y"])

    if inlet_dx > inlet_dy:
        # Inlet spans X (horizontal) → push perpendicular Y faces
        distances = {
            "ymin": abs(inlet_mid_y - ymin),
            "ymax": abs(inlet_mid_y - ymax),
        }
    else:
        # Inlet spans Y (vertical) → push perpendicular X faces
        distances = {
            "xmin": abs(inlet_mid_x - xmin),
            "xmax": abs(inlet_mid_x - xmax),
        }

    closest_face = min(distances, key=distances.get)
    return {"face": closest_face, "distance": pushback_distance}


def create_inlet_opening(inlet_element, config, z, wall_height, wall_thickness, inlet_number=1):
    """Generate a HOLE for an inlet opening at fire floor level.

    The inlet opening is centered on the inlet line midpoint with configurable
    width and height. Defaults match the original exe: 1.8m wide, 0.8m high.
    """
    points = inlet_element["points"]
    x1 = points[0]["x"]
    y1 = points[0]["y"]
    x2 = points[1]["x"]
    y2 = points[1]["y"]

    opening_width = config.get("openingWidth", 1.8)
    opening_height = config.get("openingHeight", 0.8)
    opening_base = config.get("openingBase", 0.0)

    dx = abs(x2 - x1)
    dy = abs(y2 - y1)

    # Inlet midpoint
    mid_x = (x1 + x2) / 2
    mid_y = (y1 + y2) / 2
    half_w = opening_width / 2

    # Offset Z from mesh boundaries facing ambient (FDS requirement)
    hole_z1 = round(z + opening_base, 4)
    hole_z2 = round(z + opening_base + opening_height, 4)
    if opening_base == 0:
        hole_z1 = round(hole_z1 - 0.001, 4)  # offset from mesh ZMIN
    if abs((opening_base + opening_height) - wall_height) < 0.01:
        hole_z2 = round(hole_z2 + 0.001, 4)  # offset from mesh ZMAX

    # HOLE cuts through the wall, centered on inlet midpoint
    if dx > dy:
        # Horizontal inlet: width along X, depth through wall in Y
        hole_xb = f"{round(mid_x - half_w, 2)},{round(mid_x + half_w, 2)},{round(mid_y - 0.2, 2)},{round(mid_y + 0.2, 2)},{hole_z1},{hole_z2}"
    else:
        # Vertical inlet: width along Y, depth through wall in X
        hole_xb = f"{round(mid_x - 0.2, 2)},{round(mid_x + 0.2, 2)},{round(mid_y - half_w, 2)},{round(mid_y + half_w, 2)},{hole_z1},{hole_z2}"

    return [f"&HOLE ID='Inlet Opening {inlet_number}', XB={hole_xb}/"]


def _point_in_polygon(px, py, polygon):
    """Ray casting point-in-polygon test."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _min_distance_to_polygon(px, py, polygon):
    """Minimum distance from point to any edge of the polygon."""
    min_dist = float('inf')
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        # Distance from point to line segment
        dx, dy = x2 - x1, y2 - y1
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq == 0:
            dist = ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
        else:
            t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
            proj_x = x1 + t * dx
            proj_y = y1 + t * dy
            dist = ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5
        min_dist = min(min_dist, dist)
    return min_dist


def _find_enclosing_polygon(fire_x, fire_y, elements):
    """Find the obstruction polygon that contains the fire point."""
    obstructions = [f for f in elements if f["comments"] == "obstruction"]
    for obs in obstructions:
        pts = obs["points"]
        polygon = [(p["x"], p["y"]) for p in pts]
        if _point_in_polygon(fire_x, fire_y, polygon):
            return polygon
    return None


def generate_slice_lines(elements, z, wall_height, door_roles=None, zone_config=None, slice_z_height=2.0):
    """Generate SLCF lines for FDS output.

    Places slice planes through:
    - Fire centre (X and Y)
    - Zone centres (for zones with slices=True): corridor, lobby, fire_room, internal_corridor
    - Door centres (perpendicular axis) for stair and apartment doors
    - Extract/AOV midpoints (X and Y)
    - Z slice at fire floor + slice_z_height

    Args:
        elements: List of element dicts with comments, points, id.
        z: Fire floor Z height (m).
        wall_height: Wall height (m).
        door_roles: Dict mapping door id -> role (stair, apartment, lobby, leakage).
        zone_config: Dict mapping zone id -> {type, name, slices, sensors, points}.
        slice_z_height: Height above fire floor for Z slice (default 2.0m).

    Returns:
        List of SLCF FDS lines.
    """
    if door_roles is None:
        door_roles = {}
    if zone_config is None:
        zone_config = {}

    quantities = ['TEMPERATURE', 'VISIBILITY', 'VELOCITY', 'PRESSURE']
    slices = {'X': set(), 'Y': set(), 'Z': set()}

    # 1. Z slice at fire floor + height
    slices['Z'].add(round(z + slice_z_height, 2))

    # 2. Fire centre (X and Y slices)
    fires = [f for f in elements if f["comments"] == "fire"]
    for fire in fires:
        pts = fire["points"]
        fx = round(pts[0]["x"], 2)
        fy = round(pts[0]["y"], 2)
        slices['X'].add(fx)
        slices['Y'].add(fy)

    # 3. Zone centre slices (only for zones with slices=True)
    for el_id, config in zone_config.items():
        if not config.get("slices", False):
            continue

        pts = config.get("points", None)
        if not pts:
            continue

        xs = [p["x"] if isinstance(p, dict) else p[0] for p in pts]
        ys = [p["y"] if isinstance(p, dict) else p[1] for p in pts]
        mid_x = round((min(xs) + max(xs)) / 2, 2)
        mid_y = round((min(ys) + max(ys)) / 2, 2)
        slices['X'].add(mid_x)
        slices['Y'].add(mid_y)

    # 4. Door centre slices (perpendicular to door orientation)
    doors = [f for f in elements if "door" in f["comments"]]
    for door in doors:
        door_id = str(door.get("id", ""))
        role = door_roles.get(door_id, "")
        if role not in ("stair", "apartment", "lobby"):
            continue

        pts = door["points"]
        if len(pts) < 2:
            continue
        x1, y1 = pts[0]["x"], pts[0]["y"]
        x2, y2 = pts[1]["x"], pts[1]["y"]
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        mid_x = round((x1 + x2) / 2, 2)
        mid_y = round((y1 + y2) / 2, 2)

        if dy > dx:
            # Door extends vertically -> slice perpendicular = PBX
            slices['X'].add(mid_x)
        else:
            # Door extends horizontally -> slice perpendicular = PBY
            slices['Y'].add(mid_y)

    # 5. Extract/AOV midpoint slices (X and Y)
    extracts = [f for f in elements if f["comments"] == "extract"]
    for ext in extracts:
        pts = ext["points"]
        if len(pts) < 2:
            continue
        mid_x = round((pts[0]["x"] + pts[1]["x"]) / 2, 2)
        mid_y = round((pts[0]["y"] + pts[1]["y"]) / 2, 2)
        slices['X'].add(mid_x)
        slices['Y'].add(mid_y)

    # If nothing to slice, return empty
    if not slices['X'] and not slices['Y'] and not slices['Z']:
        return []

    # Generate SLCF lines: 4 quantities per unique position
    lines = []
    axis_map = {'X': 'PBX', 'Y': 'PBY', 'Z': 'PBZ'}
    for axis in ('X', 'Y', 'Z'):
        for pos in sorted(slices[axis]):
            pb = axis_map[axis]
            for q in quantities:
                vector_str = ", VECTOR=.TRUE." if q == "VELOCITY" else ""
                lines.append(f"&SLCF QUANTITY='{q}'{vector_str}, {pb}={pos}/")

    return lines


def generate_zone_sensors(elements, z, zone_config, sensor_heights=None, spacing=0.5):
    """Generate centerline sensors for each assigned zone.

    For each zone, finds the obstruction polygon, computes centerline,
    and places sensors along it with zone-specific naming.
    """
    if not zone_config:
        return []
    if sensor_heights is None:
        sensor_heights = [2.0]

    quantities = ['TEMPERATURE', 'VISIBILITY', 'VELOCITY', 'PRESSURE']
    q_short = {'TEMPERATURE': 'temp', 'VISIBILITY': 'vis', 'VELOCITY': 'vel', 'PRESSURE': 'pres'}

    lines = []
    for el_id, config in zone_config.items():
        # Skip zones with sensors explicitly disabled
        if not config.get("sensors", True):
            continue

        zone_name = config.get("name", "Zone")
        zone_prefix = zone_name.lower().replace(" ", "_")

        # Zone points can come from detected regions (in config) or from element lookup
        pts = config.get("points", None)
        if not pts:
            # Fall back to finding obstruction element by ID
            obs = None
            for el in elements:
                if str(el.get("id", "")) == str(el_id) and el["comments"] == "obstruction":
                    obs = el
                    break
            if not obs:
                continue
            pts = obs["points"]

        xs = [p["x"] if isinstance(p, dict) else p[0] for p in pts]
        ys = [p["y"] if isinstance(p, dict) else p[1] for p in pts]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        delta_x = xmax - xmin
        delta_y = ymax - ymin
        inset = 0.3

        centre_points = []
        if delta_x > delta_y:
            # Long in X — centerline at mid-Y
            y_mid = round((ymin + ymax) / 2, 2)
            x_start = round(xmin + inset, 2)
            x_end = round(xmax - inset, 2)
            num_points = max(1, int((x_end - x_start) / spacing) + 1)
            for i in range(num_points):
                x = round(x_start + i * spacing, 2)
                if x <= x_end:
                    centre_points.append((x, y_mid))
        else:
            # Long in Y — centerline at mid-X
            x_mid = round((xmin + xmax) / 2, 2)
            y_start = round(ymin + inset, 2)
            y_end = round(ymax - inset, 2)
            num_points = max(1, int((y_end - y_start) / spacing) + 1)
            for i in range(num_points):
                y = round(y_start + i * spacing, 2)
                if y <= y_end:
                    centre_points.append((x_mid, y))

        for pt_idx, (x, y) in enumerate(centre_points, start=1):
            for height in sensor_heights:
                sensor_z = round(z + height, 2)
                for quantity in quantities:
                    prefix = q_short[quantity]
                    devc_id = f"{zone_prefix}_{prefix}_{pt_idx}"
                    lines.append(f"&DEVC ID='{devc_id}', QUANTITY='{quantity}', XYZ={x},{y},{sensor_z}/")

    return lines


def generate_sprinkler_lines(elements, z, wall_height):
    """Generate sprinkler DEVC + PROP lines from sprinkler elements.

    Sprinkler positions are computed on the frontend and passed as
    elements with comments='sprinkler'. The backend only converts
    coordinates and writes FDS lines — no auto-placement here.
    """
    sprk_z = round(z + wall_height - 0.2, 2)

    sprinkler_elements = [f for f in elements if f["comments"] == "sprinkler"]
    if not sprinkler_elements:
        return []

    sprinklers = []
    for s in sprinkler_elements:
        pts = s["points"]
        if isinstance(pts, list):
            sprinklers.append((round(pts[0]["x"], 2), round(pts[0]["y"], 2)))
        else:
            sprinklers.append((round(pts["x"], 2), round(pts["y"], 2)))

    lines = [
        "&SPEC ID='WATER VAPOR'/",
        "&PART ID='Water01',",
        "      SPEC_ID='WATER VAPOR',",
        "      DIAMETER=500.0,",
        "      MONODISPERSE=.TRUE.,",
        "      AGE=10.0,",
        "      SAMPLING_FACTOR=1/",
        "&PROP ID='Residential Link BS 9251',",
        "      PART_ID='Water01',",
        "      K_FACTOR=40.0,",
        "      OPERATING_PRESSURE=0.5,",
        "      PARTICLE_VELOCITY=5.0,",
        "      SPRAY_ANGLE=60.0,75.0/",
    ]

    for i, (sx, sy) in enumerate(sprinklers):
        lines.append(f"&DEVC ID='SPRK{i+1}', PROP_ID='Residential Link BS 9251', XYZ={sx},{sy},{sprk_z}, QUANTITY='TIME', SETPOINT=0.0/")

    return lines


def create_extract_shaft(extract_element, config, z, wall_height, stair_enclosure_roof_z, wall_thickness, cell_size=0.2, extract_number=1):
    """Generate FDS lines for an extract shaft: MESH, opening HOLE, top VENT, and optional SURF.

    Returns a list of FDS lines.
    """
    points = extract_element["points"]
    x1 = points[0]["x"]
    y1 = points[0]["y"]
    x2 = points[1]["x"]
    y2 = points[1]["y"]

    shaft_type = config.get("type", "natural")
    shaft_width = config.get("shaftWidth", 0.9)
    shaft_depth = config.get("shaftDepth", 0.9)
    flow_rate = config.get("flowRate", 3.0)
    activation = config.get("activation", "always_open")
    activation_time = config.get("activationTime", None)
    opening_height = config.get("openingHeight", wall_height)  # defaults to full wall height
    opening_base = config.get("openingBase", 0.0)  # height above floor level
    tau_v = config.get("tauV", None)

    dx = abs(x2 - x1)
    dy = abs(y2 - y1)

    lines = []

    # Determine shaft position extending perpendicular from the opening
    # Opening is on the wall; shaft extends outward by shaft_depth
    if dx > dy:
        # Horizontal opening: shaft extends in Y
        shaft_x1 = round(min(x1, x2), 2)
        shaft_x2 = round(max(x1, x2), 2)
        shaft_y1 = round(y1, 2)
        shaft_y2 = round(y1 + shaft_depth, 2)
    else:
        # Vertical opening: shaft extends in X
        shaft_x1 = round(x1, 2)
        shaft_x2 = round(x1 + shaft_depth, 2)
        shaft_y1 = round(min(y1, y2), 2)
        shaft_y2 = round(max(y1, y2), 2)

    # Shaft goes from ground to stair roof level
    shaft_z1 = 0
    shaft_z2 = round(stair_enclosure_roof_z, 1)

    # MESH for the shaft
    ijk_x = max(1, round((shaft_x2 - shaft_x1) / cell_size))
    ijk_y = max(1, round((shaft_y2 - shaft_y1) / cell_size))
    ijk_z = max(1, round((shaft_z2 - shaft_z1) / cell_size))
    shaft_id = f"Extract_Shaft_{extract_number}"
    lines.append(f"&MESH ID='{shaft_id}', IJK={ijk_x},{ijk_y},{ijk_z}, XB={shaft_x1},{shaft_x2},{shaft_y1},{shaft_y2},{shaft_z1},{shaft_z2}/")

    # Opening VENT at corridor level (flat against wall, matching exe approach)
    # The vent sits on the wall face — one dimension collapsed to a plane
    vent_z1 = round(z + opening_base, 2)
    vent_z2 = round(z + opening_base + opening_height, 2)

    ctrl_suffix = ""
    if activation == "timed":
        ctrl_suffix = f", DEVC_ID='Extract_Timer_{extract_number}'"
    elif activation == "sprinkler":
        ctrl_suffix = f", DEVC_ID='Extract_Sprinkler_{extract_number}'"

    if dx > dy:
        # Horizontal opening: vent is flat on Y face
        vent_xb = f"{shaft_x1},{shaft_x2},{shaft_y1},{shaft_y1},{vent_z1},{vent_z2}"
    else:
        # Vertical opening: vent is flat on X face
        vent_xb = f"{shaft_x1},{shaft_x1},{shaft_y1},{shaft_y2},{vent_z1},{vent_z2}"

    # Mechanical extract: define SURF before the VENT that references it
    if shaft_type == "mechanical":
        extract_surf_id = f"Extract_{extract_number}"
        tau_v_str = f", TAU_V={tau_v}" if tau_v is not None else ""
        lines.append(f"&SURF ID='{extract_surf_id}', VOLUME_FLOW={flow_rate}{tau_v_str}, RGB=26,128,26/")
        lines.append(f"&VENT ID='Extract Opening {extract_number}', SURF_ID='{extract_surf_id}', XB={vent_xb}{ctrl_suffix}/")
    else:
        lines.append(f"&VENT ID='Extract Opening {extract_number}', SURF_ID='OPEN', XB={vent_xb}{ctrl_suffix}/")

    # Top: HOLE through the roof slab + mesh vent (OPEN) at ZMAX
    roof_z = round(stair_enclosure_roof_z, 2)
    lines.append(f"&HOLE ID='Extract Roof Opening {extract_number}', XB={shaft_x1},{shaft_x2},{shaft_y1},{shaft_y2},{round(roof_z - 0.4, 2)},{round(roof_z + 0.4, 2)}/")
    lines.append(f"&VENT ID='Mesh Vent: {shaft_id} [ZMAX]', SURF_ID='OPEN', XB={shaft_x1},{shaft_x2},{shaft_y1},{shaft_y2},{shaft_z2},{shaft_z2}/")

    # Activation controls
    if activation == "timed" and activation_time is not None:
        t = float(activation_time)
        lines.append(f"&DEVC ID='Extract_Timer_{extract_number}', QUANTITY='TIME', XYZ=0,0,0, SETPOINT={t}/")
    elif activation == "sprinkler":
        mid_x = round((shaft_x1 + shaft_x2) / 2, 2)
        mid_y = round((shaft_y1 + shaft_y2) / 2, 2)
        lines.append(f"&DEVC ID='Extract_Sprinkler_{extract_number}', PROP_ID='Extract_Link_{extract_number}', XYZ={mid_x},{mid_y},{round(z + wall_height - 0.1, 2)}/")
        lines.append(f"&PROP ID='Extract_Link_{extract_number}', QUANTITY='LINK TEMPERATURE', RTI=50, ACTIVATION_TEMPERATURE=68.0/")

    return lines


def compute_corridor_centerline(obstruction_points, spacing=0.5, inset=0.4):
    """Compute centerline points along the corridor obstruction polygon.

    For a simple rectangular-ish corridor, finds the long axis and places
    points at `spacing` intervals, inset from walls by `inset` metres.
    Returns list of [x, y] points.
    """
    xs = [p["x"] for p in obstruction_points]
    ys = [p["y"] for p in obstruction_points]

    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)

    delta_x = xmax - xmin
    delta_y = ymax - ymin

    centre_points = []
    if delta_x > delta_y:
        # Long corridor along X — centerline at mid-Y
        y_mid = round((ymin + ymax) / 2, 2)
        x_start = round(xmin + inset, 2)
        x_end = round(xmax - inset, 2)
        num_points = max(1, int((x_end - x_start) / spacing) + 1)
        for i in range(num_points):
            x = round(x_start + i * spacing, 2)
            if x <= x_end:
                centre_points.append([x, y_mid])
    else:
        # Long corridor along Y — centerline at mid-X
        x_mid = round((xmin + xmax) / 2, 2)
        y_start = round(ymin + inset, 2)
        y_end = round(ymax - inset, 2)
        num_points = max(1, int((y_end - y_start) / spacing) + 1)
        for i in range(num_points):
            y = round(y_start + i * spacing, 2)
            if y <= y_end:
                centre_points.append([x_mid, y])

    return centre_points


def generate_corridor_sensor_devcs(elements, z, sensor_heights):
    """Generate DEVC lines from sensorTree elements placed by the frontend.

    The frontend computes centerline positions and stores them as sensorTree
    elements. This function reads those positions and generates FDS DEVC lines.
    """
    quantities = ["TEMPERATURE", "PRESSURE", "VISIBILITY", "VELOCITY"]
    q_short = {"TEMPERATURE": "temp", "PRESSURE": "pres", "VISIBILITY": "vis", "VELOCITY": "vel"}

    lines = []

    sensor_trees = [el for el in elements if el.get("comments") == "sensorTree"]
    print(f"[SENSOR] Found {len(sensor_trees)} sensorTree elements")
    for i, st in enumerate(sensor_trees[:5]):
        print(f"[SENSOR]   {i}: zoneName={st.get('zoneName', 'MISSING')} keys={list(st.keys())}")
    if not sensor_trees:
        return lines

    # Group sensors by zone name to reset numbering per zone
    zone_groups = {}
    for tree in sensor_trees:
        zone_name = tree.get("zoneName", "corridor")
        zone_key = zone_name.lower().replace(" ", "_")
        if zone_key not in zone_groups:
            zone_groups[zone_key] = []
        zone_groups[zone_key].append(tree)

    for zone_key, trees in zone_groups.items():
        for pt_idx, tree in enumerate(trees, start=1):
            point = tree["points"][0]
            x = round(point["x"], 2)
            y = round(point["y"], 2)
            for height in sensor_heights:
                sensor_z = round(z + height, 2)
                for quantity in quantities:
                    prefix = q_short[quantity]
                    devc_id = f"{zone_key}_{prefix}_{pt_idx}"
                    lines.append(f"&DEVC ID='{devc_id}', QUANTITY='{quantity}', XYZ={x},{y},{sensor_z}/")

    return lines


def generate_fsa_sensor_devcs(elements, z, fsa_sensor_heights):
    """Generate DEVC lines from fsaSensor elements placed by the frontend.

    FSA sensors are placed at specific distances (2m, 4m, 15m) along the walking
    route from apartment door to stair door. All 4 sensor types are generated.
    """
    quantities = ["TEMPERATURE", "PRESSURE", "VISIBILITY", "VELOCITY"]
    q_short = {"TEMPERATURE": "temp", "PRESSURE": "pres", "VISIBILITY": "vis", "VELOCITY": "vel"}

    lines = []

    fsa_sensors = [el for el in elements if el.get("comments") == "fsaSensor"]
    print(f"[FSA SENSOR] Found {len(fsa_sensors)} fsaSensor elements")
    if not fsa_sensors:
        return lines

    for sensor in fsa_sensors:
        point = sensor["points"][0]
        x = round(point["x"], 2)
        y = round(point["y"], 2)
        fsa_distance = sensor.get("fsaDistance", "?")

        for height in fsa_sensor_heights:
            sensor_z = round(z + height, 2)
            for quantity in quantities:
                prefix = q_short[quantity]
                devc_id = f"corridor_FSA_{prefix}_{fsa_distance}m"
                if len(fsa_sensor_heights) > 1:
                    devc_id += f"_h{height}"
                lines.append(f"&DEVC ID='{devc_id}', QUANTITY='{quantity}', XYZ={x},{y},{sensor_z}/")

    return lines


def generate_sensor_devcs_from_elements(elements, z, sensor_heights, fsa_sensor_heights=None):
    """Generate all DEVC lines from frontend-placed sensor elements.

    Combines sensorTree (corridor/zone centerline) and fsaSensor (FSA path)
    elements. Positions are already in the correct coordinate space after
    the element pipeline transforms them.
    """
    lines = generate_corridor_sensor_devcs(elements, z, sensor_heights)
    fsa_heights = fsa_sensor_heights if fsa_sensor_heights else [1.5]
    lines += generate_fsa_sensor_devcs(elements, z, fsa_heights)
    return lines


def testFunction(elements, z, wall_height, wall_thickness, stair_height, px_per_m, fire_floor, total_floors, stair_enclosure_roof_z,
                 scenario_type="MOE", sim_end_time=300, door_openings=None, door_leakages_enabled=False, door_leakage_config=None, door_roles=None,
                 landing_roles=None, landing_up_side=None, obstruction_transparency=None,
                 aov_mode="always_open", aov_activation_time=None, stair_style="overlapping", extract_config=None, inlet_config=None,
                 zone_config=None, include_sensors=True, corridor_sensor_heights=None, stair_sensor_heights=None, fsa_sensor_heights=None, is_sprinklered=True,
                 fire_hrr=1000.0, fire_dimension=1.4, fire_height_above_floor=0.5, fire_base=0.0,
                 fire_type="growing", fire_growth_rate="medium", fire_custom_alpha=None,
                 slice_z_height=2.0):
    if door_openings is None:
        door_openings = {}
    if door_leakage_config is None:
        door_leakage_config = {}
    if door_roles is None:
        door_roles = {}
    if obstruction_transparency is None:
        obstruction_transparency = {}
    if extract_config is None:
        extract_config = {}
    if inlet_config is None:
        inlet_config = {}
    if zone_config is None:
        zone_config = {}

    # 1. Simulation header
    header_lines = sim_header(chid='model', sim_end_time=sim_end_time)

    # 2. Materials/Surfaces
    fds_array = header_lines + [header]

    cell_size = 0.1

    # find bottom left point as origin and change all points to be relative to that
    origin = returnOrigin(elements)
    elements = makeElementsRelativeToOrigin(elements, origin)
    elements = convertElPointsToCoords(elements, px_per_m)

    # Flip Y axis: canvas Y=0 is top, FDS Y=0 is bottom
    all_ys = [p["y"] for el in elements for p in el["points"]]
    max_y = max(all_ys) if all_ys else 0
    for el in elements:
        for p in el["points"]:
            p["y"] = round(max_y - p["y"], 5)

    # 3. Meshes (with inlet pushback if inlets present)
    inlets = [f for f in elements if f["comments"] == "inlet"]
    fds_array = create_mesh(comments='mesh', elements=elements, cell_size=cell_size, px_per_m=px_per_m, z=z, fds_array=fds_array, wall_height=wall_height, inlets=inlets if inlets else None, inlet_config=inlet_config)

    # 3a. Stair meshes (Lower 0.2m / Middle 0.1m / Upper 0.2m) + mesh vent at ZMAX
    fds_array = create_stair_meshes(elements, cell_size, px_per_m, z, wall_height, stair_enclosure_roof_z, fds_array)

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

    # 6. Door holes (with CTRL_ID when scenario_type is set) — skips leakage doors
    door_scenario = scenario_type if scenario_type else "none"
    door_array = add_door_holes_to_fds(elements, z, wall_height, wall_thickness, fds_array, door_height=2.1, scenario_type=door_scenario, door_roles=door_roles)
    fds_array = add_array_to_fds_array(door_array, fds_array)

    # 6a. Leakage-only doors: generate VENT + HVAC LEAK lines
    doors = [f for f in elements if "door" in f["comments"]]
    for idx, door in enumerate(doors):
        door_id = str(door.get("id", idx))
        role = door_roles.get(door_id, "")
        if role == "leakage":
            config = door_leakage_config.get(door_id, {})
            seal = config.get("sealType", "non-smoke-sealed")
            leakage_lines = generate_door_leakage_vents(door, door_index=idx, z=z, door_height=2.1, cell_size=0.1, seal_type=seal, wall_thickness=wall_thickness)
            fds_array = add_array_to_fds_array(leakage_lines, fds_array)

    # 7. Fire obstruction & surface
    fire_area = fire_dimension * fire_dimension
    is_steady = (fire_type == "steady_state")
    fire_surface_array = fire_surface(hrr_kw=fire_hrr, fire_area=fire_area, is_steady_state=is_steady)
    fds_array = add_array_to_fds_array(fire_surface_array, fds_array)
    fds_array = add_array_to_fds_array(find_fire_obstruction(elements, z, fire_dimension, fire_height_above_floor, fire_base), fds_array)
    if not is_steady:
        ramp_lines = fire_ramp(growth_rate_name=fire_growth_rate, custom_alpha=fire_custom_alpha, hrr_kw=fire_hrr, sim_end_time=sim_end_time)
        fds_array = add_array_to_fds_array(ramp_lines, fds_array)

    # 7a. Sprinklers
    if is_sprinklered:
        sprinkler_lines = generate_sprinkler_lines(elements, z, wall_height)
        fds_array = add_array_to_fds_array(sprinkler_lines, fds_array)

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

    # 9d. Extract shafts
    extracts = [f for f in elements if f["comments"] == "extract"]
    for idx, extract in enumerate(extracts):
        ext_id = str(extract.get("id", idx))
        config = extract_config.get(ext_id, {})
        shaft_lines = create_extract_shaft(extract, config, z, wall_height, stair_enclosure_roof_z, wall_thickness, extract_number=idx + 1)
        fds_array = add_array_to_fds_array(shaft_lines, fds_array)

    # 9e. Inlet openings
    inlets = [f for f in elements if f["comments"] == "inlet"]
    for idx, inlet in enumerate(inlets):
        inlet_id = str(inlet.get("id", idx))
        config = inlet_config.get(inlet_id, {})
        inlet_lines = create_inlet_opening(inlet, config, z, wall_height, wall_thickness, inlet_number=idx + 1)
        fds_array = add_array_to_fds_array(inlet_lines, fds_array)

    # 10. Sensors — positions are computed on the frontend and sent as
    #     sensorTree / fsaSensor elements.  The backend only converts their
    #     pixel coordinates to metres and writes the DEVC lines.
    #     Do NOT recompute positions here (coordinate-system divergence).
    has_frontend_sensors = any(f["comments"] in ("sensorTree", "fsaSensor") for f in elements)
    if include_sensors and has_frontend_sensors:
        sensor_heights = corridor_sensor_heights if corridor_sensor_heights else [2.0]
        sensor_lines = generate_sensor_devcs_from_elements(elements, z, sensor_heights, fsa_sensor_heights=fsa_sensor_heights)
        fds_array = add_array_to_fds_array(sensor_lines, fds_array)
    elif include_sensors:
        # Fallback: no frontend sensors sent — use legacy backend computation
        sensor_heights = corridor_sensor_heights if corridor_sensor_heights else [2.0]
        sensor_lines = generate_corridor_sensor_devcs(elements, z, sensor_heights)
        fds_array = add_array_to_fds_array(sensor_lines, fds_array)
        if zone_config:
            zone_sensor_lines = generate_zone_sensors(elements, z, zone_config, sensor_heights=corridor_sensor_heights or [2.0])
            fds_array = add_array_to_fds_array(zone_sensor_lines, fds_array)
        fsa_heights = fsa_sensor_heights if fsa_sensor_heights else [1.5]
        fsa_lines = generate_fsa_sensor_devcs(elements, z, fsa_heights)
        fds_array = add_array_to_fds_array(fsa_lines, fds_array)

    # 11. Slice planes (SLCF)
    slice_lines = generate_slice_lines(elements, z, wall_height, door_roles=door_roles,
                                        zone_config=zone_config, slice_z_height=slice_z_height)
    fds_array = add_array_to_fds_array(slice_lines, fds_array)

    # 12. TAIL
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

