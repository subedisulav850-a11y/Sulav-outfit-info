from flask import Flask, request, jsonify, send_file
import requests
from PIL import Image
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import os

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=12)
session = requests.Session()

# ==============================================================================
# [★] SULAV OUTFIT API
# [★] DEVELOPED BY: SULAV
# ==============================================================================

API_KEYS = ["MRC", "SULAV", "DROX", "AJAY"]  # Add multiple keys: ["MRC", "key2", "key3"]
BACKGROUND_FILENAME = "background.png"
CANVAS_SIZE = (570, 720)
IMAGE_TIMEOUT = 8

# --- SERVERS (Auto-try order) ---
SERVERS = ["sg", "br", "me", "pk", "ind", "us", "sac", "cis", "bd", "tw", "th"]

# --- ICON API ---
ICON_URL = "https://cdn.jsdelivr.net/gh/ShahGCreator/icon@main/PNG/{item_id}.png"

# --- OUTFIT CATEGORIES ---
# IMPORTANT: Mask must come BEFORE Head!
# Both use "211" prefix and in equipedskills list
# mask ID (211036xxx) comes before head ID (211000xxx).
# Via used_ids mechanism:
#   - First "211" match → Mask
#   - Second "211" match → Head
OUTFIT_SLOTS = [
    {
        "name": "Mask",
        "prefix": "211",
        "default": "208000000",
        "pos": {'x': 197, 'y': 0, 'width': 185, 'height': 238}
    },
    {
        "name": "Head",
        "prefix": "211",
        "default": "211000000",
        "pos": {'x': 4, 'y': 0, 'width': 185, 'height': 238}
    },
    {
        "name": "Face Paint",
        "prefix": "214",
        "default": "214000000",
        "pos": {'x': 388, 'y': 0, 'width': 182, 'height': 238}
    },
    {
        "name": "Top",
        "prefix": "203",
        "default": "203000000",
        "pos": {'x': 4, 'y': 242, 'width': 181, 'height': 237}
    },
    {
        "name": "Bottom",
        "prefix": "204",
        "default": "204000000",
        "pos": {'x': 197, 'y': 242, 'width': 181, 'height': 237}
    },
    {
        "name": "Shoes",
        "prefix": "205",
        "default": "205000000",
        "pos": {'x': 388, 'y': 242, 'width': 181, 'height': 237}
    },
    {
        "name": "Loot Crate",
        "prefix": "912",
        "default": "900000015",
        "pos": {'x': 388, 'y': 482, 'width': 182, 'height': 240}
    },
    {
        "name": "Weapon",
        "prefix": "907",
        "default": None,  # No default, skip if not found
        "pos": {'x': 193, 'y': 480, 'width': 186, 'height': 238}
    },
    {
        "name": "Bundle",
        "prefix": "203",
        "default": "212000000",
        "pos": {'x': 4, 'y': 482, 'width': 181, 'height': 238}
    },
]


def fetch_player_info(uid: str):
    """Try all servers to fetch player info, return first successful result."""
    for server in SERVERS:
        try:
            url = f"https://mrc-info.vercel.app/get_player_personal_show?server={server}&uid={uid}"
            resp = session.get(url, timeout=IMAGE_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, dict):
                    # Skip error responses
                    if data.get("error") or data.get("status") == "error":
                        continue
                    # If profileinfo.equipedskills exists, this is the correct server
                    profile = data.get("profileinfo", {})
                    if profile.get("equipedskills"):
                        print(f"  [✓] Server found: {server} (UID: {uid})")
                        return data
                    # profileinfo exists but equipedskills missing, still accept
                    if data.get("basicinfo") or data.get("profileinfo"):
                        print(f"  [✓] Server found: {server} (UID: {uid}) - Outfit data may be missing")
                        return data
        except Exception:
            continue
    return None


def extract_outfit_ids(player_data: dict) -> list:
    """Extract equipped item IDs from player data.
    
    API response format:
      profileinfo.equipedskills: [205052003, 203000592, 214000000, 204046004, 211049002]
        → shoes, top, face paint, bottom, head/mask
      basicinfo.weaponskinshows: [907194006, 912052002, 914047001]
        → weapon, loot crate, (unknown - skipped)
    """
    if not player_data:
        return []

    # 1. Outfit IDs (profileinfo.equipedskills)
    outfit_ids = (
        player_data.get("profileinfo", {}).get("equipedskills") or
        player_data.get("profileinfo", {}).get("EquippedOutfit") or
        player_data.get("AccountProfileInfo", {}).get("EquippedOutfit") or
        player_data.get("AccountProfileInfo", {}).get("equipedOutfit") or
        []
    )

    if isinstance(outfit_ids, dict):
        outfit_ids = list(outfit_ids.values())

    all_ids = [str(oid) for oid in outfit_ids if oid]

    # 2. Weapon & Animation IDs (basicinfo.weaponskinshows)
    weapon_ids = player_data.get("basicinfo", {}).get("weaponskinshows", [])
    if isinstance(weapon_ids, dict):
        weapon_ids = list(weapon_ids.values())
    for wid in weapon_ids:
        str_wid = str(wid)
        if str_wid not in all_ids:
            all_ids.append(str_wid)

    return all_ids


def fetch_icon_image(item_id: str):
    """Download a single item icon."""
    url = ICON_URL.format(item_id=item_id)
    try:
        resp = session.get(url, timeout=IMAGE_TIMEOUT)
        if resp.status_code == 200:
            return Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception:
        pass
    return None


def find_item_for_slot(slot: dict, outfit_ids: list, used_ids: set) -> str | None:
    """Find appropriate item ID for a slot."""
    prefix = slot["prefix"]

    # Search for matching category in player's equipped items
    for oid in outfit_ids:
        if oid.startswith(prefix) and oid not in used_ids:
            used_ids.add(oid)
            return oid

    # If not found, use default (if available)
    if slot["default"]:
        return slot["default"]

    return None


@app.route('/outfit', methods=['GET'])
def make_outfit():
    uid = request.args.get('uid')
    key = request.args.get('key')

    if key not in API_KEYS:
        return jsonify({'error': 'Invalid API Key', 'status': 'unauthorized'}), 401
    if not uid:
        return jsonify({'error': 'Missing uid parameter', 'status': 'bad_request'}), 400

    # 1. Fetch player data (try all servers)
    print(f"\n[*] Generating outfit: UID={uid}")
    player_data = fetch_player_info(uid)
    if not player_data:
        return jsonify({'error': 'Player not found (all servers tried)', 'status': 'not_found'}), 404

    # 2. Extract equipped item IDs
    outfit_ids = extract_outfit_ids(player_data)
    print(f"  [i] Outfit IDs found: {len(outfit_ids)}")
    if outfit_ids:
        print(f"  [i] IDs: {outfit_ids}")

    # 3. Find matching item for each slot and download icons in parallel
    used_ids = set()
    download_tasks = []

    for slot in OUTFIT_SLOTS:
        item_id = find_item_for_slot(slot, outfit_ids, used_ids)
        if item_id:
            future = executor.submit(fetch_icon_image, item_id)
            download_tasks.append((slot, future, item_id))
        else:
            print(f"  [~] {slot['name']}: Skipped (no item)")

    # 4. Open background image
    bg_path = os.path.join(os.path.dirname(__file__), BACKGROUND_FILENAME)
    try:
        background = Image.open(bg_path).convert("RGBA")
    except FileNotFoundError:
        return jsonify({'error': f'{BACKGROUND_FILENAME} not found! Place it in the OUTFIT folder.'}), 500
    except Exception as e:
        return jsonify({'error': f'Background error: {str(e)}'}), 500

    # Create canvas
    canvas_w, canvas_h = CANVAS_SIZE if CANVAS_SIZE else background.size
    bg_resized = background.resize((canvas_w, canvas_h), Image.LANCZOS)
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    canvas.paste(bg_resized, (0, 0))

    # 5. Paste downloaded icons at their coordinates
    for slot, future, item_id in download_tasks:
        icon_img = future.result()
        if icon_img:
            pos = slot["pos"]
            icon_resized = icon_img.resize((pos['width'], pos['height']), Image.LANCZOS)
            paste_y = max(0, pos['y'])
            canvas.paste(icon_resized, (pos['x'], paste_y), icon_resized)
            print(f"  [✓] {slot['name']}: {item_id}")
        else:
            print(f"  [✗] {slot['name']}: Icon download failed ({item_id})")

    # 6. Send as PNG
    output = BytesIO()
    canvas.save(output, format='PNG', optimize=True)
    output.seek(0)

    print(f"  [✓] Outfit image generated!")
    return send_file(output, mimetype='image/png')


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'api': 'SULAV Outfit API',
        'usage': '/outfit?uid=PLAYER_UID&key=API_KEY',
        'status': 'online'
    })


if __name__ == '__main__':
    print("=" * 50)
    print("  SULAV OUTFIT API")
    print("  Port: 5000")
    print(f"  Usage: /outfit?uid=123456&key={API_KEYS[0]}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
