import os
from bs4 import BeautifulSoup

def extract_text_from_html_files(directory_path):
    # List all HTML files in the directory
    html_files = [f for f in os.listdir(directory_path) if f.endswith('.html')]
    
    all_text = []
    
    # Loop through each HTML file
    for html_file in html_files:
        file_path = os.path.join(directory_path, html_file)
        
        # Extract text from the HTML file
        with open(file_path, "r") as file:
            html_content = file.read()
        
        soup = BeautifulSoup(html_content, "lxml")
        text = soup.get_text()  # Extract text content
        
        all_text.append((html_file, text))  # Store the filename and extracted text
    
    return all_text

# Replace with your directory path
directory_path = "/Users/collinschreyer/GSA/FAR_BOT/dita_html"  

# Extract text from HTML files
extracted_texts = extract_text_from_html_files(directory_path)

# Verify the number of files processed
print(f"Total HTML files in the directory: {len(extracted_texts)}")

# Create an output directory if it doesn't exist
output_dir = directory_path  # Save in the same directory
os.makedirs(output_dir, exist_ok=True)

# Save each extracted text to a separate .txt file in the same directory
for filename, text in extracted_texts:
    output_path = os.path.join(output_dir, f"{filename}.txt")
    with open(output_path, "w") as f:
        f.write(text)
    print(f"Saved extracted text for {filename} to {output_path}")
