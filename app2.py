import os
import zipfile
from flask import Flask, request, send_from_directory, render_template_string
from PIL import Image, ImageDraw, ImageFont
import docx
import json
import uuid

app = Flask(__name__)

# Updated writable paths
UPLOAD_FOLDER = '/tmp/uploads'
OUTPUT_FOLDER = '/tmp/generated_images'

# Ensure folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Function to extract matches from DOCX
def extract_matches_from_docx(doc_path):
    doc = docx.Document(doc_path)
    match_data = []
    current_match = ""

    for para in doc.paragraphs:
        para_text = para.text.strip()
        if para_text.startswith("Date"):
            if current_match:
                match_data.append(current_match.strip())
            current_match = para_text
        else:
            current_match += "\n" + para_text

    if current_match:
        match_data.append(current_match.strip())

    return match_data

# Function to parse match data
def parse_match_data(text):
    lines = text.strip().split('\n')
    matches, current_stats = [], {}
    current_match, current_heading, stat_lines = None, None, []
    line_index = 0

    while line_index < len(lines):
        line = lines[line_index].strip()
        if not line or line.startswith('====='):
            line_index += 1
            continue
        if line == 'Multi Bet':
            line_index += 1
            continue
        if line.startswith('Date'):
            if current_match:
                if current_heading and len(stat_lines) == 3:
                    current_stats[current_heading] = '\n'.join(stat_lines)
                current_match['Stats'] = current_stats
                matches.append(current_match)
            if line_index + 1 >= len(lines):
                raise ValueError("Incomplete match: Missing Match line after Date")
            current_match = {
                'Date': line.replace('Date', '').strip(),
                'Match': lines[line_index + 1].replace('Match', '').strip()
            }
            current_stats = {}
            current_heading = None
            stat_lines = []
            line_index += 2
            continue
        if current_heading:
            stat_lines.append(line)
            if len(stat_lines) == 3:
                current_stats[current_heading] = '\n'.join(stat_lines)
                current_heading = None
                stat_lines = []
            line_index += 1
            continue
        if not current_match:
            raise ValueError(f"Heading '{line}' found before a Date/Match block")
        current_heading = line
        stat_lines = []
        line_index += 1

    if current_match:
        if current_heading and len(stat_lines) == 3:
            current_stats[current_heading] = '\n'.join(stat_lines)
        current_match['Stats'] = current_stats
        matches.append(current_match)

    return matches

# Wrap long text to fit image
def wrap_text(text, font, max_width, draw):
    lines = []
    words = text.split()
    current_line = ''
    for word in words:
        test_line = current_line + ' ' + word if current_line else word
        _, _, width, _ = draw.textbbox((0, 0), test_line, font=font)
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines

# Draw text on image
def add_text_to_template(stat_text, match_name, stat_title, template_image_path, output_image_path):
    img = Image.open(template_image_path)
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype("CalSans-Regular.ttf", 100)
    heading_font = ImageFont.truetype("BebasNeue-Regular.ttf", 100)
    body_font_1 = ImageFont.truetype("BebasNeue-Regular.ttf", 80)
    body_font_2 = ImageFont.truetype("BebasNeue-Regular.ttf", 80)
    body_font_3 = ImageFont.truetype("BebasNeue-Regular.ttf", 80)

    max_width = 1200
    title_position = (600, 150)
    heading_position = (800, 400)
    text_position = (400, 600)

    title_width, title_height = draw.textbbox((0, 0), match_name, font=title_font)[2:4]
    title_position = ((img.width - title_width) // 2, 150)

    shadow_offset = 3
    draw.text((title_position[0] + shadow_offset, title_position[1] + shadow_offset), match_name, font=title_font, fill=(0, 0, 0))
    draw.text(title_position, match_name, font=title_font, fill=(255, 255, 255))

    heading_width, heading_height = draw.textbbox((0, 0), stat_title, font=heading_font)[2:4]
    heading_position = ((img.width - heading_width) // 2, 400)

    draw.text((heading_position[0] + shadow_offset, heading_position[1] + shadow_offset), stat_title, font=heading_font, fill=(0, 0, 0))
    draw.text(heading_position, stat_title, font=heading_font, fill=(255, 215, 0))

    lines = stat_text.split('\n')
    default_line_height = 65
    wrapped_line_height = 70
    y_position = text_position[1]

    for i, line in enumerate(lines):
        if i == 0:
            font = body_font_1
            text_color = "white"
        elif i == 1:
            font = body_font_2
            text_color = "lightgreen"
        else:
            font = body_font_3
            text_color = "yellow"

        wrapped_text = wrap_text(line, font, max_width, draw)

        for wrapped_line in wrapped_text:
            text_width, text_height = draw.textbbox((0, 0), wrapped_line, font=font)[2:4]
            wrapped_line_position = ((img.width - text_width) // 2, y_position)

            draw.text((wrapped_line_position[0] + shadow_offset, wrapped_line_position[1] + shadow_offset), wrapped_line, font=font, fill=(0, 0, 0))
            draw.text(wrapped_line_position, wrapped_line, font=font, fill=text_color)
            y_position += wrapped_line_height

        y_position += default_line_height

    img.save(output_image_path)
    print(f"Image saved as: {output_image_path}")

# ZIP all images
def create_zip_from_images(output_folder, zip_filename):
    zip_file_path = f"{output_folder}/{zip_filename}.zip"
    with zipfile.ZipFile(zip_file_path, 'w') as zipf:
        for foldername, subfolders, filenames in os.walk(output_folder):
            for filename in filenames:
                file_path = os.path.join(foldername, filename)
                zipf.write(file_path, os.path.relpath(file_path, output_folder))
    return zip_file_path

# Generate images for all matches
def generate_images_for_stats_with_template(matches_data, template_image_path, output_folder):
    for match in matches_data:
        match_date = match['Date']
        match_name = match['Match']
        stats = match['Stats']

        match_folder = f"{output_folder}/{match_date}_{match_name.replace(' ', '_').replace('/', '_')}"
        os.makedirs(match_folder, exist_ok=True)

        for stat_title, stat_text in stats.items():
            image_output_path = f"{match_folder}/{stat_title.replace(' ', '_')}.png"
            add_text_to_template(stat_text, match_name, stat_title, template_image_path, image_output_path)

# HTML upload form
@app.route('/')
def home():
    return render_template_string("""
        <html><body>
        <h1>Upload your DOCX file to generate images</h1>
        <form action="/upload" method="POST" enctype="multipart/form-data">
            <input type="file" name="docx_file">
            <input type="submit" value="Upload">
        </form>
        </body></html>
    """)

# Upload and process file
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'docx_file' not in request.files:
        return "No file part"
    file = request.files['docx_file']
    if file.filename == '':
        return "No selected file"

    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    matches = extract_matches_from_docx(file_path)
    match_data = parse_match_data("\n".join(matches[1:]))
    template_image_path = '3.jpeg'

    generate_images_for_stats_with_template(match_data, template_image_path, OUTPUT_FOLDER)

    zip_filename = str(uuid.uuid4())
    zip_path = create_zip_from_images(OUTPUT_FOLDER, zip_filename)

    return send_from_directory(directory=OUTPUT_FOLDER, path=f"{zip_filename}.zip", as_attachment=True)

# Run app
if __name__ == "__main__":
    app.run(debug=True)
