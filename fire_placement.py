def convert_print_to_string(args):
    # loop through args -> convert to sring
    # TODO: if unpacked list comes in -> able to auto include commas?
    i = 0
    array = []
    while i < len(args):
        # move to array
        array.append(str(args[i]))
        i += 1

    # # join
    # return string
    return ("").join(array)

def list_to_comma_str(current_list, needs_rounding=False, dps = 1):
    # TODO: snap to grid size instead of just rounding
    if needs_rounding:
        current_list = [round(x, dps) for x in current_list]
    current_list = [ str(x) for x in current_list ]
    return ",".join(current_list)

import numpy as np
def Fire_Obstruction(Fire_D, Fire_H, Fire_B, fire_x, fire_y, z=0):## Create a Function that generates the fire obstruction 
    # TODO: add sprinklers using calcs
    fire_Co = np.round([fire_x - Fire_D/2, fire_x + Fire_D/2, fire_y - Fire_D/2, fire_y+ Fire_D/2, z+Fire_B, z+Fire_H],2) 
    return [convert_print_to_string(("&OBST ID='Fire',", 'XB =', list_to_comma_str(fire_Co, True), ", SURF_IDS='Fire','Plasterboard','Plasterboard'/"))]

def fire_surf(HRR_KW, Fire_Area):     ## Define a Function that creates the Fire properties

    array = [convert_print_to_string(("&SURF ID='Fire',")),
    convert_print_to_string(("      COLOR='RED',")),
    convert_print_to_string(("      HRRPUA=", (HRR_KW/Fire_Area))),
    convert_print_to_string(("      TMP_FRONT=300.0/"))]
    return array