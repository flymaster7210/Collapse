import re
import json
from pathlib import Path
from collections import deque

# ==========================================
# CONFIGURATION
# ==========================================
X_SPACING = 210  # Horizontal spacing between steps
Y_SPACING = 150  # Vertical spacing between parallel branches
SCENE_GAP = 320  # Extra vertical gap between major sections/days
START_X = 100
START_Y = 100


def parse_twee(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    raw_blocks = re.split(r"(?m)^::\s+", text)
    passages = []
    meta_blocks = []

    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.splitlines()
        header = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        body = body.replace(r"\$", "$")

        match = re.match(r"^([^\[\{]+?)(?:\s*(\[[^\]]*\]))?(?:\s*(\{.*\}))?$", header)
        if match:
            title = match.group(1).strip()
            tags = match.group(2) or ""
        else:
            title = header
            tags = ""

        if title in ("StoryTitle", "StoryData"):
            meta_blocks.append((title, tags, body))
            continue

        links = []
        for link_match in re.finditer(r"\[\[([^\]]+)\]\]", body):
            inner = link_match.group(1)
            if "->" in inner:
                target = inner.split("->", 1)[1].strip()
            elif "<-" in inner:
                target = inner.split("<-", 1)[0].strip()
            elif "|" in inner:
                target = inner.split("|", 1)[1].strip()
            else:
                target = inner.strip()
            if target not in links:
                links.append(target)

        passages.append({
            "title": title,
            "tags": tags,
            "body": body,
            "links": links,
            "parents": [],
        })

    return meta_blocks, passages


def get_scene_group(title, tags):
    """Groups passages into clean horizontal swimlanes by Act/Day."""
    if "startup" in tags.lower() or title in ("Start", "NotSlop", "CreditsSlop") or title.startswith("Intro-"):
        return 0  # Intro & Title
    if title == "Prologue-Title" or title.startswith("Prologue-Day1") or title.startswith("Prologue-1-"):
        return 1  # Day 1
    if title.startswith("Prologue-Day2") or title.startswith("Prologue-2-"):
        return 2  # Day 2
    if title.startswith("Prologue-Day3") or title.startswith("Prologue-3-"):
        return 3  # Day 3
    if title.startswith("Day4") or title.startswith("Prologue-4-"):
        return 4  # Day 4
    return 5


def calculate_clean_layout(passages):
    if not passages:
        return

    passage_map = {p["title"]: p for p in passages}

    # Build reverse parent pointers
    for p in passages:
        for target in p["links"]:
            if target in passage_map:
                passage_map[target]["parents"].append(p["title"])

    # Assign each passage to a horizontal swimlane (Scene/Day)
    scenes = {}
    for p in passages:
        g = get_scene_group(p["title"], p["tags"])
        p["scene"] = g
        scenes.setdefault(g, []).append(p)

    current_base_y = START_Y

    # Layout each Scene/Day independently so branches never cross between days
    for g in sorted(scenes.keys()):
        group_passages = scenes[g]
        group_titles = {p["title"] for p in group_passages}

        # Find entry nodes for this scene (nodes with no parents inside the same scene)
        roots = [
            p["title"] for p in group_passages
            if not any(par in group_titles for par in p["parents"])
        ]
        if not roots:
            roots = [group_passages[0]["title"]]

        # Assign local column depth (X) within this scene using longest-path BFS
        depths = {r: 0 for r in roots}
        queue = deque(roots)
        while queue:
            curr = queue.popleft()
            d = depths[curr]
            for nxt in passage_map[curr]["links"]:
                if nxt in group_titles:
                    # Push merge nodes forward so arrows always point right
                    if nxt not in depths or depths[nxt] < d + 1:
                        depths[nxt] = d + 1
                        queue.append(nxt)

        # Group by column X
        columns = {}
        for p in group_passages:
            d = depths.get(p["title"], 0)
            columns.setdefault(d, []).append(p)

        # Assign initial row indices
        row_pos = {}
        for d in sorted(columns.keys()):
            for idx, p in enumerate(columns[d]):
                row_pos[p["title"]] = float(idx)

        # Barycenter heuristic (4 passes) to untangle crossing arrows
        for _ in range(4):
            # Forward pass: align children with their parents' vertical position
            for d in sorted(columns.keys())[1:]:
                for p in columns[d]:
                    in_parents = [par for par in p["parents"] if par in row_pos]
                    if in_parents:
                        row_pos[p["title"]] = sum(row_pos[par] for par in in_parents) / len(in_parents)
                columns[d].sort(key=lambda x: row_pos[x["title"]])
                for idx, p in enumerate(columns[d]):
                    row_pos[p["title"]] = float(idx)

            # Backward pass: align parents with their children's vertical position
            for d in reversed(sorted(columns.keys())[:-1]):
                for p in columns[d]:
                    out_children = [ch for ch in p["links"] if ch in row_pos]
                    if out_children:
                        row_pos[p["title"]] = sum(row_pos[ch] for ch in out_children) / len(out_children)
                columns[d].sort(key=lambda x: row_pos[x["title"]])
                for idx, p in enumerate(columns[d]):
                    row_pos[p["title"]] = float(idx)

        # Calculate final pixel coordinates for this swimlane
        max_rows_in_scene = max(len(col) for col in columns.values())
        scene_height = max_rows_in_scene * Y_SPACING

        for d, col_passages in columns.items():
            # Center smaller columns vertically inside the swimlane
            col_height = (len(col_passages) - 1) * Y_SPACING
            center_offset = (scene_height - col_height) / 2

            for idx, p in enumerate(col_passages):
                p["x"] = int(START_X + (d * X_SPACING))
                p["y"] = int(current_base_y + center_offset + (idx * Y_SPACING))

        # Advance Y down for the next Day/Scene swimlane
        current_base_y += scene_height + SCENE_GAP


def write_twee(filepath, meta_blocks, passages):
    out_lines = []

    for title, tags, body in meta_blocks:
        header = f":: {title}" + (f" {tags}" if tags else "")
        out_lines.append(header)
        out_lines.append(body)
        out_lines.append("")

    for p in passages:
        pos_json = json.dumps({"position": f"{p['x']},{p['y']}", "size": "100,100"})
        header = f":: {p['title']}"
        if p["tags"]:
            header += f" {p['tags']}"
        header += f" {pos_json}"

        out_lines.append(header)
        out_lines.append(p["body"])
        out_lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))


if __name__ == "__main__":
    script_dir = Path(__file__).resolve().parent
    twee_files = [
        f for f in script_dir.glob("*.twee")
        if not f.stem.endswith("_Organized")
    ]

    if not twee_files:
        print("No .twee files found in this folder.")
    else:
        for input_path in twee_files:
            output_path = input_path.with_name(f"{input_path.stem}_Organized.twee")
            meta, story_passages = parse_twee(input_path)
            calculate_clean_layout(story_passages)
            write_twee(output_path, meta, story_passages)
            print(f"Organized {len(story_passages)} passages: '{input_path.name}' -> '{output_path.name}'")
