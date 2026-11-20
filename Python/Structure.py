import glob
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Passages where [???] belongs to $her
HER_PASSAGES = {
    "Prologue-1-1",
    "Prologue-1-2",
    "Prologue-1-3",
    "Prologue-1-4",
}

CHARACTER_MAP = {
    "Nia": "$nia",
    "Eto": "$eto",
    "Tianshi": "$tianshi",
    "Amiya": "$amiya",
    "Swire": "$swire",
}

def convert_twee(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split the .twee file into individual passages starting with ":: PassageName"
    passage_blocks = re.split(r"(^:: .*$)", content, flags=re.MULTILINE)
    
    header_pattern = re.compile(r"\(text-colour:grey\)\[([^\]]+)\]\s*")
    converted_count = 0
    unmatched = []

    current_passage = ""

    for i in range(len(passage_blocks)):
        block = passage_blocks[i]
        
        if block.startswith(":: "):
            # Extract clean passage name (ignoring [tags] or {"position":...} metadata)
            raw_title = block[3:].strip()
            current_passage = re.split(r"\s+\[|\s+\{", raw_title)[0].strip()
        else:
            def replace_match(match):
                nonlocal converted_count
                display_name = match.group(1).strip()

                # Special rule: [???] is $her ONLY in Prologue-1-1 to Prologue-1-4
                if display_name == "???":
                    if current_passage in HER_PASSAGES:
                        var_name = "$her"
                    else:
                        unmatched.append((current_passage, display_name))
                        return match.group(0)
                elif display_name in CHARACTER_MAP:
                    var_name = CHARACTER_MAP[display_name]
                else:
                    unmatched.append((current_passage, display_name))
                    return match.group(0)

                converted_count += 1
                return (
                    f"(set: $speaker to {var_name}'s name)\n"
                    f"(print: '<img src=\"' + {var_name}'s neutral + '\" class=\"char-portrait\">')\n"
                )

            passage_blocks[i] = header_pattern.sub(replace_match, block)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("".join(passage_blocks))

    print(f"File: {os.path.basename(input_path)}")
    print(f"  Converted {converted_count} character headers -> {os.path.basename(output_path)}")

    if unmatched:
        print("  Left untouched (for manual review):")
        for passage, name in unmatched:
            print(f"    - [{name}] in '{passage}'")
    print("-" * 40)

def main():
    # Find all .twee files in the script's folder, excluding already-converted outputs
    twee_files = [
        f for f in glob.glob(os.path.join(BASE_DIR, "*.twee"))
        if not f.endswith("_updated.twee")
    ]

    if not twee_files:
        print(f"No .twee files found in: {BASE_DIR}")
        return

    for input_path in twee_files:
        base_name, ext = os.path.splitext(input_path)
        output_path = f"{base_name}_updated{ext}"
        convert_twee(input_path, output_path)

if __name__ == "__main__":
    main()
