import os
from flask import Flask, request, render_template_string
from PIL import Image, ImageDraw, ImageFont
import docx
import cloudinary
import cloudinary.uploader
import uuid

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp/uploads'
TEMPLATE_IMAGE_PATH = '3.jpeg'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configure Cloudinary
cloudinary.config(
    cloud_name="dyku0f083",
    api_key='689469863154634',
    api_secret='5oVW4WKCh7sTlJfqAlaYnObYtpY'
)

# Extract matches from DOCX
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

# Parse structured match data
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

# Wrap long text
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

# Draw text and upload to Cloudinary
def add_text_to_template(stat_text, match_name, stat_title, template_image_path):
    img = Image.open(template_image_path)
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype("CalSans-Regular.ttf", 100)
    heading_font = ImageFont.truetype("BebasNeue-Regular.ttf", 100)
    body_font = ImageFont.truetype("BebasNeue-Regular.ttf", 80)

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
    y_position = text_position[1]

    for i, line in enumerate(lines):
        font = body_font
        text_color = "white" if i == 0 else "lightgreen" if i == 1 else "yellow"
        wrapped_lines = wrap_text(line, font, max_width, draw)

        for wrapped_line in wrapped_lines:
            text_width, _ = draw.textbbox((0, 0), wrapped_line, font=font)[2:4]
            x_position = (img.width - text_width) // 2
            draw.text((x_position + shadow_offset, y_position + shadow_offset), wrapped_line, font=font, fill=(0, 0, 0))
            draw.text((x_position, y_position), wrapped_line, font=font, fill=text_color)
            y_position += 70

        y_position += 65

    tmp_image_path = f"/tmp/{uuid.uuid4()}.png"
    img.save(tmp_image_path)

    # Upload to Cloudinary
    upload_result = cloudinary.uploader.upload(tmp_image_path)
    os.remove(tmp_image_path)
    return upload_result['secure_url']

# Process matches and return image URLs
def generate_images_and_upload(matches_data):
    cloudinary_urls = []

    for match in matches_data:
        match_name = match['Match']
        stats = match['Stats']

        for stat_title, stat_text in stats.items():
            url = add_text_to_template(stat_text, match_name, stat_title, TEMPLATE_IMAGE_PATH)
            cloudinary_urls.append((match_name, stat_title, url))

    return cloudinary_urls

# HTML form
@app.route('/')
def home():
    return render_template_string("""
        <html><body>
        <h1>Upload your DOCX file to generate match images</h1>
        <form action="/upload" method="POST" enctype="multipart/form-data">
            <input type="file" name="docx_file" required>
            <input type="submit" value="Upload_and_wait">
        </form>
        </body></html>
    """)

# Handle file upload and display Cloudinary URLs
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
    uploaded_urls = generate_images_and_upload(match_data)

    # Render result
    html_output = "<h2>Generated Image URLs:</h2><ul>"
    for match_name, stat_title, url in uploaded_urls:
        html_output += f"<li><strong>{match_name} - {stat_title}</strong>: <a href='{url}' target='_blank'>{url}</a></li>"
    html_output += "</ul>"
    return html_output

# Run app
if __name__ == "__main__":
    app.run(debug=True)
