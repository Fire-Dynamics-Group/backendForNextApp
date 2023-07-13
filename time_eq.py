import math
import io
import matplotlib.pyplot as plt

from mockData import mockTimeEqElements
# TODO: move to constants
font_name_normal = 'Segoe UI'
light_text_color = (0.59,0.56,0.56)
chart_config = {        
        "xtick.color": light_text_color,
        "ytick.color": light_text_color,
        "axes.titlecolor": light_text_color,
        "axes.labelcolor": light_text_color,
        "axes.edgecolor": light_text_color,
        "legend.labelcolor": light_text_color,
        "figure.figsize": [6, 4.5],
        'axes.grid': True,
        'grid.linewidth': '0.05',
        "grid.color": light_text_color,
        "text.color": light_text_color,
        "font.family": font_name_normal
        }
# from shapely.geometry import Polygon

# steel constants
c_prot=1200.0  # (J/kg.K) specific heat of the protection
rho_prot=290.0  # (kg/m3) density of the protection
therm_conduct=0.14  # thermal conductivity of the protection
rho_steel=7850  # (kg/m3) density of steel
sect_factor=121  # (Ap/V in m-1) section factor of the steel
fire_resistance_period = 30   # The required guidance FR period in minutes
failure_temperature = 550  # C - check this with D

material_b_values ={"concrete":math.sqrt(3033240), "brick": math.sqrt(2805000), "plasterboard": math.sqrt(177650)}  ### Table 7.6 of Fundamentals of Fire Phenomena Quintirere 
def calculate_polygon_area(points):
    area = 0.0
    n = len(points)

    for i in range(n):
        j = (i + 1) % n
        area += points[i].x * points[j].y
        area -= points[j].x * points[i].y

    area = abs(area) / 2.0
    return area

# what is At??
def get_b_value(room_composition, room_dimensions, At):  #gets an average B_Value based on the composition of the room.
    room_b_values = []
    for i in room_composition: # gets b_values of all surfaces
        room_b_values.append(material_b_values.get(i))
    b_value_weighted = []
    n = 0
    while n < len(room_dimensions):
        b_value_weighted.append(room_dimensions[n]*room_b_values[n]/At)  # weights b values based on the surface areas
        n=n+1
    b_value_weighted = sum(b_value_weighted)
    print(f"bvalue weighted = {b_value_weighted}")
    if b_value_weighted > 2200:  ## ensures b_values are within the limits of PD 6688.
        return 2200
    elif b_value_weighted < 100:
        return 100
    else:
        return b_value_weighted
    
## returns a valid opening factor
def get_opening_factor(av, heq, at):
    if av * math.sqrt(heq) / at < 0.01:
        O = 0.01
    elif av * math.sqrt(heq) / at > 0.2:
        O = 0.2
    else:
        O = av * math.sqrt(heq) / at
    return O    
    
def get_Av(window_list):
    Area = 0
    n = 0
    while n < len(window_list):
        temp = window_list[n]
        Area = Area + temp[0] * temp[1]
        n=n+1
    return Area

def get_Heq(window_heights, window_lengths, Av):
    # window_heights
    # window_lengths
    # Height = 0
    n = 0
    Height_weighted = []
    for n in  range(len(window_heights)):
        Height_weighted.append(((window_heights[n]**2)*window_lengths[n])/Av)

        # temp = window_list[n]
        # Height = temp[1]
        # Height_weighted.append((Height*temp[0]*temp[1])/Av)  # weights b values based on the surface areas
        # n=n+1
    return sum(Height_weighted)

# ## returns a valid opening factor
# def get_O(Heq, At, Av):
#     if Av * math.sqrt(Heq) / At < 0.01:
#         O = 0.01
#     elif Av * math.sqrt(Heq) / At > 0.2:
#         O = 0.2
#     else:
#         O = Av * math.sqrt(Heq) / At
#     return O

## returns a valid q_td
def get_q_td(q_fd, af, at, combustion_factor=1):
    if q_fd * combustion_factor * af / at < 50:
        q_td = 50
    elif q_fd * combustion_factor * af / at > 1000:
        q_td = 1000
    else:
        q_td = q_fd * combustion_factor * af / at
    return q_td

## returns a valid t_max
def get_t_max(Q_TD, O, t_lim):
    if 0.2 * 10**-3 * Q_TD / O > t_lim:
        t_max = 0.2 * 10**-3 * Q_TD / O
    else:
        t_max = t_lim
    return t_max


def get_parametric_fire(O, b, fld, Af, At, t_lim):
    ### code to calculate a parametric fire

    ## calculate all required factors

    gamma = (O / b)**2 / (0.04 / 1160)**2

    q_td = get_q_td(q_fd=fld, af=Af, at=At)
    # returns a valid q_td, which is a function of the total fire loading proportionate to the area of the surfaces of the compartment

    t_max = get_t_max(Q_TD=q_td, O=O, t_lim=t_lim)
    # gets a valid t_max

    O_lim = 0.1*10**-3 * q_td / t_lim
    # calculates opening factor for fuel controlled conditions

    gamma_lim = (O_lim / b)**2 / (0.04 / 1160)**2

    if O > 0.04 and q_td < 75 and b < 1160:
        k = 1 + ((O - 0.04)/0.04) * ((q_td - 75)/75) * ((1160 - b)/1160)
        gamma_lim = gamma_lim * k
    ## modifies gamma_lim if necessary

    tstar_max = t_max * gamma
    # calculates tstar value for the heating phase

    t = 0.5
    #sets time step as 0
    
    T = 21

    e = 2.71828
    #sets e for use in the calculation
    temperatures = [20]
    times = [0]

    T_max = 20 + 1325*(1 - 0.324*e**(-0.2*tstar_max) - 0.204*e**(-1.7*tstar_max) - 0.472*e**(-19*tstar_max))

    while T >= 20 and t<1000:
        if t_max == t_lim:
            t_star = t/60 * gamma_lim
            x  = t_lim * gamma / tstar_max
        else:
            t_star = t/60 * gamma
            x = 1.0
        T = 20 + 1325*(1 - 0.324*e**(-0.2*t_star) - 0.204*e**(-1.7*t_star) - 0.472*e**(-19*t_star))
        if T >= T_max: 
            if tstar_max >= 2:
                T = T_max - 250 * (t_star - tstar_max * x)
            elif tstar_max > 0.5:
                T = T_max - 250 * (3 - tstar_max) * (t_star - tstar_max * x)
            else: 
                T = T_max - 625 * (t_star - tstar_max * x)
        if T < 20:
            T = 20
        times.append(t)
        temperatures.append(T)

        
        t = t + 0.5
    return times, temperatures

def calculate_protsteeltemp(gas_temp, prev_gas_temp, steel_temp, d_p, c_p, rho_p, rho_a, therm_cond, delt_t):
    ### code to calculate steel temperature

    ## calculate c_a (specific heat of steel dependent on temperature)

    if steel_temp < 600:
        c_a = 425 + (7.73*10**-1 * steel_temp) - (1.69*10**-3 * steel_temp**2) + (2.22*10**-6 * steel_temp**3)
    elif 600 <= steel_temp < 735:
        c_a = 666 + 13002/(738-steel_temp)
    elif 735 <= steel_temp < 900:
        c_a = 545 + 17820/(steel_temp-731)
    else:
        # print ("Temperature < Ambient and > 1200, use c_a 650")
        c_a = 650

    ## calculate delta temperature of steel

    delta_Tgas = gas_temp - prev_gas_temp
    phi = c_p*rho_p/(c_a*rho_a)*d_p*sect_factor
    delta_T = therm_cond*sect_factor/(d_p*c_a*rho_a)*(gas_temp-steel_temp)/(1+phi/3)*delt_t*60 - (math.exp(phi/10)-1)*delta_Tgas

    ## return steel temperature

    steel_temp_new = steel_temp + delta_T

    return steel_temp_new
def calcDistPointList(pointsList):
    # get p1 and p2
    dist = 0
    for index in range(len(pointsList)-1):
        # length = distance i to i+1
        currentP = pointsList[index]
        nextP = pointsList[index + 1]

        x1 = currentP.x
        x2 = nextP.x
        y1 = currentP.y
        y2 = nextP.y
        dist += calcDist(x1, y1, x2, y2)
    return dist
    # send into calcDist
    pass
def calcDist(x1, y1, x2, y2):
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
# window data -> list of width * height
# TODO: prep for api call
# TODO: later save charts
def compute_time_eq(data, opening_heights,room_composition,is_sprinklered=False, fld=948, compartment_height=3.15, t_lim= 20/60):
    walls = [f for f in data if f.comments== 'obstruction']
    openings = [f for f in data if f.comments== 'opening']
    # b_value = material_b_values['concrete']

    combustion_factor = 1
    # TODO:
    # find room dimensions
    if is_sprinklered:
        fld = fld * 0.65
    wall_length = []
    wall_dimensions = []
    wall_points = walls[0].finalPoints # ['finalPoints']
    floor_area = calculate_polygon_area(wall_points)
    for wall_index in range(len(wall_points)-1):
        # length = distance i to i+1
        currentP = wall_points[wall_index]
        nextP = wall_points[wall_index + 1]

        x1 = currentP.x
        x2 = nextP.x
        y1 = currentP.y
        y2 = nextP.y
        dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        wall_length.append(dist)
        wall_dimensions.append(dist * compartment_height)

    room_dimensions = [floor_area, *wall_dimensions, floor_area]
    At = sum(room_dimensions) ## gets At (total area of surfaces) for use throughout.
    # get opening length from data, multiply by window height
    opening_lengths = [calcDistPointList(f.finalPoints) for f in openings]
    window_list = []
    for index in range(len(opening_lengths)):
        window_list.append(opening_lengths[index] * opening_heights[index])
    
    Av = sum(window_list)  ## gets total area of vent
    Heq_weighted_avg_height_openings = get_Heq(window_lengths=opening_lengths, window_heights=opening_heights, Av=Av) ## gets weighted vent height
    floor_area = room_dimensions[0]
    opening_factor = get_opening_factor(heq=Heq_weighted_avg_height_openings, at=At, av=Av)
    b_enclosure_surface_thermal_property = get_b_value(room_composition=room_composition, room_dimensions=room_dimensions, At=At) 
    times, temperatures = get_parametric_fire(O=opening_factor, b=b_enclosure_surface_thermal_property, fld=fld, Af=floor_area, At=At, t_lim=t_lim) 
   
    # plt.figure(figsize=(6, 4))  ## size of output
    # plt.plot(times, temperatures, color = 'blue', linewidth = 0.5,)  ## adds a line
    # plt.xlabel("Time (Minutes)", fontname = 'Segoe UI', fontsize = 10) ## sets label and font for xaxis
    # plt.ylabel("Temperature (C)", fontname = 'Segoe UI', fontsize = 10)  ## sets label and font for y axis   
    # print("O: ",opening_factor)
    # print("b: ", b_enclosure_surface_thermal_property)
    # # if __name__ == '__main__':
    # #     plt.show()    

    # #     plt.close()


    c_p = c_prot  # (J/kg.K) specific heat of the protection
    rho_p = rho_prot  # (kg/m3) density of the protection
    therm_cond = therm_conduct  # thermal conductivity of the protection
    rho_a = rho_steel  # (kg/m3) density of steel
    delt_t = 0.5  # (minute) delta T of the calculation

    isofire_T = [20]
    isofire_t = [0]
    n=0.5

    while n <= 1000:
        T = 20 + 345 * math.log(8*n+0.5,10)
        isofire_T.append(T)
        isofire_t.append(n)
        n=n+0.5

    sufficient_thickness = False
    thickness = 0.5

    while sufficient_thickness == False:

        d_p = thickness/1000  # convert protection thickness to to meter
        Prev_steel = 20
        Prev_gas = 20
        n=0
        for i in isofire_T:
            steel_temp = calculate_protsteeltemp(gas_temp=i,prev_gas_temp=Prev_gas, steel_temp=Prev_steel, d_p=d_p, c_p=c_p, rho_p=rho_p, rho_a=rho_a, therm_cond=therm_cond, delt_t=delt_t) 
            Prev_gas = i
            Prev_steel = steel_temp
            n=n+0.5
            if n == fire_resistance_period:
                break
        if steel_temp < failure_temperature:
            sufficient_thickness = True
        else:
            thickness = thickness + 0.1

    iso_steel_temps = []

    Prev_steel = 20
    Prev_gas = 20
    for i in isofire_T:
        steel_temp = calculate_protsteeltemp(gas_temp=i,prev_gas_temp=Prev_gas, steel_temp=Prev_steel, d_p=d_p, c_p=c_p, rho_p=rho_p, rho_a=rho_a, therm_cond=therm_cond, delt_t=delt_t)
        Prev_gas = i
        Prev_steel = steel_temp
        iso_steel_temps.append(steel_temp)

    print("thickness", thickness)  

    # plt.figure(figsize=(6, 4))  ## size of output
    # plt.plot(isofire_t, isofire_T, color = 'blue', linewidth = 0.5,)  ## adds a line
    # plt.plot(isofire_t, iso_steel_temps, color = 'red', linewidth = 0.5,)  ## adds a line
    # plt.xlabel("Time (Minutes)", fontname = 'Segoe UI', fontsize = 10) ## sets label and font for xaxis
    # plt.ylabel("Temperature (C)", fontname = 'Segoe UI', fontsize = 10)  ## sets label and font for y axis
    # # if __name__ == '__main__':
    # #     plt.show()    

    # #     plt.close()
    para_steel_temps = []

    Prev_steel = 20
    Prev_gas = 20
    for i in temperatures:
        steel_temp = calculate_protsteeltemp(gas_temp=i,prev_gas_temp=Prev_gas, steel_temp=Prev_steel, d_p=d_p, c_p=c_p, rho_p=rho_p, rho_a=rho_a, therm_cond=therm_cond, delt_t=delt_t)
        Prev_gas = i
        Prev_steel = steel_temp
        para_steel_temps.append(steel_temp)
    para_max_temp = max(para_steel_temps)
    index = (min(range(len(iso_steel_temps)), key=lambda i: abs(iso_steel_temps[i]-para_max_temp)))
    print(f"time equivalency value = {(index+1)/2} minutes")
    time_eq = (index+1)/2
    with plt.rc_context(chart_config):
    # TODO: bring in config
    # add vertical @ time equivalenc time
        # plt.figure(figsize=(6, 4))  ## size of output
        plt.axvline(x=time_eq, color="grey", linestyle='--', linewidth=0.75)
        # TODO: calc temp of purple fire at time equivalence
        plt.axhline(y=iso_steel_temps[index], color='grey', linestyle='--', linewidth=0.75)
        plt.plot(times, para_steel_temps, color = 'red', label="Protected Steel - Parametric Fire", linewidth = 0.5,)  ## adds a line
        plt.plot(isofire_t, iso_steel_temps, color = 'purple', label="Protected Steel - ISO Fire",linewidth = 0.5,)  ## adds a line
        plt.plot(times, temperatures, color = 'blue', label="Parametric Fire", linewidth = 0.5,)  ## adds a line
        plt.plot(isofire_t, isofire_T, color = 'green', label="ISO Fire", linewidth = 0.5,)  ## adds a line
        plt.xlabel("Time (Minutes)", fontname = 'Segoe UI', fontsize = 10) ## sets label and font for xaxis
        plt.ylabel("Temperature (C)", fontname = 'Segoe UI', fontsize = 10)  ## sets label and font for y axis
        # TODO: line below chart -> with tenability in mins rounded to 1 dp e.g.
        plt.xlim([0, 400])
        plt.legend(bbox_to_anchor =(0.25,-0.45), ncol=1,loc='lower left', fontsize = 8, frameon=False)
        plt.subplots_adjust(bottom=0.2) # This makes room.
        if time_eq % 2 == 0:
            time_eq = round(time_eq, 0)
        plt.figtext(0.5, 0.02, f'The Equivalent Time of Fire Exposure is {time_eq} Minutes', ha='center', va='center', fontsize = 8, fontname = 'Segoe UI')
        plt.tight_layout() 

        image_buffer = io.BytesIO()
        plt.savefig(image_buffer, format='jpeg')
        image_buffer.seek(0)
        img_base64 = image_buffer.getvalue()
        if __name__ == '__main__':
            plt.show()    

        plt.close()
    


    # walls to height by width list
    # get area of ceiling
    # get area of walls
    # get compartment height sent in
    print(data)

    return img_base64

def time_eq_test(data):
    wall_points = [f for f in data if f.comments== 'obstruction'][0].finalPoints

    print("data: ",wall_points)

if __name__ == '__main__':
    from typing import List
    from pydantic import BaseModel

    class Point(BaseModel):
        x: float
        y: float

    class Element(BaseModel):
        type: str
        points: List[Point]
        comments: str

    class ConvertedElement(BaseModel):
        id: int
        finalPoints: List[Point]
        comments: str
    # room comp -> all concrete
    # find number of openings -> mock heights
    mockConvertedPoints = [ConvertedElement(id=0, finalPoints=[Point(x=0.2, y=0.0), Point(x=0.2, y=5.2), Point(x=0.0, y=5.2), Point(x=0.0, y=5.8), Point(x=9.7, y=5.8), Point(x=9.7, y=5.6), Point(x=10.0, y=5.6), Point(x=10.0, y=2.4), Point(x=10.4, y=2.4), Point(x=10.4, y=0.1), Point(x=7.3, y=0.1), Point(x=7.3, y=0.0), Point(x=0.2, y=0.0)], comments='obstruction'), ConvertedElement(id=1, finalPoints=[Point(x=10.0, y=5.5), Point(x=10.0, y=4.2)], comments='opening'), ConvertedElement(id=2, finalPoints=[Point(x=10.4, y=2.4), Point(x=10.4, y=0.1)], comments='opening')]
    openings = [f for f in mockConvertedPoints if f.comments== 'opening']
    wall_points = [f for f in mockConvertedPoints if f.comments== 'obstruction'][0].finalPoints
    
    # room comp -> all concrete from num walls
    # wall_points = [f for f in mockTimeEqElements if f['comments']== 'obstruction'][0]['finalPoints']
    room_composition = ['concrete', 'concrete', 'concrete', 'concrete', 'concrete', 'concrete', 'concrete', 'concrete', 'concrete', 'concrete', 'concrete', 'concrete', 'concrete', 'concrete', 'concrete']
    opening_heights = [1.5, 1.5]

    image_data = compute_time_eq(data=mockConvertedPoints, opening_heights=opening_heights, room_composition=room_composition)