from bs4 import BeautifulSoup
import os

def split_html_into_chunks(directory_path, output_dir):
    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Loop through each HTML file in the directory
    for file_name in os.listdir(directory_path):
        if file_name.endswith('.html'):
            file_path = os.path.join(directory_path, file_name)
            print(f"Processing file: {file_name}")  # Debug: Check which file is being processed

            # Read the raw HTML content
            with open(file_path, 'r') as file:
                html_content = file.read()

            soup = BeautifulSoup(html_content, "lxml")

            # Find the main heading (e.g., 4.1301 Policy, 3.1002 Policy, etc.)
            heading = soup.find('h1', class_='title')
            heading_text = heading.get_text().strip() if heading else "No Heading"
            print(f"Found heading: {heading_text}")  # Debug: Check heading text

            # Find subsections (e.g., (a), (b), (1), etc.) in <p> tags
            subsections = soup.find_all('p', class_='ListL1')  # For (a), (b), etc.
            subsection_texts = []

            for subsection in subsections:
                subsection_number = subsection.find('span', class_='ph autonumber')
                if subsection_number:
                    # Clean up the text and number
                    subsection_text = subsection.get_text().strip()
                    subsection_texts.append(f"{subsection_number.get_text()} {subsection_text}")

            # If subsections exist, create the section tuple (heading, subsections)
            if subsection_texts:
                sections = [(heading_text, "\n".join(subsection_texts))]
            else:
                sections = [(heading_text, "No subsections found.")]

            # Save the sections into a text file
            output_file_path = os.path.join(output_dir, f"{file_name}_chunks.txt")
            with open(output_file_path, 'w') as output_file:
                for heading, section_text in sections:
                    output_file.write(f"Heading: {heading}\n")
                    output_file.write(f"Text: {section_text}\n\n")

            print(f"Saved chunks for {file_name} to {output_file_path}")  # Debug: Check where it's saved


# Example usage
directory_path = "/Users/collinschreyer/GSA/FAR_BOT/dita_html"  # Path to your HTML files
output_dir = "/Users/collinschreyer/GSA/FAR_BOT/dita_html/chunks"  # Directory to save the chunks

# Process the raw HTML files and extract chunks
split_html_into_chunks(directory_path, output_dir)
