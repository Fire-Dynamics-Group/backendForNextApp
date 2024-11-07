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
def setup_landings(comments, fire_floor, total_floors, elements, px_per_m, z, stair_enclosure_roof_z, lowest_floor_landing_z=0, lowest_floor=0):
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
    delta_x1 = abs(landing_x1 - halflanding_x1)
    delta_y1 = abs(landing_y1 - halflanding_y1)
    if delta_x1 > delta_y1:
        stair_direction = 'x'
        delta_interlandings = max(landing_x1 - halflanding_x2, halflanding_x1 - landing_x2)
        stair1_y1_list = [landing_y1 for x in range(8)]
        stair1_y2_list = [landing_y2 for x in range(8)]
        # find stair direction lists
        '''
            start at landing go to half landing
        '''
        tread = math.ceil(100*(delta_interlandings / 8)) / 100 
        if landing_x1 - halflanding_x2 < halflanding_x1 - landing_x2:
            # plus x
            stair_x1_list = [landing_x1 + tread*x for x in range(8)]
            stair_x2_list = [landing_x2 + tread*x for x in range(8)]
            pass
        else:
            # minus x
            stair_x1_list = [landing_x1 - tread*x for x in range(8)]
            stair_x2_list = [landing_x2 - tread*x for x in range(8)]
        stair_y_mid_list = [landing_y1 + (landing_y2 - landing_y1)/2 for x in range(8)]
        # TODO: debug to find how to get right values
        stair_1_y2_list = stair_y_mid_list
        stair_2_y1_list = stair_y_mid_list

        stair2_x1_list = stair_x1_list[::-1] # stair_x1_list
        stair2_x2_list = stair_x2_list[::-1] # stair_1_x2_list
    else:
        stair_direction = 'y'
        delta_interlandings = max(landing_y1 - halflanding_y2, halflanding_y1 - landing_y2)
        stair_x1_list = [landing_x1 for x in range(8)]
        stair_x2_list = [landing_x2 for x in range(8)]
        stair_x_mid_list = [landing_x1 + (landing_x2 - landing_x1)/2 for x in range(8)]
        stair_1_x2_list = stair_x_mid_list
        stair_2_x1_list = stair_x_mid_list
        
        tread = math.ceil(100*(delta_interlandings / 8)) / 100 

        if landing_y1 - halflanding_y2 < halflanding_y1 - landing_y2:
            # plus y
            # TODO: start at end of landing
            stair1_y1_list = [landing_y2 + tread*x for x in range(8)]
            stair1_y2_list = [x + tread*2 for x in stair1_y1_list]

            pass
        else:
            # minus y
            stair1_y1_list = [landing_y1 - tread*x for x in range(8)]
            stair1_y2_list = [x - tread*2 for x in stair1_y1_list]

        stair2_y1_list = stair1_y1_list[::-1]
        stair2_y2_list = stair1_y2_list[::-1]

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
            height_per_step = math.ceil(100*((z_halflanding[idx] - z_current) / 8)) / 100
            for step_num in range(8):
                current_step_z1 = round(z_current + (step_num * height_per_step), 3)
                current_step_z2 = round(z_current + ((step_num + 1) * height_per_step), 3)
                # 
                current_step_line = f"&OBST ID='STEP1', XB = {round(stair_x1_list[step_num], 3)}, {round(stair_1_x2_list[step_num], 3)}, {round(stair1_y1_list[step_num], 3)}, {round(stair1_y2_list[step_num], 3)},{round(current_step_z1, 3)}, {round(current_step_z2, 3)}, SURF_ID = 'Plasterboard'/"
                array.append(current_step_line)
    for idx, z_current in enumerate(z_halflanding):
        output = f"&OBST ID='HALFLANDING', XB = {round(halflanding_x1, 3)}, {round(halflanding_x2, 3)}, {round(halflanding_y1, 3)}, {round(halflanding_y2, 3)},{round(z_current - 0.2, 3)}, {round(z_current, 3)}, SURF_ID = 'Plasterboard'/"
        array.append(output)

        if idx < len(z_halflanding):
            # height counting current as zero
            height_per_step = math.ceil(100*((z_landing[idx+1] - z_current) / 8)) / 100
            for step_num in range(8):
                current_step_z1 = round(z_current + (step_num * height_per_step), 3)
                current_step_z2 = round(z_current + ((step_num + 1) * height_per_step), 3)
                # 
                current_step_line = f"&OBST ID='STEP2', XB = {round(stair_2_x1_list[step_num], 3)}, {round(stair_x2_list[step_num], 3)}, {round(stair2_y1_list[step_num], 3)}, {round(stair2_y2_list[step_num], 3)},{round(current_step_z1, 3)}, {round(current_step_z2, 3)}, SURF_ID = 'Plasterboard'/"
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
