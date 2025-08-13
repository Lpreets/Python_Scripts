import os
import json

def update_file_index(folder_path, index_path):
    file_index = {}
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            relative_path = os.path.relpath(os.path.join(root, file), folder_path)
            file_index[relative_path] = relative_path

    # Ensure the index_path includes the filename
    if not index_path.endswith('file_index.json'):
        index_path = os.path.join(index_path, 'file_index.json')
    
    with open(index_path, 'w') as json_file:
        json.dump(file_index, json_file, indent=4)

def main():
    extracted_folder_path = input("Enter the path to the extracted files folder: ")
    file_index_path = input("Enter the path where file_index.json should be saved: ")
    update_file_index(extracted_folder_path, file_index_path)

if __name__ == "__main__":
    main()
