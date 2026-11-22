"""Constants and protocol mappings for Gemmy Orchestra of Lights."""

from __future__ import annotations

DOMAIN = "orchestra_of_lights"

CONF_HUB_ID = "hub_id"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_PASSWORD = "password"
CONF_TRANSPORT = "transport"

TRANSPORT_AUTO = "auto"
TRANSPORT_LOCAL = "local"
TRANSPORT_CLOUD = "cloud"

DEFAULT_PORT = 8087
DEFAULT_NAME = "Orchestra of Lights"

# AWS IoT / Cognito constants from Gemmy Orchestra of Lights app v4.3.6
AWS_COGNITO_REGION = "us-east-1"
AWS_COGNITO_POOL_ID = "us-east-1:6a9bb944-b74f-4939-a3c3-3f7a557bc167"
AWS_IOT_REGION = "us-east-2"
AWS_IOT_ENDPOINT = "a9bt9m72hzndo-ats.iot.us-east-2.amazonaws.com"

# Effects (index -> name)
EFFECTS: dict[int, str] = {
    0: "Steady",
    1: "Glimmer",
    2: "Sparkle",
    3: "Starry Night",
    4: "Lightshow",
}
EFFECT_NAME_TO_ID: dict[str, int] = {v: k for k, v in EFFECTS.items()}

# Preset full lightshows (always use effect = 4)
PRESET_LIGHTSHOWS: dict[int, str] = {
    0: "Christmas LightShow",
    1: "Rainbow Wave",
    2: "Frozen Fire",
    4: "Color Frenzy",
}

# Holiday themes (r4 in app; support effects 0..4)
HOLIDAY_THEMES: dict[int, str] = {
    26: "Valentine's Day",
    27: "St. Patrick's Day",
    28: "Mardi Gras",
    29: "Easter",
    30: "Independence Day",
    31: "Halloween",
    32: "Thanksgiving",
}

# Solid color themes (s4[0..20] in app; support effects 0..3)
SOLID_COLOR_THEMES: dict[int, str] = {
    5: "Pure White",
    6: "Warm White",
    7: "Polar White",
    8: "Soft White",
    9: "Antique White",
    10: "Incandescent White",
    11: "Gold",
    12: "Red",
    13: "Orange",
    14: "Golden Yellow",
    15: "Acid Yellow",
    16: "Chartreuse",
    17: "Green",
    18: "Mint",
    19: "Turquoise",
    20: "Blue",
    21: "Royal Blue",
    22: "Lavender",
    23: "Pink",
    24: "Fuchsia",
    25: "Purple",
}

# Dual & multi-color themes (s4[21..32] in app; support effects 0..4)
MULTI_COLOR_THEMES: dict[int, str] = {
    33: "Red & White",
    34: "Red & Green",
    35: "White & Blue",
    41: "Red & Blue",
    37: "Pink & Purple",
    38: "Pink & Green",
    39: "Red & Turquoise",
    40: "Red, Turquoise & Chartreuse",
    36: "Red, White & Chartreuse",
    43: "Red, Green, Blue & Yellow",
    42: "Multicolor",
    3: "Multichange",
}

# Combined theme ID -> display name
THEMES: dict[int, str] = {
    **PRESET_LIGHTSHOWS,
    **HOLIDAY_THEMES,
    **SOLID_COLOR_THEMES,
    **MULTI_COLOR_THEMES,
}
THEME_NAME_TO_ID: dict[str, int] = {v: k for k, v in THEMES.items()}

# Built-in songs (0..5 Gen 1 + Gen 2; 6..11 Op. 2 speakers)
SONGS: dict[int, str] = {
    0: "Jingle Bells (Instrumental)",
    1: "Classic Christmas Medley",
    2: "Bell Carol",
    3: "Dance of the Sugar Plum Fairy",
    4: "Deck the Halls",
    5: "Religious Medley",
    6: "Jingle Bells (Vocal)",
    7: "Feliz Navidad",
    8: "Jolly Old St. Nicholas",
    9: "Magic Sleigh Ride",
    10: "Santa's Gonna Swing Tonight",
    11: "Have Yourself a Merry Little Christmas",
}
SONG_NAME_TO_ID: dict[str, int] = {v: k for k, v in SONGS.items()}

# Paired 2.4 GHz device type IDs (from m0/c.java)
DEVICE_TYPES: dict[int, str] = {
    1: "Lightshow Tree",
    2: "Speaker",
    3: "Lightshow Box",
    4: "Projection Set of 5",
    5: "Projection Set of 3",
    6: "SnowFlurry",
    7: "Edison Light Bulb",
    12: "TubeLights Pathway",
    14: "Lightshow Tree",
    15: '22" Moravian Star',
    17: "Candy Cane Arch Pathway",
    18: "12' Rope Light",
    21: '36" Snowflake',
    22: '24" Tube Light Starburst Op. 2',
    23: "Star Tree Topper Op. 2",
    25: "Tree Kit Op. 2",
    29: "Snowflake Ornament Garland Op. 2",
    31: "Wire Frame Ornament Op. 2",
    32: "Virtuoso Speaker Op. 2",
    33: "Snowflake Pathway Op. 2",
    34: "C9 Light String Op. 2",
    35: "Curtain Light Op. 2",
    36: "Candy Cane Pathway Op. 2",
    37: "NetLight Op. 2",
    38: "TubeLights Op. 2",
    39: "Modern Angled Icicle Op. 2",
    40: "Candy Cane Lightshow Pathway Arch Op. 2",
    41: "Rope Light Op. 2",
    42: '36" Snowflake Op. 2',
    43: "Edison Style Bulb Op. 2",
    44: '22" Moravian Star Op. 2',
    45: "Merry Moves Projection Set Op. 2",
    46: "Speaker Op. 2",
    47: "Premium Speaker Op. 2",
    48: "Lightshow Christmas Tree Op. 2",
    49: "24' Lighted Spheres Op. 2",
    50: "Blow Mold Christmas Bulb Op. 2",
    51: "Dancing Light String Op. 2",
    54: "12' Lighted Spheres Op. 2",
    128: "Topiary Tree",
    129: "Topiary Tree",
    130: "Mini Light String",
    131: "Mini Lights",
    132: "C9 Light String",
    133: "C9 Lights",
    134: "Hanging Snowflake",
    135: '36" Snowflake',
    136: "Lightshow Tree",
    137: "Lightshow Tree",
    138: "Lighted Wreath",
    139: "Wreath",
    140: "Lighted Garland",
    141: "Garland",
    142: "G100 Light String",
    143: "G100 Lights",
    144: "Faceted Icicle Light String",
    145: "Color Changing Icicle",
    146: "Dancing Icicle",
    147: "Dancing Icicle",
    148: "Candy Cane Pathway",
    149: "Candy Cane Pathway",
    150: "Lightshow Tree",
    151: "Snowman Pathway",
    152: "C7 Light String",
    153: "Hanging Sign",
    160: "Gift Box Pathway",
    161: "NetLight",
    162: '48" Snowman',
    163: '36" Gift Stack',
}

# Op. 2 speaker IDs that unlock songs 6..11
OP2_SPEAKER_IDS = {32, 45, 46, 47, 53}
