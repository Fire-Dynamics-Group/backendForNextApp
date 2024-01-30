from PIL import Image, ImageDraw, ImageFont

def create_legend(legend_object, save_path='legend.png'):
    # Font for text in the legend
    font_location = 'SEGOEUIL.TTF'#'C:\Windows\Fonts\Segoe UI\SEGOEUIL.TTF.ttf' #SEGOEUIL.TTF
    font = ImageFont.truetype(font_location, 16)
    # font = ImageFont.load_default()

    # Calculate the size of the legend image
    # find max width of text in legend
    labels = [legend_object[f]['label'] for f in legend_object]
    max_label_width = max([len(f) for f in labels]) * 5
    box_height = 20
    box_width = 20
    padding = 5
    text_padding = 40
    legend_width = box_width + text_padding + padding * 2 + max_label_width
    legend_height = len(legend_object) * (box_height + padding) + 2*padding

    # Create a new image for the legend
    legend_img = Image.new('RGB', (legend_width, legend_height), color = (255, 255, 255))
    d = ImageDraw.Draw(legend_img)

    # Starting position for the legend
    x = 10
    y = 10

    # Draw each item in the legend
    for name, sub_obj in legend_object.items():
        if sub_obj['points']:

            # Draw the color box
            if sub_obj['shape'] == 'rect':
                d.rectangle([x, y, x + box_width, y + box_height], fill=sub_obj['color'], outline=sub_obj['outline'], width=5)
            else:
                d.ellipse([x, y, x + box_width, y + box_height], fill=sub_obj['color'], outline=sub_obj['outline'])

            # Draw the label text
            d.text((x + box_width + padding, y), sub_obj['label'], fill=(0,0,0), font=font)

            # Move to the next item position
            y += box_height + padding

    # Save the legend image
    legend_img.save(save_path)
