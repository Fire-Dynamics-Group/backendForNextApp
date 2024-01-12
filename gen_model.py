'''
TODO: allow inputs of stair width, stair height, room width and length etc to create fds model
have bottom left corner of room as origin (0, 0, 0)
cell size = 0.2m

have x amount of runs
each with different inputs chosen from a list of options
'''

from stairs_fds import gen_landings
from fds import points_to_fds_wall_lines, create_fds_mesh_lines, Stair_Mesh_Vent
from sensors import run_sensors
from fire_placement import Fire_Obstruction, fire_surf

# constants
fire_floor = 0


# TODO: create logic for random within bounds
# shuffle pack
room_area_list = [round(x*1 + 15, 2) for x in range(31)]
room_width_list = [round(x*0.2 + 3, 2) for x in range(21)]
# room_width = 5
# room_length = 5
# room_height = 3
room_height_list = [round(x*0.2 + 2.2, 2) for x in range(11)]
# stair_width = 1
stair_width_list = [round(x*0.2 + 0.8, 2) for x in range(5)]
# total_floors = 3
total_floors_list = [x for x in range(2, 6)]


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

def gen_roof(x1, x2, y1, y2, z1, z2, comment='stairObstruction'):
    xMin = min(x1, x2)
    xMax = max(x1, x2)+0.2
    yMin = min(y1, y2)-0.2
    yMax = max(y1, y2)
    zMin = min(z1, z2)
    ZMax = max(z1, z2)
    # find centre of roof
    xCentre = round((xMin + xMax)/2, 3)
    yCentre = round((yMin + yMax)/2, 3)
    # add hole 1m x 1m
    hole_x1 = xCentre - 0.5
    hole_x2 = xCentre + 0.5
    hole_y1 = yCentre - 0.5
    hole_y2 = yCentre + 0.5

    output = []
    output.append(f"&OBST ID='{comment}', XB = {round(xMin, 3)}, {round(xMax, 3)}, {round(yMin, 3)}, {round(yMax, 3)},{round(zMin, 3)}, {round(ZMax, 3)}, SURF_ID = 'Plasterboard'/")
    output.append(f"&HOLE ID='AOV', XB = {round(hole_x1, 3)}, {round(hole_x2, 3)}, {round(hole_y1, 3)}, {round(hole_y2, 3)},{round(zMin-0.2, 3)}, {round(ZMax+0.2, 3)}/")
    return output

def gen_stairs(room_width, room_length, stair_width, stair_enclosure_roof_z, fire_floor, total_floors, stair_depth=3, stair_offset_y=0):
    stair_start_pos = [room_width, stair_offset_y, 0]
    stair_landing_depth = 1
    stair_landing_width = stair_width*2
    z = 0

    fire_floor_landing_points = [
        {"x": stair_start_pos[0], "y": stair_start_pos[1]},
        {"x": stair_start_pos[0]+stair_landing_depth, "y": stair_start_pos[1]+stair_landing_width},
    ]

    fire_floor_halflanding_points = [
        {"x": stair_start_pos[0]+stair_landing_depth+stair_depth, "y": stair_start_pos[1]},
        {"x": stair_start_pos[0]+2*stair_landing_depth+stair_depth, "y": stair_start_pos[1]+stair_landing_width},
    ]
    wall_points = [
        {"x": stair_start_pos[0], "y": stair_start_pos[1]+stair_landing_width},
        fire_floor_halflanding_points[-1], 
        {"x": stair_start_pos[0]+2*stair_landing_depth+stair_depth, "y": stair_start_pos[1]},
        fire_floor_landing_points[0],
    ]

    incomplete_wall_points = [
        fire_floor_landing_points[0],
        {"x": stair_start_pos[0], "y": stair_start_pos[1]+stair_landing_width},
    ]

    room_points = [
        {"x": stair_start_pos[0], "y": 0},
        {"x": 0, "y": 0},
        {"x": 0, "y": room_length},
        {"x": stair_start_pos[0], "y": room_length},

    ]

    final_wall_points1 = [
        {"x": stair_start_pos[0], "y": room_length},
        {"x": stair_start_pos[0], "y": stair_start_pos[1]+stair_landing_width},
    ]
    final_wall_points2 = [
        {"x": stair_start_pos[0], "y": stair_start_pos[1]},
        {"x": stair_start_pos[0], "y": 0},
    ]
    # fire_floor_landing_points = [
    #     {"x": stair_start_pos[0], "y": stair_start_pos[1]},
    #     {"x": stair_start_pos[0]+stair_landing_depth, "y": stair_start_pos[1]+stair_landing_width},
    # ]

    # fire_floor_halflanding_points = [
    #     {"x": stair_start_pos[0], "y": stair_start_pos[1]+stair_landing_depth+stair_depth},
    #     {"x": stair_start_pos[0]+stair_landing_width, "y": stair_start_pos[1]+2*stair_landing_depth+stair_depth},
    # ]
    # TODO: add sensors above each stair and landing
    array = []
    array = gen_landings(fire_floor_landing_points, fire_floor_halflanding_points, z, stair_enclosure_roof_z, lowest_floor_landing_z=0, num_lower_landings=0, num_upper_landings=total_floors, array=array)
    wall_array = points_to_fds_wall_lines(wall_points, wall_thickness=0.2, px_per_m=1, comments="stairObstruction", z=0, wall_height=stair_enclosure_roof_z,is_stair=False)
    incomplete_wall_array = points_to_fds_wall_lines(incomplete_wall_points, wall_thickness=0.2, px_per_m=1, comments="stairObstruction", z=room_height, wall_height=stair_enclosure_roof_z-room_height,is_stair=False)
    stair_roof = gen_roof(x1=wall_points[0]['x'], x2=wall_points[1]['x'], y1=wall_points[0]['y'], y2=wall_points[-1]['y'], z1=stair_enclosure_roof_z, z2=stair_enclosure_roof_z+0.2)
    room_points_array = points_to_fds_wall_lines(room_points, wall_thickness=0.2, px_per_m=1, comments="obstruction", z=0, wall_height=room_height,is_stair=False)
    final_wall_points1_array = points_to_fds_wall_lines(final_wall_points1, wall_thickness=0.2, px_per_m=1, comments="obstruction", z=0, wall_height=room_height,is_stair=False)
    final_wall_points2_array = points_to_fds_wall_lines(final_wall_points2, wall_thickness=0.2, px_per_m=1, comments="obstruction", z=0, wall_height=room_height,is_stair=False)

    room_mesh = create_fds_mesh_lines(points=room_points, cell_size=0.2, z1=0, z2=room_height, px_per_m=1, comments='mesh', idx=0, is_stair=False)
    stair_mesh = create_fds_mesh_lines(points=wall_points, cell_size=0.2, z1=0, z2=stair_enclosure_roof_z+0.4, px_per_m=1, comments='stairMesh', idx=0, is_stair=True)
    vent_mesh = Stair_Mesh_Vent(wall_points, stair_enclosure_roof_z)
    # sensor_array = run_sensors(floor_z_list, sensor_points_list)
    # extract all step coordinates from array
    step_list = [f for f in array if 'STEP' in f or 'LANDING' in f]
    temp = [f.split(',')[1:7] for f in step_list]
    import re
    float_regex = r"[-+]?\d*\.\d+|\d+"

    # Extracting only the floats from each string
    floats_nested_list = []
    for sublist in temp:
        floats_list = [float(match) for item in sublist for match in re.findall(float_regex, item)]
        floats_nested_list.append(floats_list)
    mid_step_points = [[round((x1+x2)/2, 2), round((y1+y2)/2, 2), z2] for [x1, x2, y1, y2, z1, z2] in floats_nested_list]
    sensor_array = run_sensors(mid_step_points)

    array += wall_array + incomplete_wall_array + stair_roof + room_points_array + [room_mesh] + [stair_mesh] + vent_mesh
    if room_length != stair_start_pos[1]+stair_landing_width:
        array += final_wall_points1_array
    if stair_start_pos[1] != 0:
        array += final_wall_points2_array
    array += sensor_array
    return array

import math
def create_grid(max_x, max_y, min_x=0, min_y=0,cell_size=0.2):
    step = cell_size
    grid = []
    num_steps_x = math.ceil((max_x - min_x) / step)
    num_steps_y = math.ceil((max_y - min_y) / step)
    for i in [round((min_x + (step * x)), 1) for x in range(num_steps_x+1)]: # column
        for j in [round((min_y + (step * y)), 1) for y in range(num_steps_y+1)]: # row
        # TODO: check it's not a wall
            grid.append([i, j])
    return grid

import random
def return_random_element(array):
    random.shuffle(array)
    return array[0]

def place_fire_in_room(room_width, room_length, fire_dimension=1.4, cell_size=0.2):
    max_x = room_width
    max_y = room_length - cell_size
    min_x = cell_size
    min_y = 0
    grid = create_grid(max_x=max_x, max_y=max_y, min_x=min_x)
    # choose random point from grid
    random.shuffle(grid)
    point = grid[0]
    # check if point is not within fire dimension/2 to wall
    if point[0] < min_x + (fire_dimension / 2):
        point[0] = min_x + (fire_dimension / 2)
    elif point[0] > max_x - (fire_dimension / 2):
        point[0] = max_x - (fire_dimension / 2)
    if point[1] < min_y + (fire_dimension / 2):
        point[1] = min_y + (fire_dimension / 2)
    elif point[1] > max_y - (fire_dimension / 2):
        point[1] = max_y - (fire_dimension / 2)

    return point

def array_to_str(array):
    array = [ f for f in array if len(f)!= 0]
    return "\n".join(array)

def add_rows_to_fds_array(fds_array, *args):
    for element in (args):
        fds_array.append(element)

def add_array_to_fds_array(array, fds_array):
    add_rows_to_fds_array(fds_array, *array)


# for i in range(len(total_floors_list)):
for i in range(10):
    fds_array = header.copy()
    room_height = return_random_element(room_height_list)
    total_floors = return_random_element(total_floors_list)
    stair_enclosure_roof_z = room_height * total_floors
    stair_width = return_random_element(stair_width_list)

    room_area = None
    while room_area is None:
        room_area = return_random_element(room_area_list)
        room_width = return_random_element(room_width_list)
        room_length = round(room_area/room_width, 2) # should be factor or 0.2
        
        if room_length < 3 or room_length > 7:
            room_area = None


    # TODO: add stair walls

    array = gen_stairs(room_width, room_length, stair_width, stair_enclosure_roof_z, fire_floor, total_floors)

    fire_dimension = 1.4

    add_array_to_fds_array(array, fds_array)
    fire_point = place_fire_in_room(room_width, room_length)
    fire_array = fire_surf(HRR_KW=1000, Fire_Area=fire_dimension**2)
    fire_array += Fire_Obstruction(Fire_D=1.4, Fire_H=0.5, Fire_B=0, fire_x=fire_point[0], fire_y=fire_point[1])
    add_array_to_fds_array(fire_array, fds_array)
    # write to .fds file
    fds_array_str = array_to_str(fds_array)
    with open(f"output-models/stairs{i}.fds", "w") as f:
        f.write(fds_array_str)