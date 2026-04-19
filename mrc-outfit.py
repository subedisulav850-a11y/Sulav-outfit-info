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

# API Keys removed

BACKGROUND_FILENAME = "background.png"
CANVAS_SIZE = (570, 720)
IMAGE_TIMEOUT = 8

# --- ICON API ---
ICON_URL = "https://cdn.jsdelivr.net/gh/ShahGCreator/icon@main/PNG/{item_id}.png"

# --- OUTFIT CATEGORIES ---
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
        "default": None,
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
    """Fetch player info from the new API endpoint."""
    try:
        url = f"https://mafuuuu-info-api.vercel.app/mafu-info?uid={uid}"
        resp = session.get(url, timeout=IMAGE_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, dict):
                # Check if we have profileInfo with clothes
                if data.get("profileInfo", {}).get("clothes"):
                    print(f"  [✓] Player info fetched for UID: {uid}")
                    return data
                else:
                    print(f"  [✗] No clothes data found for UID: {uid}")
                    return None
        else:
            print(f"  [✗] API returned status {resp.status_code} for UID: {uid}")
            return None
    except Exception as e:
        print(f"  [✗] Error fetching player info: {str(e)}")
        return None

def extract_outfit_ids(player_data: dict) -> list:
    """Extract equipped item IDs from the new API response format."""
    if not player_data:
        return []

    # Get clothes from profileInfo (new API format)
    clothes = player_data.get("profileInfo", {}).get("clothes", [])
    
    if isinstance(clothes, dict):
        clothes = list(clothes.values())
    
    # Convert to strings
    all_ids = [str(cid) for cid in clothes if cid]
    
    # Note: The new API doesn't seem to have weapon skins in the response
    # If needed, you can add weapon ID extraction here
    
    print(f"  [i] Found {len(all_ids)} clothing items: {all_ids}")
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
    
    # No API key check - removed

    if not uid:
        return jsonify({'error': 'Missing uid parameter', 'status': 'bad_request'}), 400

    # 1. Fetch player data from new API
    print(f"\n[*] Generating outfit: UID={uid}")
    player_data = fetch_player_info(uid)
    if not player_data:
        return jsonify({'error': 'Player not found or has no outfit data', 'status': 'not_found'}), 404

    # 2. Extract equipped item IDs
    outfit_ids = extract_outfit_ids(player_data)
    if not outfit_ids:
        return jsonify({'error': 'No outfit items found for this player', 'status': 'not_found'}), 404

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
        'usage': '/outfit?uid=PLAYER_UID',
        'status': 'online'
    })

if __name__ == '__main__':
    print("=" * 50)
    print("  SULAV OUTFIT API")
    print("  Port: 5000")
    print("  Usage: /outfit?uid=123456")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)