'''
TODO: allow inputs of stair width, stair height, room width and length etc to create fds model
have bottom left corner of room as origin (0, 0, 0)
cell size = 0.2m

have x amount of runs
each with different inputs chosen from a list of options
'''

from stairs_fds import gen_landings
from fds import points_to_fds_wall_lines
from sensors import run_sensors

# constants
room_width = 5
room_length = 5
fire_floor = 0


# TODO: create logic for random within bounds
# shuffle pack
room_height = 3
room_height_list = [round(x*0.2 + 2.2, 2) for x in range(11)]
stair_width = 1
stair_width_list = [round(x*0.2 + 0.8, 2) for x in range(5)]
total_floors = 3
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
    array = []
    array = gen_landings(fire_floor_landing_points, fire_floor_halflanding_points, z, stair_enclosure_roof_z, lowest_floor_landing_z=0, num_lower_landings=0, num_upper_landings=total_floors, array=array)
    wall_array = points_to_fds_wall_lines(wall_points, wall_thickness=0.2, px_per_m=1, comments="stairObstruction", z=0, wall_height=stair_enclosure_roof_z,is_stair=False)
    incomplete_wall_array = points_to_fds_wall_lines(incomplete_wall_points, wall_thickness=0.2, px_per_m=1, comments="stairObstruction", z=room_height, wall_height=stair_enclosure_roof_z-room_height,is_stair=False)
    room_points_array = points_to_fds_wall_lines(room_points, wall_thickness=0.2, px_per_m=1, comments="obstruction", z=0, wall_height=room_height,is_stair=False)
    final_wall_points1_array = points_to_fds_wall_lines(final_wall_points1, wall_thickness=0.2, px_per_m=1, comments="obstruction", z=0, wall_height=room_height,is_stair=False)
    final_wall_points2_array = points_to_fds_wall_lines(final_wall_points2, wall_thickness=0.2, px_per_m=1, comments="obstruction", z=0, wall_height=room_height,is_stair=False)
    # sensor_array = run_sensors(floor_z_list, sensor_points_list)


    array += wall_array + incomplete_wall_array + room_points_array
    if room_length != stair_start_pos[1]+stair_landing_width:
        array += final_wall_points1_array
    if stair_start_pos[1] != 0:
        array += final_wall_points2_array
    return array

def array_to_str(array):
    array = [ f for f in array if len(f)!= 0]
    return "\n".join(array)

def add_rows_to_fds_array(fds_array, *args):
    for element in (args):
        fds_array.append(element)

def add_array_to_fds_array(array, fds_array):
    add_rows_to_fds_array(fds_array, *array)


for i in range(len(total_floors_list)):
    fds_array = header.copy()
    room_height = room_height_list[i]
    total_floors = total_floors_list[i]
    stair_enclosure_roof_z = room_height * total_floors
    stair_width = stair_width_list[i]


    # TODO: add stair walls

    array = gen_stairs(room_width, room_length, stair_width, stair_enclosure_roof_z, fire_floor, total_floors)
    
    
    
    add_array_to_fds_array(array, fds_array)
    # write to .fds file
    fds_array_str = array_to_str(fds_array)
    with open(f"output-models/stairs{i}.fds", "w") as f:
        f.write(fds_array_str)