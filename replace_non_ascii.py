import os
import re
import time
from unidecode import unidecode

# Mapping for specific characters
character_mapping = {
    'æ': 'ae',
    'ø': 'oo',
    'å': 'aa',
    'Æ': 'Ae',
    'Ø': 'Oo',
    'Å': 'Aa'
}

def replace_non_ascii(word):
    """
    Replace non-ASCII characters in a word based on the character_mapping.
    """
    new_word = ""
    for char in word:
        if char in character_mapping:
            new_word += character_mapping[char]
        else:
            new_word += unidecode(char) if not char.isascii() else char
    return new_word

def rename_file_or_directory(path):
    directory, filename = os.path.split(path)
    new_filename = ''.join(replace_non_ascii(char) for char in filename)
    new_path = os.path.join(directory, new_filename)
    
    # Check if new_path already exists and adjust the name if necessary
    if os.path.exists(new_path) and path != new_path:
        base, extension = os.path.splitext(new_filename)
        counter = 1
        while os.path.exists(new_path):
            new_filename = f"{base}_{counter}{extension}"
            new_path = os.path.join(directory, new_filename)
            counter += 1
    
    if path != new_path:
        print(f"Renaming '{path}' to '{new_path}'")
        os.rename(path, new_path)
    
    return new_path

def process_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
    except UnicodeDecodeError:
        print(f"Skipping binary file: {filepath}")
        return

    # Replace non-ASCII characters in content
    words_to_replace = {word: replace_non_ascii(word) for word in re.findall(r'\b\w+\b', content) if any(not c.isascii() for c in word)}

    for old_word, new_word in words_to_replace.items():
        content = content.replace(old_word, new_word)

    with open(filepath, 'w', encoding='utf-8') as file:
        file.write(content)
    print(f"Processed file: {filepath}")

def process_directory(directory):
    for root, dirs, files in os.walk(directory, topdown=False):
        # Rename directories first
        for dir in dirs:
            dirpath = os.path.join(root, dir)
            new_dirpath = rename_file_or_directory(dirpath)
            # Update the directory name in the list
            if new_dirpath != dirpath:
                dirs[dirs.index(dir)] = os.path.basename(new_dirpath)
            time.sleep(0.1)  # Add a short delay
        
        # Rename files
        for file in files:
            filepath = os.path.join(root, file)
            new_filepath = rename_file_or_directory(filepath)
            process_file(new_filepath)
            time.sleep(0.1)  # Add a short delay

if __name__ == "__main__":
    directory = input("Enter the path to the directory: ")
    process_directory(directory)
    print("Processing complete. All non-ASCII characters have been replaced.")
