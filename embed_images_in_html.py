#!/usr/bin/env python3
"""
Embed images as base64 data URIs directly into HTML files.
Makes HTML files completely self-contained with no external dependencies.
"""

import base64
import re
from pathlib import Path


def image_to_base64(image_path):
    """Convert an image file to a base64 data URI."""
    with open(image_path, 'rb') as img_file:
        img_data = img_file.read()
        b64_data = base64.b64encode(img_data).decode('utf-8')
        
        # Determine MIME type from extension
        ext = image_path.suffix.lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.webp': 'image/webp'
        }
        mime_type = mime_types.get(ext, 'image/png')
        
        return f"data:{mime_type};base64,{b64_data}"


def embed_images_in_html(html_file, image_mappings):
    """
    Replace image src attributes with base64 data URIs.
    
    Args:
        html_file: Path to the HTML file
        image_mappings: Dict mapping image paths in HTML to actual file paths
    """
    print(f"\n📄 Processing: {html_file}")
    
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    replacements_made = 0
    
    for html_path, file_path in image_mappings.items():
        if html_path in content:
            if Path(file_path).exists():
                print(f"  🖼️  Embedding: {html_path}")
                base64_uri = image_to_base64(Path(file_path))
                content = content.replace(f'src="{html_path}"', f'src="{base64_uri}"')
                replacements_made += 1
            else:
                print(f"  ⚠️  Warning: Image not found: {file_path}")
    
    if replacements_made > 0:
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✅ Embedded {replacements_made} images")
    else:
        print(f"  ℹ️  No images to embed")


def main():
    print("🎨 Embedding Images in HTML Files")
    print("=" * 50)
    
    # Define image mappings for FAR_Bot_Journey.html
    far_bot_mappings = {
        'FAR_BOT_CHARACTER/FAR_BOT_HAS_IDEA.png': 'FAR_BOT_CHARACTER/FAR_BOT_HAS_IDEA.png',
        'FAR_BOT_CHARACTER/FAR_BOT_RESEARCHING.png': 'FAR_BOT_CHARACTER/FAR_BOT_RESEARCHING.png',
        'FAR_BOT_CHARACTER/FAR_BOT_THINKING.png': 'FAR_BOT_CHARACTER/FAR_BOT_THINKING.png',
        'FAR_BOT_CHARACTER/FAR_BOT_PRESENTING.png': 'FAR_BOT_CHARACTER/FAR_BOT_PRESENTING.png',
        'FAR_BOT_CHARACTER/FAR_BOT.png': 'FAR_BOT_CHARACTER/FAR_BOT.png',
    }
    
    # Process FAR_Bot_Journey.html
    if Path('FAR_Bot_Journey.html').exists():
        embed_images_in_html('FAR_Bot_Journey.html', far_bot_mappings)
    
    # Process FAR_Bot_Journey copy.html if it exists
    if Path('FAR_Bot_Journey copy.html').exists():
        embed_images_in_html('FAR_Bot_Journey copy.html', far_bot_mappings)
    
    # Process far_chatbot_demo.html if it exists
    if Path('far_chatbot_demo.html').exists():
        embed_images_in_html('far_chatbot_demo.html', far_bot_mappings)
    
    # For tss_ai_pipeline_building_journey.html, we need to check if the logo files exist
    tss_logo_mappings = {}
    
    # Check for B&A logo
    ba_logo_path = '/Users/collinschreyer/Desktop/TSS_PART_2/B_A_LOGO_WHITE_BG.png'
    if Path(ba_logo_path).exists():
        tss_logo_mappings[ba_logo_path] = ba_logo_path
    else:
        print(f"\n⚠️  B&A Logo not found at: {ba_logo_path}")
        print("   Please provide the correct path or copy the file to the project directory")
    
    # Check for USAI logo
    usai_logo_path = '/Users/collinschreyer/Desktop/TSS_PART_2/usai_logo.png'
    if Path(usai_logo_path).exists():
        tss_logo_mappings[usai_logo_path] = usai_logo_path
    else:
        print(f"\n⚠️  USAI Logo not found at: {usai_logo_path}")
        print("   Please provide the correct path or copy the file to the project directory")
    
    if Path('tss_ai_pipeline_building_journey.html').exists() and tss_logo_mappings:
        embed_images_in_html('tss_ai_pipeline_building_journey.html', tss_logo_mappings)
    
    print("\n" + "=" * 50)
    print("✨ Done! Your HTML files now contain embedded images.")
    print("   They are completely self-contained and portable.")


if __name__ == '__main__':
    main()
