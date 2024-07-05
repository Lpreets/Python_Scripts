import os
from psd_tools import PSDImage
from PIL import Image

def convert_psd_to_png(psd_path, output_path):
    try:
        psd = PSDImage.open(psd_path)
        composite_image = psd.composite()
        
        if composite_image.mode == 'CMYK':
            composite_image = composite_image.convert('RGB')
        
        composite_image.save(output_path)
        print(f"Converted: {psd_path} -> {output_path}")
    except Exception as e:
        print(f"Failed to convert {psd_path}: {e}")

def main():
    # Get the input directory from the user
    input_dir = input("Enter the directory containing PSD files: ").strip()
    output_dir = input("Enter the directory to save PNG files: ").strip()

    if not os.path.isdir(input_dir):
        print("The specified input directory does not exist.")
        return

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # Iterate over all files in the input directory
    for filename in os.listdir(input_dir):
        if filename.lower().endswith('.psd'):
            psd_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, os.path.splitext(filename)[0] + '.png')
            convert_psd_to_png(psd_path, output_path)

if __name__ == "__main__":
    main()
