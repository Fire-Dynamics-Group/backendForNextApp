import math

# TODO: add upper landings and stairs
def convert_points_to_dict(points):
    try:
        return [{"x": point.x, "y": point.y} for point in points]
    except:
        return points

def convert_canvas_points_to_fds(points, px_per_m):
    if __name__ != '__main__':
        points = convert_points_to_dict(points)
    # TODO: incorporate scale before sending co-ordinates
    points = [{"x": p["x"]/px_per_m, "y":p["y"]/px_per_m} for p in points]
    return points

# TODO: landings to be guaged from being closer to stair door; or be marked on drawing
def setup_landings(comments, fire_floor, total_floors, elements, px_per_m, z, stair_enclosure_roof_z, lowest_floor_landing_z=0, lowest_floor=0, landing_roles=None, landing_up_side=None, stair_style="overlapping"):
    array = []
    try:
        landings = [ f for f in elements if f.comments == comments]
        if landings:
            fire_floor_landing_points = landings[0].points
            fire_floor_halflanding_points = landings[-1].points
        else:
            # Handle the case where no elements match
            # For example, return an empty list or raise an exception
            print("no elements match")
            return []
    except:
        # landings = [ f for f in elements if f["comments"] == comments]
        filtered_elements = [f for f in elements if f["comments"] == comments]
        if filtered_elements:
            # output = filtered_elements[0]
            # points = output["points"]
            landings = filtered_elements
        else:
            # Handle the case where no elements match
            # For example, return an empty list or raise an exception
            print("no elements match")
            return []  
        # should be a check for 2 landings at frontend
        fire_floor_landing_points = landings[0]["points"]
        fire_floor_halflanding_points = landings[1]["points"]

    # Use explicit roles if provided, otherwise fall back to array order
    if landing_roles:
        floor_landing = next((l for l in landings if landing_roles.get(str(l.id if hasattr(l, 'id') else l.get('id', ''))) == 'floor'), None)
        half_landing = next((l for l in landings if landing_roles.get(str(l.id if hasattr(l, 'id') else l.get('id', ''))) == 'half'), None)
        if floor_landing and half_landing:
            try:
                fire_floor_landing_points = floor_landing.points
                fire_floor_halflanding_points = half_landing.points
            except:
                fire_floor_landing_points = floor_landing["points"]
                fire_floor_halflanding_points = half_landing["points"]

    # if __name__ != '__main__':
    # else:

    num_upper_landings = total_floors - fire_floor + 1 # perhaps need z of top floor? or add one on and use stair roof
    num_lower_landings = fire_floor - lowest_floor

    # convert to 4 corner points
    # # convert to fds coordinates
    # fire_floor_landing_points = convert_canvas_points_to_fds(fire_floor_landing_points, px_per_m)
    # fire_floor_halflanding_points = convert_canvas_points_to_fds(fire_floor_halflanding_points, px_per_m)
    z_list = []
    try:
        z_diff_lower = round((z - lowest_floor_landing_z) / num_lower_landings, 2)
    except:
        z_diff_lower = 0
    try:
        z_diff_higher = round((stair_enclosure_roof_z - z) / (num_upper_landings), 2)
    except:
        z_diff_higher = 0
    # lower z's
    lower_z = [lowest_floor_landing_z + (x * z_diff_lower) for x in range(num_lower_landings)]
    lower_z_halflanding = [round(x + 0.5 * z_diff_lower, 3) for x in lower_z]
    # upper z's
    upper_z = [z + (x * z_diff_higher) for x in range(num_upper_landings)] # includes top floor!
    upper_z_halflanding = [round(x + 0.5 * z_diff_higher, 3) for x in upper_z[:-1]]
    z_landing = lower_z + upper_z
    z_halflanding = lower_z_halflanding + upper_z_halflanding
    # LATER: allow for multiple stairs!!
    # landing_points = fire_floor_landing_points
    landing_x1 = fire_floor_landing_points[0]['x']
    landing_x2 = fire_floor_landing_points[1]['x']
    landing_y1 = fire_floor_landing_points[0]['y']
    landing_y2 = fire_floor_landing_points[1]['y']

    halflanding_x1 = fire_floor_halflanding_points[0]['x']
    halflanding_x2 = fire_floor_halflanding_points[1]['x']
    halflanding_y1 = fire_floor_halflanding_points[0]['y']
    halflanding_y2 = fire_floor_halflanding_points[1]['y']
    # half_landing_points = fire_floor_landing_points[-1]
    ''' assume first rect is landing adn second is half landing 
        return fds lines
    '''
    num_steps = 8
    delta_x1 = abs(landing_x1 - halflanding_x1)
    delta_y1 = abs(landing_y1 - halflanding_y1)
    if delta_x1 > delta_y1:
        stair_direction = 'x'
        delta_interlandings = max(landing_x1 - halflanding_x2, halflanding_x1 - landing_x2)
        # Use the overlap of both landings' y ranges so steps fit within both
        common_y1 = max(landing_y1, halflanding_y1)
        common_y2 = min(landing_y2, halflanding_y2)
        stair1_y1_list = [common_y1 for x in range(num_steps)]
        stair1_y2_list = [common_y2 for x in range(num_steps)]
        # find stair direction lists
        '''
            start at landing go to half landing
        '''
        # Determine stair direction: use landing_up_side if provided, else heuristic
        if landing_up_side == 'right':
            go_plus_x = True
        elif landing_up_side == 'left':
            go_plus_x = False
        else:
            go_plus_x = landing_x1 - halflanding_x2 < halflanding_x1 - landing_x2

        if stair_style == "individual":
            # Individual treads: each step is one tread wide, placed side by side
            tread = math.ceil(100*(delta_interlandings / num_steps)) / 100
            if go_plus_x:
                # STEP1: bottom step at landing edge, top step at half landing edge
                stair_x1_list = [landing_x2 + tread*x for x in range(num_steps)]
                stair_x2_list = [landing_x2 + tread*(x+1) for x in range(num_steps)]
                # STEP2: bottom step at half landing edge, top step at landing edge
                stair2_x1_list = [halflanding_x1 - tread*(x+1) for x in range(num_steps)]
                stair2_x2_list = [halflanding_x1 - tread*x for x in range(num_steps)]
            else:
                stair_x1_list = [landing_x1 - tread*(x+1) for x in range(num_steps)]
                stair_x2_list = [landing_x1 - tread*x for x in range(num_steps)]
                stair2_x1_list = [halflanding_x2 + tread*x for x in range(num_steps)]
                stair2_x2_list = [halflanding_x2 + tread*(x+1) for x in range(num_steps)]
        else:
            # Overlapping style: top step (step 7) overlaps the destination landing,
            # bottom step (step 0) just protrudes from the source landing.
            tread = math.ceil(100*(delta_interlandings / (num_steps - 1))) / 100
            if go_plus_x:
                # STEP1: top step (7) at half landing, bottom step (0) near floor landing
                stair_x1_list = [halflanding_x1 - tread*(num_steps-1-x) for x in range(num_steps)]
                stair_x2_list = [halflanding_x2 - tread*(num_steps-1-x) for x in range(num_steps)]
                # STEP2: top step (7) at floor landing, bottom step (0) near half landing
                stair2_x1_list = [landing_x1 + tread*(num_steps-1-x) for x in range(num_steps)]
                stair2_x2_list = [landing_x2 + tread*(num_steps-1-x) for x in range(num_steps)]
            else:
                # STEP1: top step at half landing, bottom step near floor landing
                stair_x1_list = [halflanding_x1 + tread*(num_steps-1-x) for x in range(num_steps)]
                stair_x2_list = [halflanding_x2 + tread*(num_steps-1-x) for x in range(num_steps)]
                # STEP2: top step at floor landing, bottom step near half landing
                stair2_x1_list = [landing_x1 - tread*(num_steps-1-x) for x in range(num_steps)]
                stair2_x2_list = [landing_x2 - tread*(num_steps-1-x) for x in range(num_steps)]

        stair_y_mid_list = [common_y1 + (common_y2 - common_y1)/2 for x in range(num_steps)]
        stair_1_y2_list = stair_y_mid_list
        stair_2_y1_list = stair_y_mid_list
    else:
        stair_direction = 'y'
        delta_interlandings = max(landing_y1 - halflanding_y2, halflanding_y1 - landing_y2)
        # Use the overlap of both landings' x ranges so steps fit within both
        common_x1 = max(landing_x1, halflanding_x1)
        common_x2 = min(landing_x2, halflanding_x2)
        stair_x1_list = [common_x1 for x in range(num_steps)]
        stair_x2_list = [common_x2 for x in range(num_steps)]
        stair_x_mid_list = [common_x1 + (common_x2 - common_x1)/2 for x in range(num_steps)]
        stair_1_x2_list = stair_x_mid_list
        stair_2_x1_list = stair_x_mid_list

        tread = math.ceil(100*(delta_interlandings / num_steps)) / 100

        # Determine stair direction: use landing_up_side if provided, else heuristic
        if landing_up_side == 'bottom':
            go_plus_y = True
        elif landing_up_side == 'top':
            go_plus_y = False
        else:
            go_plus_y = landing_y1 - halflanding_y2 < halflanding_y1 - landing_y2
        if go_plus_y:
            # plus y: STEP1 from landing toward half landing
            stair1_y1_list = [landing_y2 + tread*x for x in range(num_steps)]
            stair1_y2_list = [x + tread*2 for x in stair1_y1_list]
            # STEP2: from half landing toward floor landing
            stair2_y1_list = [halflanding_y1 - tread*(x+2) for x in range(num_steps)]
            stair2_y2_list = [halflanding_y1 - tread*x for x in range(num_steps)]
        else:
            # minus y: STEP1 from landing toward half landing
            stair1_y1_list = [landing_y1 - tread*x for x in range(num_steps)]
            stair1_y2_list = [x - tread*2 for x in stair1_y1_list]
            # STEP2: from half landing toward floor landing
            stair2_y1_list = [halflanding_y2 + tread*x for x in range(num_steps)]
            stair2_y2_list = [halflanding_y2 + tread*(x+2) for x in range(num_steps)]

    # tread = math.ceil(100*(delta_interlandings / 8)) / 100 # diff between landings / 8
    # steps should be halfway of landing expanse i.e. to middle of the landing to the outerside
    step_array = []
    for idx, z_current in enumerate(z_landing):
        output = f"&OBST ID='LANDING', XB = {round(landing_x1, 3)}, {round(landing_x2, 3)}, {round(landing_y1, 3)}, {round(landing_y2, 3)},{round(z_current - 0.2, 3)}, {round(z_current, 3)}, SURF_ID = 'Plasterboard'/"
        array.append(output)


        # loop through landing to half landing
        # # should 
        if idx < len(z_halflanding):
            # height counting current as zero
            height_per_step = math.ceil(100*((z_halflanding[idx] - z_current) / num_steps)) / 100
            for step_num in range(num_steps):
                current_step_z1 = round(z_current + (step_num * height_per_step), 3)
                current_step_z2 = round(z_current + ((step_num + 1) * height_per_step), 3)
                if stair_direction == 'x':
                    s1_x1 = round(stair_x1_list[step_num], 3)
                    s1_x2 = round(stair_x2_list[step_num], 3)
                    s1_y1 = round(stair1_y1_list[step_num], 3)
                    s1_y2 = round(stair_1_y2_list[step_num], 3)
                else:
                    s1_x1 = round(stair_x1_list[step_num], 3)
                    s1_x2 = round(stair_1_x2_list[step_num], 3)
                    s1_y1 = round(stair1_y1_list[step_num], 3)
                    s1_y2 = round(stair1_y2_list[step_num], 3)
                current_step_line = f"&OBST ID='STEP1', XB = {s1_x1}, {s1_x2}, {s1_y1}, {s1_y2},{round(current_step_z1, 3)}, {round(current_step_z2, 3)}, SURF_ID = 'Plasterboard'/"
                array.append(current_step_line)
    for idx, z_current in enumerate(z_halflanding):
        output = f"&OBST ID='HALFLANDING', XB = {round(halflanding_x1, 3)}, {round(halflanding_x2, 3)}, {round(halflanding_y1, 3)}, {round(halflanding_y2, 3)},{round(z_current - 0.2, 3)}, {round(z_current, 3)}, SURF_ID = 'Plasterboard'/"
        array.append(output)

        if idx < len(z_halflanding):
            # height counting current as zero
            height_per_step = math.ceil(100*((z_landing[idx+1] - z_current) / num_steps)) / 100
            for step_num in range(num_steps):
                current_step_z1 = round(z_current + (step_num * height_per_step), 3)
                current_step_z2 = round(z_current + ((step_num + 1) * height_per_step), 3)
                if stair_direction == 'x':
                    s2_x1 = round(stair2_x1_list[step_num], 3)
                    s2_x2 = round(stair2_x2_list[step_num], 3)
                    s2_y1 = round(stair_2_y1_list[step_num], 3)
                    s2_y2 = round(stair1_y2_list[step_num], 3)
                else:
                    s2_x1 = round(stair_2_x1_list[step_num], 3)
                    s2_x2 = round(stair_x2_list[step_num], 3)
                    s2_y1 = round(stair2_y1_list[step_num], 3)
                    s2_y2 = round(stair2_y2_list[step_num], 3)
                current_step_line = f"&OBST ID='STEP2', XB = {s2_x1}, {s2_x2}, {s2_y1}, {s2_y2},{round(current_step_z1, 3)}, {round(current_step_z2, 3)}, SURF_ID = 'Plasterboard'/"
                array.append(current_step_line)
    # also half landing
    # 
    # assume 8 steps between 
    # start at landing; find if pos or negative to half landing
    # step in tread distance; step_heihgt
    '''
    step height depends on height between landing and next half landing etc
    add to fds file
    '''

    return array
    pass

def create_landings_fds_lines():
    pass

if __name__ == '__main__':     
    px_per_m = 33.600380950221385
    from mockData import stairElsTwo
    # setup_landings(
    #                 comments="landing", 
    #                 fire_floor=4, 
    #                 total_floors=7, 
    #                 elements=stairElsTwo, 
    #                 px_per_m=px_per_m,
    #                 z=25, 
    #                 stair_enclosure_roof_z=60
    #                 )
    
    '''
    elementList=[Element(comments='stairObstruction', id=0, points=[Point(x=609.0521531954386, y=915.2423067144568), Point(x=665.630768519605, y=915.2423067144568), Point(x=665.630768519605, y=895.2733836588687), Point(x=695.5841531029872, y=895.2733836588687), Point(x=695.5841531029872, y=1094.9626142147501), Point(x=609.0521531954386, y=1094.9626142147501), Point(x=609.0521531954386, y=915.2423067144568)], type='polyline')] 
    z=3.0 
    wall_height=3.0 
    wall_thickness=0.2 
    stair_height=20.0 
    px_per_m=33.6 
    fire_floor=1 
    total_floors=8 
    stair_enclosure_roof_z=25.0
    '''
    setup_landings(
                    comments="landing", 
                    fire_floor=3, 
                    total_floors=6, 
                    elements=stairElsTwo,
                    # elements=[{"comments":"landing","points":[{"x":609.0521531954386,"y":915.2423067144568},{"x":665.630768519605,"y":915.2423067144568},{"x":665.630768519605,"y":895.2733836588687},{"x":695.5841531029872,"y":895.2733836588687},{"x":695.5841531029872,"y":1094.9626142147501},{"x":609.0521531954386,"y":1094.9626142147501},{"x":609.0521531954386,"y":915.2423067144568}],"type":"polyline"}], 
                    px_per_m=33.6,
                    z=10, 
                    stair_enclosure_roof_z=35.0 
    )
