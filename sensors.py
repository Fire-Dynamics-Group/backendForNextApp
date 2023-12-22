def Sensor_Generator(z, points, sensor_type, area, is_firefighting_dist=False,start_from_index=0):
    array = []
    counter = 0
    if "temp" in sensor_type.lower() or "pres" in sensor_type.lower():
        param = sensor_type.lower()[0:4]
    else:
        param = sensor_type.lower()[0:3]

    for i in range(len(points)):
        currentX, currentY = points[i]
        for j in range(len(z)): # len 1 when not tree of sensors
            # TODO: allow for _2m etc change below if ff
            if is_firefighting_dist:
                distance_array = [ 2, 4, 15]
                current_distance = distance_array[i]
                id_name = f'{area}_FSA_{param}_{current_distance}m'
            else:
                id_name = f'{area}_{param}_{counter+1+start_from_index}'
            output = f"&DEVC ID='{id_name}', QUANTITY = '{sensor_type}', XYZ= {currentX}, {currentY}, {z[j]}/"
            array.append(output)
            counter += 1
    return array

def run_sensors(floor_z_list, sensor_points_list):
    sensor_types = ["TEMPERATURE", "PRESSURE", "VISIBILITY", "VELOCITY"]
    sensor_array = []
    for sens_type in sensor_types:
        for idx, floor_z in enumerate(floor_z_list):
            sensor_point = sensor_points_list[idx]
        # for i in range(12): # for each point use 1.8 above floor level
            sensor_array += (Sensor_Generator(z=[floor_z+1.8], points=[sensor_point], sensor_type=sens_type, area="stair", is_firefighting_dist=False,start_from_index=idx))
pass