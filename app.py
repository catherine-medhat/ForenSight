from flask import Flask, render_template, request, send_file, jsonify
import pandas as pd
from datetime import timedelta
import re
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# Function to parse the text and extract relevant information from 'Join status text'
def parse_joined_text(text):
    if isinstance(text, str):
        patterns = {
            'hours': r'(\d+) hours ago',
            'days': r'(\d+) days ago',
            'weeks': r'(\d+) weeks ago',
            'months': r'about (\d+) months ago',
            'years': r'about (\d+) years ago'
        }

        # Iterate over patterns to find matches in text
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                value = int(match.group(1))
                # Convert matched time to timedelta object based on the key
                if key == 'hours':
                    return timedelta(hours=value)
                elif key == 'days':
                    return timedelta(days=value)
                elif key == 'weeks':
                    return timedelta(weeks=value)
                elif key == 'months':
                    return timedelta(days=value * 30)   # Approximate month as 30 days
                elif key == 'years':
                    return timedelta(days=value * 365)  # Approximate year as 365 days
    return pd.NaT # Return NaT (Not a Time) for non-matching or invalid text

# Function to calculate the fake probability level for each member
def calculate_fake_probability(row):
    fake_probability = 0
    # Check if the account is verified
    if row['Is verified'] == 1:
        row['Is verified'] = True
    else:
        row['Is verified'] = False
    # Check various factors and increment fake_probability accordingly
    if row['Is verified']:
        return 'Level 1 (0% fake)' # Verified accounts have 0% fake probability
    if pd.isnull(row['Is verified']) or row['Is verified'] == 0:
        fake_probability += 20 # Non-verified accounts have additional fake probability
    if pd.isnull(row['Mobile']):
        fake_probability += 20 # Missing mobile number adds to fake probability
    if pd.isnull(row['User Name']):
        fake_probability += 20 # Missing user name adds to fake probability
    if pd.isnull(row['avatar']):
        fake_probability += 20 # Missing avatar adds to fake probability
    if not pd.isnull(row['Days Joined']) and row['Days Joined'] < timedelta(days=90):
        fake_probability += 20 # Accounts joined less than 90 days ago have additional fake probability
     # Determine the fake probability level based on accumulated fake_probability
    if fake_probability >= 80:
        return 'Level 5 (80% fake)'
    elif fake_probability >= 60:
        return 'Level 4 (60% fake)'
    elif fake_probability >= 40:
        return 'Level 3 (40% fake)'
    elif fake_probability >= 20:
        return 'Level 2 (20% fake)'
    else:
        return 'Level 1 (0% fake)'

# Route for the home page
@app.route('/')
def home():
    return render_template('index.html', show_results=False) # Render the index.html template

# Route for handling file uploads and processing
@app.route('/upload', methods=['POST'])
def upload():
    file1 = request.files['file1'] # Get the first uploaded file
    file2 = request.files['file2'] # Get the second uploaded file

    # Ensure that both files are uploaded
    if not file1 or not file2:
        return 'Please upload both files.', 400

    # Save the uploaded files
    file1_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file1.filename))
    file2_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file2.filename))
    file1.save(file1_path)
    file2.save(file2_path)

    # Load both sheets from the Excel file
    sheet1_df = pd.read_excel(file1_path)
    sheet2_df = pd.read_excel(file2_path)

    # Merge the two sheets based on the 'ID' and 'User Id' columns, using all values from both sheets
    merged_df = pd.merge(sheet1_df, sheet2_df, left_on='ID', right_on='User Id', how='outer')

    # Merge the 'Name' and 'Username' columns from both sheets
    merged_df['Name'] = merged_df.apply(lambda row: row['Name'] if pd.notnull(row['Name']) else row['Username'], axis=1)

    # Merge the 'Link' and 'Profile URL' columns from both sheets
    merged_df['Link'] = merged_df.apply(lambda row: row['Link'] if pd.notnull(row['Link']) else row['Profile URL'], axis=1)

    # Drop original merged columns
    merged_df = merged_df.drop(columns=['Username', 'Profile URL'])

    # Reorder columns
    column_order = ['ID', 'Name', 'User Name', 'Mobile', 'Gender', 'Is verified',
                    'Work', 'Hometown', 'Location',
                    'Join status text', 'Link', 'avatar']
    merged_df = merged_df[column_order]

    # Apply the function to the 'Joined' column to calculate 'Days Joined'
    merged_df['Days Joined'] = merged_df['Join status text'].apply(parse_joined_text)

    # Drop duplicate rows based on matching IDs
    merged_df.drop_duplicates(subset='ID', keep='first', inplace=True)

    # Add a new column specifying the level of each member
    merged_df['Fake Probability'] = merged_df.apply(calculate_fake_probability, axis=1)

    # Count the number of users for each fake probability level
    fake_probability_counts = merged_df['Fake Probability'].value_counts().to_dict()

    # Save the merged DataFrame to a new Excel file
    output_filename = os.path.join(app.config['UPLOAD_FOLDER'], 'auto_data_with_level.xlsx')
    merged_df.to_excel(output_filename, index=False)

    # Return JSON response with number of users, fake probability counts, and indication to show results
    return jsonify({'num_users': len(merged_df), 'fake_probability_counts': fake_probability_counts, 'show_results': True})

# Route for downloading selected data based on fake probability level
@app.route('/download', methods=['POST'])
def download():
    selected_level = request.form['level'] # Get the selected fake probability level from the form

    # Read the Excel file with analyzed data
    input_filename = os.path.join(app.config['UPLOAD_FOLDER'], 'auto_data_with_level.xlsx')
    df = pd.read_excel(input_filename)

    # Filter the DataFrame based on the selected level
    filtered_df = df[df['Fake Probability'] == selected_level]

    # Extract name, profile url, and level to a new Excel file
    output_filename = os.path.join(app.config['UPLOAD_FOLDER'], 'selected_data.xlsx')
    filtered_df[['Name', 'Link', 'Fake Probability']].to_excel(output_filename, index=False)

    return send_file(output_filename, as_attachment=True)

# Route for getting data for the pie chart
@app.route('/get_pie_data')
def get_pie_data():
    # Read the Excel file with analyzed data
    input_filename = os.path.join(app.config['UPLOAD_FOLDER'], 'auto_data_with_level.xlsx')
    df = pd.read_excel(input_filename)

    # Count the number of users for each fake probability level
    fake_probability_counts = df['Fake Probability'].value_counts().to_dict()

    return jsonify(fake_probability_counts)

if __name__ == '__main__':
    app.run(debug=True)
