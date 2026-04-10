#!/usr/bin/env python3
"""Generate quest content for all Berrien County towns."""
import json
import os
import random

QUEST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quests")
REGION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "region_maps")


def find_town_tile(seg_name):
    """Find the town tile position in a segment."""
    path = os.path.join(REGION_DIR, f"{seg_name}.json")
    with open(path) as f:
        grid = json.load(f)
    for y in range(len(grid)):
        for x in range(len(grid[0])):
            if grid[y][x] == 15:
                return x, y, grid
    return None, None, grid


def find_entrance_pos(grid, tx, ty, seed):
    """Find a passable tile 4-7 tiles from town for dungeon entrance."""
    rng = random.Random(seed)
    for _ in range(100):
        dx = rng.randint(-6, 6)
        dy = rng.randint(-6, 6)
        dist = abs(dx) + abs(dy)
        if 4 <= dist <= 7:
            nx, ny = tx + dx, ty + dy
            if 0 <= nx < len(grid[0]) and 0 <= ny < len(grid):
                if grid[ny][nx] in (10, 11):
                    return nx, ny
    return tx + 4, ty + 3


def write_quest(quest_id, name, desc, segment, lore,
                npc_id, npc_name, npc_sym, npc_art, dialog_start, dialog_complete,
                floor_key, floor_name, floor_size, floor_theme, floor_diff, floor_desc, monsters,
                boss_name, boss_hp, boss_atk, boss_def, boss_xp, boss_gold, boss_art, boss_dialog,
                reward_gold, blessing):
    tx, ty, grid = find_town_tile(segment)
    if tx is None:
        print(f"  WARNING: No town in {segment} for {quest_id}")
        return
    npc_x, npc_y = tx - 1, ty
    ent_x, ent_y = find_entrance_pos(grid, tx, ty, hash(quest_id))

    quest = {
        "id": quest_id,
        "name": name,
        "description": desc,
        "lore": lore,
        "map_mods": [],
        "entrances": [{
            "floor": segment,
            "x": ent_x, "y": ent_y,
            "visible_if": "quest_stage >= started",
            "label": floor_name,
            "target_floor": floor_key
        }],
        "quest_floors": {
            floor_key: {
                "name": floor_name, "size": floor_size,
                "theme": floor_theme, "difficulty": floor_diff,
                "description": floor_desc, "monsters": monsters
            }
        },
        "npcs": {
            npc_id: {
                "name": npc_name, "description": f"Quest giver in {name}.",
                "floor": segment, "x": npc_x, "y": npc_y,
                "location": "town", "symbol": npc_sym,
                "art": npc_art,
                "dialog_start": dialog_start,
                "dialog_complete": dialog_complete
            }
        },
        "boss": {
            "name": boss_name, "description": f"Boss of {floor_name}.",
            "floor": floor_key,
            "x": floor_size // 2, "y": floor_size // 2,
            "hp": boss_hp, "atk": boss_atk, "def": boss_def,
            "xp": boss_xp, "gold": boss_gold,
            "art": boss_art, "defeat_flag": "boss_defeated",
            "dialog": boss_dialog
        },
        "rewards": {"gold": reward_gold, "blessing": blessing},
        "stages": [
            {"id": "started", "description": f"Talk to {npc_name}."},
            {"id": "boss_defeated", "description": f"Defeat {boss_name}."},
            {"id": "complete", "description": f"Return to {npc_name}."}
        ]
    }

    path = os.path.join(QUEST_DIR, f"{quest_id}.json")
    with open(path, "w") as f:
        json.dump(quest, f, indent=2)
    print(f"  {quest_id}: {name} (NPC@{npc_x},{npc_y} ent@{ent_x},{ent_y})")


def main():
    print("Generating quests for Berrien County towns...\n")

    # ── Buchanan ──
    write_quest(
        "quest_buchanan", "The EternalVoice Factory",
        "The old EternaVox speaker factory is broadcasting again. On frequencies that shouldn't exist.", "seg_3_0",
        ["Buchanan was a factory town. EternaVox Acoustics made speakers here",
         "from 1927 to 2006. Best sound equipment in the world.",
         "The factory's been empty for twenty years.",
         "But last week, the test lab started transmitting.",
         "Not radio. Not audio. Something else entirely.",
         "The signal makes your fillings hum."],
        "granny", "Granny", "G",
        ["  .---.", " ( o.o )", "  \\---/", " [GRAN]", " [NY! ]"],
        ["Granny: I worked the EternaVox line for forty years.",
         "Granny: Best speakers ever made. Right here in Buchanan.",
         "Granny: The factory's been dark since '06.",
         "Granny: But the anechoic chamber is active again.",
         "Granny: Something is broadcasting from the sub-basement.",
         "Granny: Frequencies that shouldn't be possible.", "",
         "  [Quest accepted: The EternalVoice Factory]"],
        ["Granny: The signal stopped. Good.",
         "Granny: Some frequencies aren't meant to be heard.",
         "Granny: Here — my old prototype mic. Still works perfect.", "  [Quest complete!]"],
        "eternavox_basement", "EternaVox Sub-Basement", 24, "gray", 3,
        "Soundproofed corridors. Dead speakers line the walls. Something is humming.",
        [{"name": "Feedback Loop", "hp": 14, "atk": 5, "def": 2, "xp": 12, "gold": 6,
          "art": ["  ))))", " ((((", "  ))))", " (((("]},
         {"name": "Blown Woofer", "hp": 25, "atk": 8, "def": 6, "xp": 20, "gold": 12,
          "art": ["  .===.", " / o o \\", " |=====|", "  \\===/"]},
         {"name": "Phantom Signal", "hp": 18, "atk": 6, "def": 3, "xp": 15, "gold": 8,
          "art": ["  ~|~|~", " ~|~|~|~", "  ~|~|~"]}],
        "The Resonance", 80, 16, 6, 120, 100,
        ["  .========.  ", " | )))(((  | ", " | (SPEAK) | ", " | )))(((  | ",
         " |  CONE   | ", "  '========'  ", "   |||||||    ", "  ~~~~~~~~~   "],
        ["Every speaker in the factory fires at once.",
         "The sound coalesces into a shape. A voice.",
         "Resonance: I AM THE PERFECT FREQUENCY.",
         "Resonance: I WAS BORN IN THE ANECHOIC CHAMBER.",
         "Resonance: AND I WILL BE HEARD."],
        600, {"name": "Perfect Pitch", "atk_bonus": 3, "def_bonus": 2})

    # ── Niles ──
    write_quest(
        "quest_niles", "The Four Flags Problem",
        "The old fort is haunted by four spectral flags.", "seg_5_0",
        ["Niles: the City of Four Flags. French, British, Spanish, American.",
         "The old fort was never fully excavated.",
         "A construction crew broke into a chamber. They saw flags moving with no wind."],
        "foreman", "Diane", "D",
        ["  .---.", " ( -.- )", "  \\   /", " [HARD]", " [HAT!]"],
        ["Diane: I don't believe in ghosts.", "Diane: But my crew does.",
         "Diane: Four flags hanging in mid-air. No poles, no wind.",
         "Diane: Go down there and deal with it.", "",
         "  [Quest accepted: The Four Flags Problem]"],
        ["Diane: The flags are gone? My crew can get back to work?", "  [Quest complete!]"],
        "niles_fort", "Fort St. Joseph", 20, "cyan", 4,
        "Stone walls from four different eras.",
        [{"name": "French Phantom", "hp": 20, "atk": 8, "def": 3, "xp": 18, "gold": 10,
          "art": ["  ~ooo~", " ~ | | ~", "  \\|_|/"]},
         {"name": "British Shade", "hp": 22, "atk": 9, "def": 4, "xp": 20, "gold": 12,
          "art": ["  .-==-.", " |  ++ |", "  '===' "]},
         {"name": "Spectral Soldier", "hp": 28, "atk": 10, "def": 5, "xp": 25, "gold": 15,
          "art": ["  .--.", " (o  o)", "  |==|", " /|  |\\"]}],
        "The Flag Bearer", 100, 20, 7, 160, 120,
        [" |F| |B| |S| |A|", "  .---+---+---.  ", " (  O       O  ) ",
         "  |   ====   |   ", "    ~~~~~~~~     "],
        ["Four flags snap to attention.", "Flag Bearer: I HAVE HELD THESE FLAGS FOR CENTURIES.",
         "Flag Bearer: NONE SHALL PASS."],
        800, {"name": "Four Flags Valor", "atk_bonus": 3, "def_bonus": 3})

    # ── Berrien Springs ──
    write_quest(
        "quest_berrien_springs", "The River's Memory",
        "The St. Joseph River is flooding in one spot, and the water remembers things.", "seg_3_3",
        ["Berrien Springs is a quiet college town on the river.",
         "Something upstream is feeding the river memories.",
         "People see faces in the water. Hear voices at night."],
        "professor", "Professor Mills", "P",
        ["  .---.", " ( o o )", "  | = |", " [LABS]", "  +--+"],
        ["Prof. Mills: The water table is doing something impossible.",
         "Prof. Mills: There's a sinkhole feeding into a cave system.",
         "Prof. Mills: Can you investigate?", "",
         "  [Quest accepted: The River's Memory]"],
        ["Prof. Mills: The resonance stopped! The river's calming.", "  [Quest complete!]"],
        "river_caves", "River Caves", 22, "blue", 4,
        "Wet limestone caves. The walls echo with centuries of whispers.",
        [{"name": "Memory Echo", "hp": 18, "atk": 7, "def": 3, "xp": 16, "gold": 9,
          "art": ["  ~~~", " (. .)", "  ~~~"]},
         {"name": "River Shade", "hp": 24, "atk": 9, "def": 4, "xp": 22, "gold": 14,
          "art": ["  ~.~.~", " / o o \\", "  ~~~~~"]},
         {"name": "Calcified Crayfish", "hp": 30, "atk": 6, "def": 8, "xp": 20, "gold": 10,
          "art": ["  V   V", " /=====\\", "  \\===/"]}],
        "The Drowned Choir", 110, 18, 6, 150, 110,
        [" ~ o  o  o ~", " ~  )  )  ) ~", "  ~~~~~~~~  ", " ~MEMORIES~ "],
        ["Faces surface in the pool.", "Choir: WE REMEMBER THE FLOODS.",
         "Choir: JOIN US. ADD YOUR VOICE."],
        700, {"name": "River's Clarity", "hp_bonus": 30, "mp_bonus": 15})

    # ── Eau Claire ──
    write_quest(
        "quest_eau_claire", "The Witch of Pipestone Creek",
        "Livestock are going missing near Pipestone Creek.", "seg_4_3",
        ["Eau Claire is farm country. Orchards and cornfields.",
         "Farmers have been losing chickens, goats, even a cow.",
         "Grandma Hess says it's the Pipestone Witch."],
        "farmer", "Grandma Hess", "H",
        ["  .---.", " (o  o)", "  \\--/", " [====]", " /|GUN|\\"],
        ["Grandma Hess: I told 'em for years.", "Something lives in that ravine.",
         "Grandma Hess: Go down to the creek. Follow it upstream.",
         "Grandma Hess: *hands you a salt-packed shotgun shell*", "",
         "  [Quest accepted: The Witch of Pipestone Creek]"],
        ["Grandma Hess: *nods slowly*", "Grandma Hess: I knew it. Fifty years I knew it.",
         "  [Quest complete!]"],
        "pipestone_ravine", "Pipestone Ravine", 20, "green", 3,
        "A deep, narrow ravine choked with thorns. Bones hang from branches.",
        [{"name": "Bone Crow", "hp": 12, "atk": 6, "def": 2, "xp": 10, "gold": 5,
          "art": ["  v   v", " /=^=\\", "  ==="]},
         {"name": "Thorn Golem", "hp": 28, "atk": 8, "def": 5, "xp": 22, "gold": 12,
          "art": ["  /|\\", " /|||\\", " |   |"]},
         {"name": "Creek Hag", "hp": 20, "atk": 10, "def": 3, "xp": 18, "gold": 10,
          "art": ["  .^.", " (o o)", " /~~~\\"]}],
        "The Pipestone Witch", 90, 18, 5, 130, 90,
        ["    .^^^^^.    ", "   / o   o \\   ", "  |  ~~~~   |  ",
         "  | /BONES\\ |  ", "   \\|     |/   "],
        ["Bones rattle. The thorns part.", "Witch: HUNGRY. ALWAYS HUNGRY.",
         "Witch: YOU'LL DO NICELY."],
        600, {"name": "Hess Family Recipe", "hp_bonus": 25, "atk_bonus": 2})

    # ── St. Joseph ──
    write_quest(
        "quest_st_joseph", "The Last Kit",
        "The old ApexKit Electronics warehouse is building something by itself.", "seg_1_6",
        ["St. Joseph was the home of ApexKit Electronics.",
         "Build-it-yourself radios, TVs, computers — shipped worldwide.",
         "The warehouse closed in '92. Everything was auctioned off.",
         "But the soldering stations are hot again.",
         "Something is assembling a kit that was never in the catalog.",
         "The schematics on the workbench don't match anything human."],
        "engineer", "Marge", "M",
        ["  .===.", " ( o.o )", "  |   |", " [APEX]", " [KIT!]"],
        ["Marge: I was a tech writer at ApexKit for fifteen years.",
         "Marge: Wrote the manuals. Every kit, every revision.",
         "Marge: Someone's in the warehouse. Soldering, wiring.",
         "Marge: I looked through the window — the benches are lit up.",
         "Marge: And the thing they're building... it's not in any manual I wrote.",
         "Marge: The schematics use symbols I've never seen.", "",
         "  [Quest accepted: The Last Kit]"],
        ["Marge: It stopped? The warehouse is dark?",
         "Marge: Kit #999. The one that was never shipped.",
         "Marge: Maybe some things shouldn't be assembled.",
         "Marge: Here — a prototype multimeter. Still works.", "  [Quest complete!]"],
        "apexkit_warehouse", "ApexKit Warehouse", 20, "cyan", 5,
        "Rows of soldering stations glow in the dark. Half-built kits twitch on the benches.",
        [{"name": "Solder Sprite", "hp": 16, "atk": 9, "def": 2, "xp": 18, "gold": 10,
          "art": ["  .o.", " /~~~\\", " |zap|", "  '-'"]},
         {"name": "Rogue Oscillator", "hp": 22, "atk": 8, "def": 4, "xp": 20, "gold": 12,
          "art": ["  /\\/\\", " /\\/\\/\\", " \\/\\/\\/", "  \\/\\/"]},
         {"name": "Kit Golem", "hp": 35, "atk": 7, "def": 7, "xp": 25, "gold": 15,
          "art": ["  [===]", " [RADIO]", " [=====]", "  [===]"]}],
        "Kit #999", 120, 22, 8, 180, 130,
        ["  .=========.  ", " | .--. .--. | ", " | |##| |##| | ", " | '--' '--' | ",
         " |  KIT #999 | ", " |  ~~~~~~~~ | ", "  '========='  ", "   ||  ||  ||   "],
        ["The final kit assembles itself. Vacuum tubes glow.",
         "It hums. It crackles. It speaks.",
         "Kit #999: I AM THE SCHEMATIC THAT WAS NEVER PUBLISHED.",
         "Kit #999: THE FREQUENCY BEYOND THE DIAL.",
         "Kit #999: ASSEMBLE ME AND I WILL SHOW YOU EVERYTHING."],
        900, {"name": "Kit Builder's Precision", "atk_bonus": 4, "spd_bonus": 3})

    # ── Benton Harbor ──
    write_quest(
        "quest_benton_harbor", "The Spin Cycle",
        "The old MaelstromCo appliance plant is running again. Every machine, all at once.", "seg_1_6",
        ["Benton Harbor was the appliance capital of the world.",
         "MaelstromCo built washers, dryers, dishwashers — you name it.",
         "The plant closed ten years ago. Thousands of jobs gone.",
         "Last week the power grid spiked. The old plant drew 2 megawatts.",
         "Nobody's inside. But every machine on the floor is running.",
         "The spin cycle never stops."],
        "larry", "Larry", "L",
        ["  .---.", " ( o.o )", "  \\   /", " [ENG ]--.", "  |  |", "  +--+"],
        ["Larry: I was a line engineer at MaelstromCo for twenty-two years.",
         "Larry: *waves his one hand*",
         "Larry: Don't ask about the other one. Dynamite fishing accident.",
         "Larry: Anyway — the plant's been dead since they moved to Mexico.",
         "Larry: But I drove past last night. Every light was on.",
         "Larry: Machines running. Nobody at the controls.",
         "Larry: Something in the sub-basement. The old prototype lab.", "",
         "  [Quest accepted: The Spin Cycle]"],
        ["Larry: Plant's dark again. Power company's relieved.",
         "Larry: *scratches chin with his one hand*",
         "Larry: Twenty-two years on that line and I never saw anything like that.",
         "Larry: Here — my old foreman's badge. Might come in handy.", "  [Quest complete!]"],
        "maelstromco_plant", "MaelstromCo Prototype Lab", 22, "white", 4,
        "Assembly lines run unmanned. Washers spin. Dryers tumble. The noise is deafening.",
        [{"name": "Rogue Washer", "hp": 28, "atk": 8, "def": 6, "xp": 20, "gold": 12,
          "art": ["  .===.", " |     |", " | @@@ |", " |     |", "  '==='"]},
         {"name": "Lint Phantom", "hp": 16, "atk": 7, "def": 2, "xp": 14, "gold": 8,
          "art": ["  ~~~", " ~~~~~", " ~~~~~", "  ~~~"]},
         {"name": "Assembly Arm", "hp": 24, "atk": 10, "def": 4, "xp": 22, "gold": 14,
          "art": ["  |", "  |--.", " /|  |", "  |  o"]}],
        "The Prototype", 100, 19, 6, 150, 110,
        ["  .==========.  ", " |  MAELSTROM | ", " | |  @@@@  | | ", " | | @    @ | | ",
         " | |  @@@@  | | ", " |  CYCLE:99 | ", "  '=========='  ", "  ~SPIN~SPIN~   "],
        ["A washer the size of a car roars to life.",
         "Its drum spins impossibly fast. The room shakes.",
         "Prototype: PERMANENT PRESS.",
         "Prototype: HEAVY DUTY.",
         "Prototype: THE CYCLE NEVER ENDS."],
        750, {"name": "Iron Will", "def_bonus": 4, "hp_bonus": 20})

    # ── Bridgman ──
    write_quest(
        "quest_bridgman", "The Dune Walker",
        "Something is moving through the dunes at Warren Dunes.", "seg_0_3",
        ["Warren Dunes State Park draws a million visitors a year.",
         "The rangers found massive tracks. Two legs. Eight feet tall.",
         "The tracks lead into the back dunes."],
        "ranger", "Ranger Okafor", "R",
        ["  .===.", " ( o.o )", "  |   |", " [RANG]", " [ER! ]"],
        ["Ranger Okafor: These tracks don't match anything in my guide.",
         "Ranger Okafor: The tracks lead into the back dunes.",
         "Ranger Okafor: I need someone to follow the trail.", "",
         "  [Quest accepted: The Dune Walker]"],
        ["Ranger Okafor: A sand elemental? Not in my field guide.", "  [Quest complete!]"],
        "back_dunes", "The Back Dunes", 20, "yellow", 3,
        "Shifting sand dunes under open sky. The wind never stops.",
        [{"name": "Sand Viper", "hp": 14, "atk": 7, "def": 2, "xp": 12, "gold": 6,
          "art": ["  ~~~~", " /o  o\\", " ~~~~~~"]},
         {"name": "Dune Beetle", "hp": 20, "atk": 5, "def": 6, "xp": 14, "gold": 8,
          "art": ["  .==.", " /o  o\\", "  \\==/"]},
         {"name": "Wind Sprite", "hp": 10, "atk": 9, "def": 1, "xp": 16, "gold": 10,
          "art": ["  ~ ~", " ( . )", "  ~~~"]}],
        "The Dune Walker", 95, 17, 7, 140, 100,
        ["     .---.     ", "    / O O \\    ", "   |  ===  |   ",
         "   | ::::: |   ", "    \\::::::/    ", "  ~~~~===~~~~  "],
        ["The dune rises into a towering figure.",
         "Dune Walker: I WAS HERE BEFORE THE TREES.", "Dune Walker: YOU ARE A BRIEF INCONVENIENCE."],
        600, {"name": "Dune Strider", "spd_bonus": 5})

    # ── Baroda ──
    write_quest(
        "quest_baroda", "The Vineyard Blight",
        "The vineyards around Baroda are dying from something in the soil.", "seg_1_3",
        ["Baroda is wine country. Rolling hills, vineyards everywhere.",
         "The vines are turning black. Not rot, not frost.",
         "Something in the soil moves at night."],
        "vintner", "Rosa", "R",
        ["  .---.", " ( o.o )", "  \\ ~ /", " [WINE]", "  +--+"],
        ["Rosa: *holds up a blackened vine*",
         "Rosa: The blight is spreading from the old root cellar.",
         "Rosa: Something's down there. I can hear it.", "",
         "  [Quest accepted: The Vineyard Blight]"],
        ["Rosa: The vines are greening up already!", "  [Quest complete!]"],
        "root_cellar", "The Root Cellar", 18, "green", 3,
        "A wine cellar overgrown with twisted, blackened roots.",
        [{"name": "Blight Root", "hp": 16, "atk": 6, "def": 3, "xp": 12, "gold": 7,
          "art": ["  \\|/", "  -o-", "  /|\\"]},
         {"name": "Fungal Lurker", "hp": 22, "atk": 7, "def": 4, "xp": 16, "gold": 9,
          "art": ["  .o.", " /ooo\\", "  \\o/"]},
         {"name": "Barrel Mimic", "hp": 30, "atk": 9, "def": 5, "xp": 22, "gold": 15,
          "art": ["  .==.", " |WINE|", "  '=='"]}],
        "The Root King", 85, 15, 6, 120, 90,
        ["   \\\\|//   ", "   /oOo\\   ", "  /ooooo\\  ",
         " |oo===oo| ", "   \\|||/   "],
        ["The roots part to reveal a pulsing fungal mass.",
         "Root King: THE VINES ARE MINE NOW.", "Root King: AND I AM STILL THIRSTY."],
        550, {"name": "Vintner's Vigor", "hp_bonus": 20, "atk_bonus": 2})

    # ── Stevensville ──
    write_quest(
        "quest_stevensville", "The Lincoln Highway Ghost",
        "A phantom car on the old Red Arrow Highway is causing real accidents.", "seg_0_4",
        ["The Red Arrow Highway was the main road before I-94.",
         "A phantom car — headlights, engine, but no car —",
         "has been running the highway at midnight."],
        "mechanic", "Dave", "D",
        ["  .---.", " ( o.o )", "  \\   /", " [MECH]", "  +--+"],
        ["Dave: Saw it again last night. Headlights, engine, the whole deal.",
         "Dave: It's coming from the old Lincoln Highway tunnel.",
         "Dave: Under the railroad. Been sealed since the '60s.", "",
         "  [Quest accepted: The Lincoln Highway Ghost]"],
        ["Dave: No phantom car last night. First quiet night in weeks.", "  [Quest complete!]"],
        "highway_tunnel", "Lincoln Highway Tunnel", 18, "gray", 2,
        "A crumbling concrete tunnel under the railroad.",
        [{"name": "Road Ghost", "hp": 12, "atk": 5, "def": 2, "xp": 10, "gold": 5,
          "art": ["  o o", " /~~~\\", "  ~~~"]},
         {"name": "Hubcap Mimic", "hp": 18, "atk": 6, "def": 4, "xp": 14, "gold": 8,
          "art": ["  .--.", " / () \\", "  '--'"]},
         {"name": "Exhaust Wraith", "hp": 15, "atk": 7, "def": 2, "xp": 12, "gold": 6,
          "art": ["  ~~~", " ~~~~", "  ~~~"]}],
        "The Phantom Driver", 70, 14, 5, 100, 80,
        ["  O====O====O  ", " /    ____   \\ ", "| O  |    | O |",
         "   (O)  (O)    "],
        ["Headlights blaze. A 1932 Ford materializes.",
         "Driver: ALMOST HOME. ALMOST THERE.", "Driver: WHY WON'T THE ROAD END?"],
        500, {"name": "Road Runner", "spd_bonus": 4})

    # ── Coloma ──
    write_quest(
        "quest_coloma", "The Orchard Rot",
        "Apple trees in Coloma are bearing rotten, writhing fruit out of season.", "seg_1_4",
        ["Coloma is apple country. Orchards as far as you can see.",
         "The trees are fruiting in winter. Black apples.",
         "Some of them move. Some of them have teeth."],
        "orchardist", "Big Jim", "J",
        ["  .===.", " ( o o )", "  |===|", " [APPL]", " [ES! ]"],
        ["Big Jim: I grow Honeycrisp. Best in the county.",
         "Big Jim: *holds up a pulsing black apple*",
         "Big Jim: Something in the ground woke up.", "",
         "  [Quest accepted: The Orchard Rot]"],
        ["Big Jim: Trees are budding normal again!", "  [Quest complete!]"],
        "root_network", "The Root Network", 20, "green", 3,
        "Beneath the orchard, roots form a labyrinth. Smells of fermenting apples.",
        [{"name": "Rot Apple", "hp": 10, "atk": 5, "def": 2, "xp": 8, "gold": 4,
          "art": ["  .@.", " ( ~ )", "  '-'"]},
         {"name": "Root Tendril", "hp": 20, "atk": 7, "def": 3, "xp": 14, "gold": 8,
          "art": ["  \\|/", "  |||", "  /|\\"]},
         {"name": "Orchard Wight", "hp": 25, "atk": 8, "def": 4, "xp": 18, "gold": 10,
          "art": ["  .--.", " (o  o)", " |~~~~|"]}],
        "The Mother Tree", 90, 16, 7, 130, 95,
        ["    \\|||/    ", "   //||\\\\   ", " |  (OO)  | ",
         "  \\ |||| /  ", "    ||||    "],
        ["A massive trunk rises from the soil. Eyes open in the bark.",
         "Mother Tree: MY CHILDREN. YOU HURT MY CHILDREN.",
         "Mother Tree: YOU WILL FEED MY ROOTS."],
        600, {"name": "Orchard's Bounty", "hp_bonus": 30, "def_bonus": 2})

    # ── Hagar Shores ──
    write_quest(
        "quest_hagar_shores", "The Shipwreck Choir",
        "Singing from the lake. From a ship that sank in 1913.", "seg_0_5",
        ["Hagar Shores sits on the bluffs above Lake Michigan.",
         "The Great Storm of 1913 sank the SS Meridian offshore.",
         "On still nights, you can hear singing from the water."],
        "diver", "Chen", "C",
        ["  .===.", " ( o.o )", "  |O2 |", " [DIVE]", "  +--+"],
        ["Chen: I found the Meridian. I wish I hadn't.",
         "Chen: The hull is intact. That shouldn't be possible.",
         "Chen: The singing is coming from inside the ship.", "",
         "  [Quest accepted: The Shipwreck Choir]"],
        ["Chen: The singing stopped. Rest in peace, Meridian.", "  [Quest complete!]"],
        "ss_meridian", "SS Meridian Wreck", 18, "blue", 5,
        "Inside a sunken freighter. Water drips. Someone is singing.",
        [{"name": "Drowned Sailor", "hp": 24, "atk": 9, "def": 4, "xp": 22, "gold": 12,
          "art": ["  .--.", " (x  x)", "  |  |"]},
         {"name": "Barnacle Golem", "hp": 35, "atk": 7, "def": 8, "xp": 20, "gold": 10,
          "art": ["  [ooo]", " [ooooo]", "  [ooo]"]},
         {"name": "Hull Wraith", "hp": 28, "atk": 11, "def": 4, "xp": 25, "gold": 15,
          "art": ["  ~~~~", " /    \\", "  ~~~~"]}],
        "Captain Mercer", 115, 20, 7, 170, 120,
        ["    .-=-.      ", "   / O O \\     ", "  |[WHEEL]|    ",
         "   \\ === /     ", "  ~~|   |~~    "],
        ["A figure solidifies behind the ship's wheel.",
         "Mercer: I WILL NOT ABANDON MY SHIP.",
         "Mercer: A HUNDRED YEARS AT THE WHEEL."],
        850, {"name": "Mariner's Resolve", "def_bonus": 4, "hp_bonus": 25})

    # ── Benton East ──
    write_quest(
        "quest_benton_east", "The Fruit Market Phantom",
        "The old fruit market warehouse is alive at night.", "seg_2_6",
        ["Benton Harbor's fruit market was the largest in the world.",
         "The old warehouse is mostly abandoned.",
         "But the scales still work. Something is keeping inventory."],
        "watchman", "Earl", "E",
        ["  .---.", " ( o.o )", "  |   |", " [NITE]", " [WTCH]"],
        ["Earl: Every night at 3 AM. The conveyor starts.",
         "Earl: Exactly 1,847 bushels. Same number every night.",
         "Earl: The basement door won't stay locked.", "",
         "  [Quest accepted: The Fruit Market Phantom]"],
        ["Earl: Quiet night. First one in months.", "  [Quest complete!]"],
        "fruit_warehouse", "Warehouse Basement", 20, "yellow", 4,
        "Endless rows of ghostly crates. Scales tip on their own.",
        [{"name": "Crate Golem", "hp": 25, "atk": 7, "def": 6, "xp": 18, "gold": 10,
          "art": ["  [===]", " [=   =]", "  [===]"]},
         {"name": "Scale Phantom", "hp": 18, "atk": 9, "def": 3, "xp": 16, "gold": 8,
          "art": ["   |", " __|__", "  \\_/"]},
         {"name": "Rot Sprite", "hp": 14, "atk": 8, "def": 2, "xp": 14, "gold": 12,
          "art": ["  .@.", " (~.~)", "  ~~~"]}],
        "The Accountant", 95, 17, 6, 140, 100,
        ["    .---.      ", "   / o o \\     ", "  | |LED| |    ",
         "  | |GER| |    ", "   1,847       "],
        ["A figure sits at a desk, pen scratching.",
         "Accountant: 1,847 BUSHELS. MISSING SINCE 1929.",
         "Accountant: YOU ARE NOT IN MY LEDGER."],
        700, {"name": "Balanced Books", "mp_bonus": 20, "atk_bonus": 2})

    # ── Buchanan North ──
    write_quest(
        "quest_buchanan_north", "The Pumpkin King",
        "Something is growing in the pumpkin fields. Something big.", "seg_3_1",
        ["The farms north of Buchanan grow the best pumpkins.",
         "One of them is the size of a tractor shed.",
         "It has a face now. And it's still growing."],
        "farmer_pete", "Pete", "P",
        ["  .---.", " ( o_o )", "  \\   /", " [FARM]", "  +--+"],
        ["Pete: It's the size of my barn. And it has a FACE.",
         "Pete: Last night I swear it looked at me.",
         "Pete: The roots go deep. Something's under my field.", "",
         "  [Quest accepted: The Pumpkin King]"],
        ["Pete: It's shrinking! Just a regular giant pumpkin now.", "  [Quest complete!]"],
        "pumpkin_roots", "The Root System", 18, "yellow", 2,
        "Massive pumpkin roots form the walls. Everything smells like autumn.",
        [{"name": "Vine Creep", "hp": 12, "atk": 5, "def": 2, "xp": 10, "gold": 5,
          "art": ["  \\|/", "  -O-", "  /|\\"]},
         {"name": "Seed Spitter", "hp": 16, "atk": 7, "def": 2, "xp": 12, "gold": 7,
          "art": ["  .@.", " (ooo)", "  '-'"]},
         {"name": "Gourd Guard", "hp": 22, "atk": 6, "def": 5, "xp": 16, "gold": 10,
          "art": ["  .--.", " /o  o\\", "  \\--/"]}],
        "The Pumpkin King", 75, 14, 5, 100, 80,
        ["    .====.     ", "  /  o  o  \\   ", " |  \\~~~~/ |   ",
         "  \\  ====  /   ", "   |||||||     "],
        ["An enormous pumpkin rises. Its carved face glows.",
         "Pumpkin King: GROOOOOOW.", "Pumpkin King: YOU ARE SMALL. I WILL OUTGROW YOU."],
        450, {"name": "Harvest Bounty", "hp_bonus": 20, "def_bonus": 2})

    # ── Niles North ──
    write_quest(
        "quest_niles_north", "The Brandywine Falls",
        "The waterfall has stopped falling. The water hangs frozen in mid-air.", "seg_5_1",
        ["Brandywine Creek has a beautiful waterfall north of Niles.",
         "Last Thursday, the water stopped. Not froze. Stopped.",
         "Hanging in mid-air. Warm. Wet. But it won't fall."],
        "hiker", "Jamie", "J",
        ["  .---.", " ( O.O )", "  \\ o /", " [HIKE]", "  /  \\"],
        ["Jamie: The waterfall just... stopped.",
         "Jamie: There's a cave behind the falls.",
         "Jamie: I went in ten feet. Then I heard something.", "",
         "  [Quest accepted: The Brandywine Falls]"],
        ["Jamie: It's falling again! Listen!", "  [Quest complete!]"],
        "falls_cave", "Behind the Falls", 16, "blue", 3,
        "A cave of impossible stillness. Water hangs like curtains.",
        [{"name": "Time Eddy", "hp": 16, "atk": 8, "def": 2, "xp": 14, "gold": 8,
          "art": ["  @@@", " @   @", "  @@@"]},
         {"name": "Still Water", "hp": 20, "atk": 6, "def": 5, "xp": 16, "gold": 10,
          "art": ["  ===", " | . |", "  ==="]},
         {"name": "Creek Sprite", "hp": 12, "atk": 9, "def": 2, "xp": 12, "gold": 6,
          "art": ["  ~.~", " (~.~)", "  ~.~"]}],
        "The Chronolith", 85, 16, 6, 130, 95,
        ["      *        ", "     /|\\       ", "   /  |  \\     ",
         "  / TICK  \\    ", " /  TOCK   \\   "],
        ["A crystal hums in the deepest chamber.",
         "Chronolith: TIME IS A RIVER.", "Chronolith: I HAVE DAMMED IT."],
        600, {"name": "Timeless Flow", "spd_bonus": 3, "mp_bonus": 15})

    # ── Coloma South ──
    write_quest(
        "quest_coloma_south", "The Honey War",
        "Two rival apiaries are at war. The bees have taken sides.", "seg_2_3",
        ["The Patterson and Kowalski families have kept bees for generations.",
         "Now the bees themselves have joined the feud.",
         "Something in the hives has made them organized."],
        "beekeeper", "Agnes", "A",
        ["  .===.", " (o  o )", "  |BEE|", " [KEEP]", "  +--+"],
        ["Agnes: Both families are blaming each other.",
         "Agnes: Something's controlling the bees. From underground.",
         "Agnes: There's an old root cellar between both properties.", "",
         "  [Quest accepted: The Honey War]"],
        ["Agnes: The swarms calmed down overnight!", "  [Quest complete!]"],
        "queen_hive", "The Queen Hive", 18, "yellow", 3,
        "Hexagonal chambers of wax and honey. The buzzing is deafening.",
        [{"name": "Soldier Bee", "hp": 14, "atk": 6, "def": 3, "xp": 12, "gold": 6,
          "art": ["  /\\", " /oo\\", "  \\/"]},
         {"name": "Honey Slime", "hp": 20, "atk": 5, "def": 4, "xp": 14, "gold": 10,
          "art": ["  ~~~", " (~~~)", "  ~~~"]},
         {"name": "Wax Sentinel", "hp": 26, "atk": 8, "def": 5, "xp": 18, "gold": 12,
          "art": ["  [HEX]", " [     ]", "  [HEX]"]}],
        "The Mega Queen", 80, 15, 5, 110, 85,
        ["    /====\\     ", "   / O  O \\    ", "  | |BUZZ| |   ",
         "   \\|    |/    ", "  ~~~~~~~~     "],
        ["A massive queen bee descends from the ceiling.",
         "Mega Queen: MY HIVES. MY TERRITORY.",
         "Mega Queen: YOU ARE NOT A BEE."],
        550, {"name": "Queen's Honey", "hp_bonus": 25, "spd_bonus": 2})

    # ── Berrien East ──
    write_quest(
        "quest_berrien_east", "The Windmill Ghost",
        "An old Dutch windmill is grinding grain by itself at midnight.", "seg_5_3",
        ["The old Huss farm had a windmill built by Dutch settlers.",
         "It hasn't worked in fifty years. Until last month.",
         "Fresh flour on the millstone every morning."],
        "farmer_huss", "Old Man Huss", "H",
        ["  .---.", " ( >.< )", "  \\   /", " [HUSS]", "  +--+"],
        ["Huss: That's MY windmill. MY family built it.",
         "Huss: Whatever's grinding grain at midnight don't pay rent.",
         "Huss: There's a cellar entrance around back.", "",
         "  [Quest accepted: The Windmill Ghost]"],
        ["Huss: Clean. Good. Maybe I'll fix her up proper.", "  [Quest complete!]"],
        "windmill_cellar", "Windmill Cellar", 16, "gray", 3,
        "A stone cellar beneath the windmill. Flour dust fills the air.",
        [{"name": "Flour Phantom", "hp": 14, "atk": 6, "def": 2, "xp": 10, "gold": 5,
          "art": ["  ...", " (. .)", "  ..."]},
         {"name": "Gear Golem", "hp": 24, "atk": 7, "def": 6, "xp": 18, "gold": 10,
          "art": ["  .=.", " /ooo\\", "  \\o/"]},
         {"name": "Mill Rat", "hp": 10, "atk": 8, "def": 1, "xp": 8, "gold": 4,
          "art": ["  (\\.)", " (~.~)", "  ~~~"]}],
        "The Miller", 80, 15, 5, 110, 85,
        ["    .---.      ", "   / o o \\     ", "  |[FLOUR]|    ",
         "   \\     /     ", "  GRIST MILL   "],
        ["Flour cascades from the ceiling.",
         "Miller: THE GRAIN MUST BE GROUND.", "Miller: I WILL NOT BREAK MY WORD."],
        550, {"name": "Miller's Endurance", "def_bonus": 3, "hp_bonus": 15})

    # ── Watervliet ──
    write_quest(
        "quest_watervliet_area", "The Paper Mill Curse",
        "The old paper mill is producing prophetic paper.", "seg_2_2",
        ["Watervliet had a paper mill on the Paw Paw River.",
         "Paper started coming out of the old machinery.",
         "Words appear on it. Warnings. Things that haven't happened yet."],
        "reporter", "Lisa", "L",
        ["  .---.", " ( o.o )", "  \\   /", " [NEWS]", " [PAD!]"],
        ["Lisa: *shows paper* 'Bridge collapse, March 15.'",
         "Lisa: That was yesterday!",
         "Lisa: Something in the mill basement is writing the future.", "",
         "  [Quest accepted: The Paper Mill Curse]"],
        ["Lisa: The last sheet? Blank. The future's ours to write.", "  [Quest complete!]"],
        "paper_mill", "Paper Mill Basement", 20, "white", 4,
        "Machinery runs itself. Paper scrolls fly through the air.",
        [{"name": "Paper Wasp", "hp": 12, "atk": 7, "def": 1, "xp": 10, "gold": 5,
          "art": ["  /\\", " /  \\", "  \\/"]},
         {"name": "Ink Blob", "hp": 20, "atk": 6, "def": 4, "xp": 14, "gold": 8,
          "art": ["  ooo", " ooooo", "  ooo"]},
         {"name": "Scroll Golem", "hp": 28, "atk": 8, "def": 5, "xp": 20, "gold": 12,
          "art": ["  [===]", " [WORDS]", "  [===]"]}],
        "The Oracle Press", 100, 18, 6, 145, 105,
        ["  [=========]  ", "  |  PRESS  |  ", "  | | THE | |  ",
         "  | |FUTUR| |  ", "  [=========]  "],
        ["Words form in the air, written in ink:",
         "Oracle: I SEE ALL ENDINGS.", "Oracle: LET ME SHOW YOU HOW THIS STORY ENDS."],
        700, {"name": "Prophet's Insight", "mp_bonus": 25, "spd_bonus": 2})

    # ── Eau Claire West ──
    write_quest(
        "quest_eau_claire_west", "The Covered Bridge",
        "The old covered bridge keeps rebuilding itself overnight.", "seg_3_4",
        ["There used to be a covered bridge on the road to Eau Claire.",
         "It burned in 1952. But it grew back. Wood and all.",
         "The county tore it down. It grew back by morning."],
        "road_crew", "Hank", "H",
        ["  .---.", " ( -.- )", "  |   |", " [ROAD]", " [CREW]"],
        ["Hank: We tore it down Monday. It was back Tuesday.",
         "Hank: There's something under the bridge. A cave.",
         "Hank: I'm not going under a bridge that rebuilds itself.", "",
         "  [Quest accepted: The Covered Bridge]"],
        ["Hank: Bridge is still there. But it stopped growing.", "  [Quest complete!]"],
        "bridge_cave", "Under the Bridge", 16, "green", 3,
        "A cave beneath the creek. Wooden roots grow from the ceiling.",
        [{"name": "Wood Sprite", "hp": 14, "atk": 6, "def": 3, "xp": 12, "gold": 6,
          "art": ["  .|.", " /.|.\\", "  '-'"]},
         {"name": "Nail Swarm", "hp": 10, "atk": 9, "def": 1, "xp": 10, "gold": 5,
          "art": ["  ///", " ////", "  ///"]},
         {"name": "Plank Golem", "hp": 26, "atk": 7, "def": 6, "xp": 18, "gold": 10,
          "art": ["  [==]", " [    ]", "  [==]"]}],
        "The Bridge Keeper", 75, 14, 5, 100, 80,
        ["    .---.      ", "   / o o \\     ", "  | BUILT |    ",
         "  | 1887  |    ", "  ==BRIDGE==   "],
        ["A figure steps from the wall.",
         "Bridge Keeper: I BUILT THIS BRIDGE WITH MY OWN HANDS.",
         "Bridge Keeper: GOOD WORK ENDURES."],
        500, {"name": "Builder's Resolve", "def_bonus": 3, "hp_bonus": 15})

    print(f"\nDone!")


if __name__ == "__main__":
    main()
