import re
from PIL import Image, ImageDraw

def fds_draw_clone(
        path_to_fds_file ="dev_folder\FS1 MOE.fds"
):
        # -*- coding: utf-8 -*-

    border_width = 0
    #### Variables
    # find floor height; to cut off z
    # find main mesh z bottom and top
    # find fire location -> find mesh with fire init for z cutoff -> check that fire within bounds
    image_width = 1180
    image_width = 7650
    # z_cut_low = -0.1
    # z_cut_high = 6.0




    # Initialize an empty list to store the coordinates of obstructions
    obstruction_coordinates = []
    fire_locations = []
    sprinkler_locations = []
    sensor_locations = []
    aov_locations = []
    inlet_locations = []
    mech_vent_locations = []
    flat_door_locations = []
    stair_door_locations = []
    misc_door_locations = []

    def is_numeric(s):
        try:
            float(s)
            return True
        except ValueError:
            return False
    # Open the .fds file for reading
    with open(path_to_fds_file, 'r') as fds_file:
        # Iterate through each line in the file

        for line in fds_file:
            # Remove all spaces from the line
            line = line.replace(" ", "")
            # Check if the line contains "&OBST" and "XB="
            if "&OBST" in line and "XB=" in line:
                if "Fire" in line and "SURF_IDS=" in line:
                    # extract coords for fire
                    xb_data = line.split("XB=")[1].split(",SURF")[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    fire_locations.append(tuple(coordinates))
                    # TODO: find mesh max and min
                    pass
                else:
                    if "COLOR=" in line:
                        pass
                    # Extract the part of the line between "XB=" and "/"
                    xb_data = line.split("XB=")[1]
                    xb_data = re.split("/|,QUANTITY", xb_data)[0]
                    # Split the coordinates into a list
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)][:6]
                    # Append the coordinates to the list of obstructions
                    obstruction_coordinates.append(tuple(coordinates))
            
            elif "&DEVC" in line:
                if "SPRK" in line:
                    xb_data = line.split("XYZ=")[1]
                    xb_data = re.split("/|,QUANTITY", xb_data)[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    sprinkler_locations.append(tuple(coordinates))
                if "QUANTITY='" in line:
                    xb_data = line.split("XYZ=")[1]
                    xb_data = re.split("/|,QUANTITY", xb_data)[0]
                    # xb_data = line.split("XYZ=")[1].split(",QUANTITY")[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    sensor_locations.append(tuple(coordinates))                        
                pass
            elif "&HOLE" in line:
                if "AOV" in line:
                    xb_data = line.split("XB=")[1].split("/")[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    aov_locations.append(tuple(coordinates))
                elif "inlet" in line.lower():
                    xb_data = line.split("XB=")[1].split("/")[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    inlet_locations.append(tuple(coordinates))
                elif "door" in line.lower():
                    if "apt" in line.lower() or "apartment" in line.lower():
                        xb_data = line.split("XB=")[1].split("/")[0]
                        coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                        flat_door_locations.append(tuple(coordinates))
                    elif "stair" in line.lower():
                        xb_data = line.split("XB=")[1].split("/")[0]
                        coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                        stair_door_locations.append(tuple(coordinates))
                    else:
                        xb_data = line.split("XB=")[1].split("/")[0]
                        coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                        misc_door_locations.append(tuple(coordinates))
            elif "&VENT" in line:
                if "inlet" in line.lower():
                    xb_data = line.split("XB=")[1].split("/")[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    mech_vent_locations.append(tuple(coordinates))
                elif "extract" in line.lower():
                    xb_data = line.split("XB=")[1].split("/")[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    mech_vent_locations.append(tuple(coordinates))
                pass
                

            '''
            &VENT ID='Mesh Vent: Apartment Inlet [YMAX]', SURF_ID='OPEN', XB=35.7,35.7,0.0,3.3,4.0,7.2/ 
            &VENT ID='Mesh Vent: Stair_Mesh_Upper1 [ZMAX]', SURF_ID='OPEN', XB=3.6,11.0,9.2,14.2,35.6,35.6/ 
            &VENT ID='Mech Extract1', SURF_ID='Extract', XB=27.1,27.1,22.7,23.6,5.8,6.4/ 
            &VENT ID='Mech Inlet1', SURF_ID='Inlet', XB=5.0,5.0,19.9,20.8,5.8,6.4/ 


            '''
    # TODO: find fire etc
        # &OBST ID='Fire', XB=30.8,32.2,0.9,2.3,4.0,4.5, SURF_IDS='Fire','Plasterboard','Plasterboard'/ 

    # Print the list of obstruction coordinates
    #print(obstruction_coordinates)

    all_obstructions = obstruction_coordinates + fire_locations + sprinkler_locations + sensor_locations + aov_locations + inlet_locations
    lowest_x = min(min(coords[0], coords[-2]) for coords in all_obstructions)
    lowest_y = min(min(coords[1], coords[-1]) for coords in all_obstructions)
    highest_x = max(max(coords[-2], coords[0]) for coords in all_obstructions)
    highest_y = max(max(coords[-1], coords[1]) for coords in all_obstructions)
    # Find the lowest x1 value among all tuples
    lowest_x1 = lowest_x

    # Find the highest x2 value among all tuples
    highest_x2 = highest_x-lowest_x1

    lowest_y1 = lowest_y

    highest_y2 = highest_y

    delta_x = highest_x2 - lowest_x1
    delta_y = highest_y2 - lowest_y1
    diff_deltas = abs(delta_x - delta_y)


    # # Adjust image size to include the border
    b_width = 50
    image_width = image_width + 2 * b_width
    image_height = image_width + 2 * b_width
    # Calculate the scaling factor for x1, x2, y1, y2
    scaling_factor = image_width
    def convert_single_point(coordinates, scaling_factor):
        updated_coordinates = []
        for coords in coordinates:
            x, y, z = coords
            # Subtract the lowest x1 and y1 values and adjust y coordinates
            x -= lowest_x1 
            # x+= 
            y += diff_deltas + 5
            y = highest_y2 - y # flip y
            x += border_width
            y += border_width
            # Scale and convert to pixels
            x = int(x/(highest_x2+b_width) * scaling_factor) + b_width
            y = int(y/(highest_x2+b_width) * scaling_factor) + b_width
            updated_coordinates.append((x, y, z))
        return updated_coordinates
    # Process the coordinates and update the list of tuples
    def convert_points(coordinates, scaling_factor):
        updated_coordinates = []
        for coords in coordinates:
            x1, x2, y1, y2, z1, z2 = coords
            # Subtract the lowest x1 and y1 values and adjust y coordinates
            x1 -= lowest_x1
            x2 -= lowest_x1
            y1 += diff_deltas + 5 # gives b_width pixel cushion at bottom
            y1 = highest_y2 - y1
            y2 += diff_deltas + 5
            y2 = highest_y2 - y2
            x1 += border_width
            x2 += border_width
            y1 += border_width
            y2 += border_width
            # Scale and convert to pixels
            x1 = int(x1/(highest_x2+b_width) * scaling_factor) + b_width
            x2 = int(x2/(highest_x2+b_width) * scaling_factor) + b_width
            y1 = int(y1/(highest_x2+b_width) * scaling_factor) + b_width
            y2 = int(y2/(highest_x2+b_width) * scaling_factor) + b_width
            y1, y2 = min(y1, y2), max(y1, y2)
            x1, x2 = min(x1, x2), max(x1, x2)
            updated_coordinates.append((x1, x2, y1, y2, z1, z2))


        # Sort the list of tuples based on the z2 values in ascending order
        sorted_obstruction_coordinates = sorted(updated_coordinates, key=lambda x: x[5])
        return sorted_obstruction_coordinates

    # Print the sorted list of tuples



    obstruction_coordinates = convert_points(obstruction_coordinates, scaling_factor)
    fire_locations = convert_points(fire_locations, scaling_factor)
    aov_locations = convert_points(aov_locations, scaling_factor)
    inlet_locations = convert_points(inlet_locations, scaling_factor)
    mech_vent_locations = convert_points(mech_vent_locations, scaling_factor)
    flat_door_locations = convert_points(flat_door_locations, scaling_factor)
    stair_door_locations = convert_points(stair_door_locations, scaling_factor)
    misc_door_locations = convert_points(misc_door_locations, scaling_factor)

    sprinkler_locations = convert_single_point(sprinkler_locations, scaling_factor)
    sensor_locations = convert_single_point(sensor_locations, scaling_factor)

    lowest_x1 = int(min(coords[0] for coords in obstruction_coordinates))
    lowest_y1 = int(min(coords[1] for coords in obstruction_coordinates))
    highest_y2 = int(max(coords[1] for coords in obstruction_coordinates))
    # Find the highest x2 value among all tuples
    highest_x2 = int(max(coords[1] for coords in obstruction_coordinates))


    # TODO: find mesh max and min with fire
    z_cut_low = fire_locations[0][-2] - 0.3
    z_cut_high = fire_locations[0][-1] + 3


    # # Create a new image with a white background
    # image_w = highest_x2 + border_width
    # image_h = highest_y2 + border_width
    # image_width = highest_x2 + border_width  # Adjust as needed
    # image_height = highest_y2 + border_width  # Adjust as needed
    # image_width = 1180
    # image_height = 1180
    # image_width = 7650
    background_color = (255, 255, 255)  # White

    # Create an Image object
    image = Image.new("RGB", (int(highest_x2 + b_width), int(highest_y2 + b_width)), background_color)

    # Create a drawing object to draw on the image
    draw = ImageDraw.Draw(image)

    # Define colors for rectangles
    outline_color = (64, 64, 64)  # Dark grey
    fill_color = (192, 192, 192)  # Light grey

    print(obstruction_coordinates)

    # Iterate through the list of coordinates and draw rectangles
    def draw_circle(list, outline_color, fill_color, radius=40):
        for coords in list:
            x, y, z = coords
            right_lower = (int(x) + radius, int(y) + radius) 
            left_upper = (int(x) - radius, int(y) - radius)
            draw.ellipse([left_upper, right_lower], outline=outline_color, fill=fill_color, width=5)
    def draw_rect(list, outline_color, fill_color):
        for coords in list:
            x1, x2, y1, y2, z1, z2 = coords
            left_upper = (int(x1), int(y1)) 
            right_lower = (int(x2), int(y2))
            draw.rectangle([left_upper, right_lower], outline=outline_color, fill=fill_color, width=20)

    for coords in obstruction_coordinates:
        x1, x2, y1, y2, z1, z2 = coords

        temp_list = []  ### couldnt work out the if statement so this monstrosity checks creates a list of numbers to check against
        n = z1
        temp_list.append(n)
        n = n+0.1
        while n < z2:
            temp_list.append(n)
            n=n+0.1
        temp_list.append(z2)
            
        for num in temp_list:
            if num >= z_cut_low and num <= z_cut_high:
                left_upper = (int(x1), int(y1))
                right_lower = (int(x2), int(y2))
                draw.rectangle([left_upper, right_lower], outline=outline_color, fill=fill_color)
    # create object for each type of obstruction - legend
    legend_object = {
        "fire": {
            "color": "red",
            "label": "Fire",
            "outline": "black",
            "width": 20,
            "shape": "rect",
            "points": fire_locations  
        },
        "sprinkler": {
            "color": "blue",
            "label": "Sprinkler",
            "outline": "blue",
            "width": 10,
            "radius": 40,
            "shape": "circle",
            "points": sprinkler_locations        
        },
        "sensor": {
            "color": "yellow",
            "label": "Point Sensor",
            "outline": "black",
            "width": 10,
            "radius": 40,
            "shape": "circle",
            "points": sensor_locations      
        },
        "aov": {
            "color": "white",
            "label": "AOV",
            "outline": "black",
            "width": 20,
            "shape": "rect",
            "points": aov_locations
        },
        "inlet": {
            "color": "grey",
            "label": "Inlet",
            "outline": "red",
            "width": 20,
            "shape": "rect",
            "points": inlet_locations
        },
        "mech_vent": {
            "color": "black",
            "label": "Mech Vent",
            "outline": "green",
            "width": 20,
            "shape": "rect",
            "points": mech_vent_locations
        },
        "flat_door": {
            "color": "black",
            "label": "Flat Door",
            "outline": "green",
            "width": 20,
            "shape": "rect",
            "points": flat_door_locations
        },
        "stair_door": {
            "color": "black",
            "label": "Stair Door",
            "outline": "green",
            "width": 20,
            "shape": "rect",
            "points": stair_door_locations
        },
        "misc_door": {
            "color": "black",
            "label": "Misc Door",
            "outline": "green",
            "width": 20,
            "shape": "rect",
            "points": misc_door_locations
        },
    }
    from draw_legend import create_legend
    create_legend(legend_object)
    draw_rect(fire_locations, "black", "red")
    draw_rect(aov_locations, "black", "white")
    draw_rect(inlet_locations, "red", "grey")
    draw_rect(mech_vent_locations, "green", "black")
    draw_rect(flat_door_locations, "green", "black")
    draw_rect(stair_door_locations, "green", "black")
    draw_rect(misc_door_locations, "green", "black")

    draw_circle(sensor_locations, "black", "yellow")
    draw_circle(sprinkler_locations, "blue", "blue")




    # Save the image as a JPEG
    # Show the image (optional)
    save_dir = 'dev_folder'
    image.save(f"{save_dir}/fds.png")
    image.show()


if __name__ == "__main__":
    # Your code here
    fds_draw_clone()