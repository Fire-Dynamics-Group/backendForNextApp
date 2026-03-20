"""
Door controls for FDS generation.
Ported from reference Python project's controls.py.
Generates RAMP/CTRL lines for door open/close timing per scenario type.
"""

Control_ID_Apartment = 'Apartment Door Hole'
Control_ID_Stair = 'Stair Door Hole'
Control_ID_Extract = 'Extract Vent'
Control_ID_Apartment_Inlet = 'Apartment Inlet Hole'


def moe_door_controls(apartment_door_open, apartment_door_close, stair_door_open, stair_door_close, is_stair_door_needed_for_inlet=False):
    """
    MOE scenario: doors open then close.
    FDS removes/creates obstruction 0.25s before the specified time.
    """
    Input_ID = 'TIME'
    array = []

    apt_open = [apartment_door_open - 0.25, apartment_door_open + 0.25]
    apt_close = [apartment_door_close - 0.25, apartment_door_close + 0.25]
    st_open = [stair_door_open - 0.25, stair_door_open + 0.25]
    st_close = [stair_door_close - 0.25, stair_door_close + 0.25]

    F_d = -1.0
    F_a = 1.0

    # Apartment door open
    for t in apt_open:
        F_t = F_d if t < apartment_door_open else F_a
        array.append(f"&RAMP ID = '{Control_ID_Apartment}_RAMP', T = {t}, F={F_t}/")

    # Apartment door close
    for t in apt_close:
        F_t = F_a if t < apartment_door_close else F_d
        array.append(f"&RAMP ID = '{Control_ID_Apartment}_RAMP', T = {t}, F={F_t}/")

    array.append(f"&CTRL ID = '{Control_ID_Apartment}', FUNCTION_TYPE = 'CUSTOM', RAMP_ID = '{Control_ID_Apartment}_RAMP', LATCH =.FALSE., INPUT_ID='{Input_ID}'/")
    array.append(f"&DEVC ID = '{Input_ID}', QUANTITY='{Input_ID}', XYZ = 0.0,0.0,0.0/")

    # Stair door open
    for t in st_open:
        F_t = F_d if t < stair_door_open else F_a
        array.append(f"&RAMP ID = '{Control_ID_Stair}_RAMP', T = {t}, F={F_t}/")

    # Stair door close (skip if stair door needed for inlet)
    if not is_stair_door_needed_for_inlet:
        for t in st_close:
            F_t = F_a if t < stair_door_close else F_d
            array.append(f"&RAMP ID = '{Control_ID_Stair}_RAMP', T = {t}, F={F_t}/")

    array.append(f"&CTRL ID = '{Control_ID_Stair}', FUNCTION_TYPE = 'CUSTOM', RAMP_ID = '{Control_ID_Stair}_RAMP', LATCH =.FALSE., INPUT_ID='{Input_ID}'/")
    array.append(f"&DEVC ID = '{Input_ID}', QUANTITY='{Input_ID}', XYZ = 0.0,0.0,0.0/")

    return array


def fsa_door_deactivate(stair_door_open, apartment_door_open):
    """
    FSA scenario: doors open and stay open (no close).
    """
    Input_ID = 'TIME'
    array = []

    apt_open = [apartment_door_open - 0.25, apartment_door_open + 0.25]
    st_open = [stair_door_open - 0.25, stair_door_open + 0.25]

    F_d = -1.0
    F_a = 1.0

    # Apartment door open
    for t in apt_open:
        F_t = F_d if t < apartment_door_open else F_a
        array.append(f"&RAMP ID = '{Control_ID_Apartment}_RAMP', T = {t}, F={F_t}/")

    array.append(f"&CTRL ID = '{Control_ID_Apartment}', FUNCTION_TYPE = 'CUSTOM', RAMP_ID = '{Control_ID_Apartment}_RAMP', LATCH =.FALSE., INPUT_ID='{Input_ID}'/")
    array.append(f"&DEVC ID = '{Input_ID}', QUANTITY='{Input_ID}', XYZ = 0.0,0.0,0.0/")

    # Stair door open
    for t in st_open:
        F_t = F_d if t < stair_door_open else F_a
        array.append(f"&RAMP ID = '{Control_ID_Stair}_RAMP', T = {t}, F={F_t}/")

    array.append(f"&CTRL ID = '{Control_ID_Stair}', FUNCTION_TYPE = 'CUSTOM', RAMP_ID = '{Control_ID_Stair}_RAMP', LATCH =.FALSE., INPUT_ID='{Input_ID}'/")
    array.append(f"&DEVC ID = '{Input_ID}', QUANTITY='{Input_ID}', XYZ = 0.0,0.0,0.0/")

    return array


def hybrid_door_controls(door_openings):
    """
    Hybrid (Both) scenario: MOE open/close then FSA final open.
    door_openings dict must contain keys for MOE and FSA timings.
    """
    Input_ID = 'TIME'
    array = []

    F_d = -1.0
    F_a = 1.0

    # MOE Phase
    moe_apt_open = door_openings.get("moe_apartment_open", 30)
    moe_apt_close = door_openings.get("moe_apartment_close", 60)
    moe_st_open = door_openings.get("moe_stair_open", 35)
    moe_st_close = door_openings.get("moe_stair_close", 65)

    # FSA Phase
    fsa_apt_open = door_openings.get("fsa_apartment_open", 900)
    fsa_st_open = door_openings.get("fsa_stair_open", 900)

    # Apartment door - MOE open
    for t in [moe_apt_open - 0.25, moe_apt_open + 0.25]:
        F_t = F_d if t < moe_apt_open else F_a
        array.append(f"&RAMP ID = '{Control_ID_Apartment}_RAMP', T = {t}, F={F_t}/")

    # Apartment door - MOE close
    for t in [moe_apt_close - 0.25, moe_apt_close + 0.25]:
        F_t = F_a if t < moe_apt_close else F_d
        array.append(f"&RAMP ID = '{Control_ID_Apartment}_RAMP', T = {t}, F={F_t}/")

    # Apartment door - FSA open
    for t in [fsa_apt_open - 0.25, fsa_apt_open + 0.25]:
        F_t = F_d if t < fsa_apt_open else F_a
        array.append(f"&RAMP ID = '{Control_ID_Apartment}_RAMP', T = {t}, F={F_t}/")

    array.append(f"&CTRL ID = '{Control_ID_Apartment}', FUNCTION_TYPE = 'CUSTOM', RAMP_ID = '{Control_ID_Apartment}_RAMP', LATCH =.FALSE., INPUT_ID='{Input_ID}'/")
    array.append(f"&DEVC ID = '{Input_ID}', QUANTITY='{Input_ID}', XYZ = 0.0,0.0,0.0/")

    # Stair door - MOE open
    for t in [moe_st_open - 0.25, moe_st_open + 0.25]:
        F_t = F_d if t < moe_st_open else F_a
        array.append(f"&RAMP ID = '{Control_ID_Stair}_RAMP', T = {t}, F={F_t}/")

    # Stair door - MOE close
    for t in [moe_st_close - 0.25, moe_st_close + 0.25]:
        F_t = F_a if t < moe_st_close else F_d
        array.append(f"&RAMP ID = '{Control_ID_Stair}_RAMP', T = {t}, F={F_t}/")

    # Stair door - FSA open
    for t in [fsa_st_open - 0.25, fsa_st_open + 0.25]:
        F_t = F_d if t < fsa_st_open else F_a
        array.append(f"&RAMP ID = '{Control_ID_Stair}_RAMP', T = {t}, F={F_t}/")

    array.append(f"&CTRL ID = '{Control_ID_Stair}', FUNCTION_TYPE = 'CUSTOM', RAMP_ID = '{Control_ID_Stair}_RAMP', LATCH =.FALSE., INPUT_ID='{Input_ID}'/")
    array.append(f"&DEVC ID = '{Input_ID}', QUANTITY='{Input_ID}', XYZ = 0.0,0.0,0.0/")

    return array


def extract_controls_fds(apartment_door_open, number, is_firefighting=False, is_ramped=False, ramp_duration=10):
    """Generate RAMP/CTRL for extract vent activation."""
    Input_ID = 'TIME'
    array = []

    extract_activation = apartment_door_open + 10
    if is_firefighting:
        extract_activation = apartment_door_open

    extract_actions = [extract_activation - 0.25, extract_activation + 0.25]

    extract_id = f'{Control_ID_Extract}{number}'

    F_d = -1.0
    F_a = 1.0

    if is_ramped:
        F_r0 = 0.0
        extract_actions.append(extract_actions[-1] + ramp_duration)

    for t in extract_actions:
        if t < extract_activation:
            F_t = F_d
        else:
            if t == extract_actions[-1] and is_ramped:
                F_t = F_a
            elif t == extract_actions[-1]:
                F_t = F_a
            else:
                F_t = F_r0 if is_ramped else F_a
        array.append(f"&RAMP ID = '{extract_id}_RAMP', T = {t}, F={F_t}/")

    array.append(f"&CTRL ID = '{extract_id}', FUNCTION_TYPE = 'CUSTOM', RAMP_ID = '{extract_id}_RAMP', LATCH =.FALSE., INPUT_ID='{Input_ID}'/")
    array.append(f"&DEVC ID = '{Input_ID}', QUANTITY='{Input_ID}', XYZ = 0.0,0.0,0.0/")

    return array


def return_hole_controls(activation_time=None, deactivation_time=None):
    """Generic hole activation/deactivation controls."""
    Input_ID = 'TIME'
    array = []
    F_d = -1.0
    F_a = 1.0

    if activation_time:
        timings = [activation_time - 0.25, activation_time + 0.25]
        action_list = [F_d, F_a]
    elif deactivation_time:
        timings = [deactivation_time - 0.25, deactivation_time + 0.25]
        action_list = [F_a, F_d]
    else:
        return array

    for i in range(len(action_list)):
        array.append(f"&RAMP ID = '{Control_ID_Apartment_Inlet}_RAMP', T = {timings[i]}, F={action_list[i]}/")

    array.append(f"&CTRL ID = '{Control_ID_Apartment_Inlet}', FUNCTION_TYPE = 'CUSTOM', RAMP_ID = '{Control_ID_Apartment_Inlet}_RAMP', LATCH =.FALSE., INPUT_ID='{Input_ID}'/")
    array.append(f"&DEVC ID = '{Input_ID}', QUANTITY='{Input_ID}', XYZ = 0.0,0.0,0.0/")

    return array


def generate_door_controls(scenario_type, door_openings):
    """
    Main entry point: generate door controls based on scenario type.

    door_openings: dict with door timing values from frontend.
    For MOE: needs apartment_open, apartment_close, stair_open, stair_close
    For FSA: needs apartment_open, stair_open
    For Both: needs both sets of timings
    """
    # Default timings if not provided
    apt_open = float(door_openings.get("apartment_open", 30))
    apt_close = float(door_openings.get("apartment_close", 60))
    stair_open = float(door_openings.get("stair_open", 35))
    stair_close = float(door_openings.get("stair_close", 65))

    if scenario_type == "MOE":
        return moe_door_controls(apt_open, apt_close, stair_open, stair_close)
    elif scenario_type == "FSA":
        return fsa_door_deactivate(stair_open, apt_open)
    elif scenario_type == "Both":
        hybrid_timings = {
            "moe_apartment_open": apt_open,
            "moe_apartment_close": apt_close,
            "moe_stair_open": stair_open,
            "moe_stair_close": stair_close,
            "fsa_apartment_open": float(door_openings.get("fsa_apartment_open", 900)),
            "fsa_stair_open": float(door_openings.get("fsa_stair_open", 900)),
        }
        return hybrid_door_controls(hybrid_timings)
    else:
        return []
