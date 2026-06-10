"""
Xeno-canto API Client for Chinese Bird Sound Data.
Fetches bird recordings from xeno-canto.org for training the CNN model.
Xeno-canto is the primary open bird sound database referenced in Sugai et al. (2026).
"""

import os
import json
import time
import requests
from pathlib import Path
from typing import Optional

API_BASE = "https://xeno-canto.org/api/3/recordings"
_CONFIG_DIR = Path(
    os.environ.get("BIRD_PLATFORM_CONFIG_DIR", Path.home() / ".bird_sound_platform")
).expanduser()
_KEY_FILE = _CONFIG_DIR / "xc_api_key"


def _load_api_key() -> str:
    """Load API key from env var or local file."""
    key = os.environ.get("XC_API_KEY", "")
    if key:
        return key
    try:
        if _KEY_FILE.exists():
            return _KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return ""


def set_api_key(key: str):
    """Persist API key to an app-specific config file outside the repo."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_text(key.strip(), encoding="utf-8")


def get_api_key() -> str:
    return _load_api_key()


# Common Chinese bird species list (50 representative species spanning
# multiple families found in China including Taiwan)
CHINA_BIRD_SPECIES = [
    # Passeriformes (雀形目)
    {"scientific": "Garrulax canorus", "chinese": "画眉", "english": "Chinese Hwamei"},
    {
        "scientific": "Leiothrix lutea",
        "chinese": "红嘴相思鸟",
        "english": "Red-billed Leiothrix",
    },
    {
        "scientific": "Urocissa erythroryncha",
        "chinese": "红嘴蓝鹊",
        "english": "Red-billed Blue Magpie",
    },
    {
        "scientific": "Copsychus saularis",
        "chinese": "鹊鸲",
        "english": "Oriental Magpie-Robin",
    },
    {
        "scientific": "Pycnonotus sinensis",
        "chinese": "白头鹎",
        "english": "Light-vented Bulbul",
    },
    {
        "scientific": "Pycnonotus jocosus",
        "chinese": "红耳鹎",
        "english": "Red-whiskered Bulbul",
    },
    {
        "scientific": "Oriolus chinensis",
        "chinese": "黑枕黄鹂",
        "english": "Black-naped Oriole",
    },
    {
        "scientific": "Cyanoptila cyanomelana",
        "chinese": "白腹姬鹟",
        "english": "Blue-and-white Flycatcher",
    },
    {
        "scientific": "Tarsiger cyanurus",
        "chinese": "红胁蓝尾鸲",
        "english": "Orange-flanked Bush-Robin",
    },
    {
        "scientific": "Ficedula narcissina",
        "chinese": "黄眉姬鹟",
        "english": "Narcissus Flycatcher",
    },
    {
        "scientific": "Phylloscopus coronatus",
        "chinese": "冕柳莺",
        "english": "Eastern Crowned Warbler",
    },
    {
        "scientific": "Paradoxornis webbianus",
        "chinese": "棕头鸦雀",
        "english": "Vinous-throated Parrotbill",
    },
    {
        "scientific": "Emberiza cioides",
        "chinese": "三道眉草鹀",
        "english": "Meadow Bunting",
    },
    {"scientific": "Parus major", "chinese": "大山雀", "english": "Great Tit"},
    {
        "scientific": "Aegithalos concinnus",
        "chinese": "红头长尾山雀",
        "english": "Black-throated Bushtit",
    },
    {
        "scientific": "Lanius schach",
        "chinese": "棕背伯劳",
        "english": "Long-tailed Shrike",
    },
    {
        "scientific": "Dicrurus macrocercus",
        "chinese": "黑卷尾",
        "english": "Black Drongo",
    },
    {
        "scientific": "Sturnus sericeus",
        "chinese": "丝光椋鸟",
        "english": "Red-billed Starling",
    },
    {
        "scientific": "Zosterops japonicus",
        "chinese": "暗绿绣眼鸟",
        "english": "Japanese White-eye",
    },
    {
        "scientific": "Passer montanus",
        "chinese": "麻雀",
        "english": "Eurasian Tree Sparrow",
    },
    # Cuculiformes (鹃形目)
    {"scientific": "Cuculus canorus", "chinese": "大杜鹃", "english": "Common Cuckoo"},
    {"scientific": "Eudynamys scolopaceus", "chinese": "噪鹃", "english": "Asian Koel"},
    # Strigiformes (鸮形目)
    {"scientific": "Otus lettia", "chinese": "领角鸮", "english": "Collared Scops Owl"},
    {"scientific": "Ninox scutulata", "chinese": "鹰鸮", "english": "Brown Hawk-Owl"},
    # Piciformes (鴷形目)
    {
        "scientific": "Dendrocopos canicapillus",
        "chinese": "星头啄木鸟",
        "english": "Grey-capped Pygmy Woodpecker",
    },
    {
        "scientific": "Picus canus",
        "chinese": "灰头绿啄木鸟",
        "english": "Grey-headed Woodpecker",
    },
    # Coraciiformes (佛法僧目)
    {
        "scientific": "Halcyon smyrnensis",
        "chinese": "白胸翡翠",
        "english": "White-throated Kingfisher",
    },
    {
        "scientific": "Alcedo atthis",
        "chinese": "普通翠鸟",
        "english": "Common Kingfisher",
    },
    {
        "scientific": "Merops philippinus",
        "chinese": "栗喉蜂虎",
        "english": "Blue-tailed Bee-eater",
    },
    # Pelecaniformes (鹈形目) — including herons
    {
        "scientific": "Gorsachius magnificus",
        "chinese": "海南鳽",
        "english": "White-eared Night Heron",
    },
    {
        "scientific": "Nycticorax nycticorax",
        "chinese": "夜鹭",
        "english": "Black-crowned Night Heron",
    },
    {"scientific": "Egretta garzetta", "chinese": "白鹭", "english": "Little Egret"},
    {"scientific": "Ardea cinerea", "chinese": "苍鹭", "english": "Grey Heron"},
    # Accipitriformes (鹰形目)
    {
        "scientific": "Spilornis cheela",
        "chinese": "蛇雕",
        "english": "Crested Serpent Eagle",
    },
    {"scientific": "Accipiter virgatus", "chinese": "松雀鹰", "english": "Besra"},
    # Falconiformes (隼形目)
    {"scientific": "Falco tinnunculus", "chinese": "红隼", "english": "Common Kestrel"},
    # Galliformes (鸡形目)
    {
        "scientific": "Chrysolophus pictus",
        "chinese": "红腹锦鸡",
        "english": "Golden Pheasant",
    },
    {
        "scientific": "Bambusicola thoracicus",
        "chinese": "灰胸竹鸡",
        "english": "Chinese Bamboo Partridge",
    },
    {
        "scientific": "Tragopan temminckii",
        "chinese": "红腹角雉",
        "english": "Temminck's Tragopan",
    },
    # Gruiformes (鹤形目)
    {
        "scientific": "Amaurornis phoenicurus",
        "chinese": "白胸苦恶鸟",
        "english": "White-breasted Waterhen",
    },
    # Columbiformes (鸽形目)
    {
        "scientific": "Streptopelia chinensis",
        "chinese": "珠颈斑鸠",
        "english": "Spotted Dove",
    },
    {
        "scientific": "Treron sieboldii",
        "chinese": "红翅绿鸠",
        "english": "White-bellied Green Pigeon",
    },
    # Caprimulgiformes (夜鹰目)
    {
        "scientific": "Caprimulgus indicus",
        "chinese": "普通夜鹰",
        "english": "Grey Nightjar",
    },
    # Apodiformes (雨燕目)
    {
        "scientific": "Apus nipalensis",
        "chinese": "小白腰雨燕",
        "english": "House Swift",
    },
    # Charadriiformes (鸻形目)
    {
        "scientific": "Vanellus vanellus",
        "chinese": "凤头麦鸡",
        "english": "Northern Lapwing",
    },
    # Anseriformes (雁形目)
    {"scientific": "Aix galericulata", "chinese": "鸳鸯", "english": "Mandarin Duck"},
    # Psittaciformes (鹦鹉目)
    {
        "scientific": "Psittacula alexandri",
        "chinese": "绯胸鹦鹉",
        "english": "Red-breasted Parakeet",
    },
    # Bucerotiformes (犀鸟目)
    {"scientific": "Upupa epops", "chinese": "戴胜", "english": "Eurasian Hoopoe"},
    # Passeriformes additional
    {"scientific": "Cinclus pallasii", "chinese": "褐河乌", "english": "Brown Dipper"},
    {
        "scientific": "Sitta europaea",
        "chinese": "普通鳾",
        "english": "Eurasian Nuthatch",
    },
]


def _parse_recording(r: dict) -> dict:
    """Parse a single recording object from xeno-canto API v3 response."""
    file_url = r.get("file", "")
    if file_url.startswith("//"):
        file_url = "https:" + file_url
    sono = r.get("sono", {})
    sono_url = ""
    if isinstance(sono, dict):
        sono_url = sono.get("small", "")
        if sono_url.startswith("//"):
            sono_url = "https:" + sono_url
    return {
        "id": r.get("id", ""),
        "species": r.get("en", ""),
        "scientific_name": f'{r.get("gen", "")} {r.get("sp", "")}',
        "country": r.get("cnt", ""),
        "locality": r.get("loc", ""),
        "latitude": r.get("lat", ""),
        "longitude": r.get("lon", r.get("lng", "")),
        "type": r.get("type", ""),
        "quality": r.get("q", ""),
        "duration": r.get("length", ""),
        "file_url": file_url,
        "sono_url": sono_url,
        "date": r.get("date", ""),
        "recordist": r.get("rec", ""),
    }


def search_recordings(
    species_name: str, country: str = "China", quality: str = "A", max_results: int = 50
) -> list:
    """
    Search xeno-canto for bird recordings.

    Args:
        species_name: Scientific name of the species
        country: Country filter (default: China, includes Taiwan)
        quality: Minimum quality rating (A, B, C, D, E)
        max_results: Maximum number of recordings to return
    """
    # API v3 uses search tags: sp:"genus species" cnt:country q:A
    parts = [f'sp:"{species_name}"', "grp:birds"]
    if country:
        parts.append(f"cnt:{country}")
    if quality:
        parts.append(f"q:{quality}")
    query_str = " ".join(parts)
    api_key = _load_api_key()
    if not api_key:
        return [
            {
                "error": "需要Xeno-canto API Key。请在 https://xeno-canto.org/account 注册获取，然后在平台设置中填入。"
            }
        ]
    params = {"query": query_str, "key": api_key}
    try:
        resp = requests.get(API_BASE, params=params, timeout=30)
        if resp.status_code == 401:
            return [
                {
                    "error": "API Key无效或已过期。请访问 https://xeno-canto.org/account 获取有效的Key。"
                }
            ]
        if resp.status_code == 400:
            return [
                {
                    "error": f"查询格式错误: {resp.json().get('message', resp.text[:200])}"
                }
            ]
        resp.raise_for_status()
        data = resp.json()
        recordings = data.get("recordings", [])[:max_results]
        return [_parse_recording(r) for r in recordings]
    except requests.exceptions.RequestException as e:
        print(f"Error searching xeno-canto for {species_name}: {e}")
        return []
    except Exception as e:
        print(f"Error parsing xeno-canto response for {species_name}: {e}")
        return []


def search_recordings_global(species_name: str, max_results: int = 100) -> list:
    """Search xeno-canto globally (no country filter) for more training data."""
    api_key = _load_api_key()
    if not api_key:
        return []
    parts = [f'sp:"{species_name}"', "grp:birds", "q:C"]
    query_str = " ".join(parts)
    params = {"query": query_str, "key": api_key}
    try:
        resp = requests.get(API_BASE, params=params, timeout=30)
        if resp.status_code == 401:
            return []
        resp.raise_for_status()
        data = resp.json()
        recordings = data.get("recordings", [])[:max_results]
        return [_parse_recording(r) for r in recordings]
    except Exception as e:
        print(f"Error: {e}")
        return []


def download_recording(
    file_url: str, save_dir: str, recording_id: str
) -> Optional[str]:
    """Download a single recording from xeno-canto."""
    # v3 URLs may omit scheme
    if file_url.startswith("//"):
        file_url = "https:" + file_url
    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)
    # Check for existing files (mp3 or wav)
    for ext in (".mp3", ".wav"):
        candidate = save_path / f"XC{recording_id}{ext}"
        if candidate.exists():
            return str(candidate)
    api_key = _load_api_key()
    try:
        # Pass API key for authenticated download
        params = {"key": api_key} if api_key else {}
        resp = requests.get(file_url, params=params, timeout=60, stream=True)
        resp.raise_for_status()
        # Detect content type to choose extension and reject HTML
        ct = resp.headers.get("content-type", "")
        if "text/html" in ct:
            print(
                f"  Skip XC{recording_id}: got HTML instead of audio (may require login)"
            )
            return None
        ext = ".wav" if "wav" in ct else ".mp3"
        filename = save_path / f"XC{recording_id}{ext}"
        with open(filename, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return str(filename)
    except Exception as e:
        print(f"Error downloading {file_url}: {e}")
        return None


def build_training_dataset(
    data_dir: str,
    species_list: list = None,
    max_per_species: int = 30,
    country: str = "China",
):
    """
    Build training dataset by downloading recordings from xeno-canto.

    Args:
        data_dir: Root directory for saving audio files
        species_list: List of species dicts (default: CHINA_BIRD_SPECIES)
        max_per_species: Max recordings per species
        country: Country filter

    Returns:
        manifest: List of {species, file_path, metadata} dicts
    """
    if species_list is None:
        species_list = CHINA_BIRD_SPECIES

    manifest = []
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    for idx, sp in enumerate(species_list):
        species_dir = data_path / sp["scientific"].replace(" ", "_")
        species_dir.mkdir(parents=True, exist_ok=True)
        print(
            f"[{idx + 1}/{len(species_list)}] Fetching: {sp['chinese']} ({sp['scientific']})"
        )

        # v3 API: many recordings lack file URLs (~50%), request 3x to compensate
        fetch_limit = max_per_species * 3
        recordings = search_recordings(
            sp["scientific"], country=country, quality="B", max_results=fetch_limit
        )
        # Filter to only downloadable recordings
        downloadable = [r for r in recordings if r.get("file_url")]

        # If not enough from country search, try global
        if len(downloadable) < max_per_species:
            global_recs = search_recordings_global(
                sp["scientific"], max_results=fetch_limit
            )
            existing_ids = {r["id"] for r in downloadable}
            for r in global_recs:
                if r["id"] not in existing_ids and r.get("file_url"):
                    downloadable.append(r)
                    if len(downloadable) >= max_per_species:
                        break

        # Also try without quality filter if still not enough
        if len(downloadable) < max_per_species:
            more_recs = search_recordings(
                sp["scientific"], country="", quality="", max_results=fetch_limit
            )
            existing_ids = {r["id"] for r in downloadable}
            for r in more_recs:
                if r["id"] not in existing_ids and r.get("file_url"):
                    downloadable.append(r)
                    if len(downloadable) >= max_per_species:
                        break

        downloadable = downloadable[:max_per_species]
        downloaded = 0
        for rec in downloadable:
            filepath = download_recording(rec["file_url"], str(species_dir), rec["id"])
            if filepath:
                downloaded += 1
                manifest.append(
                    {
                        "species_scientific": sp["scientific"],
                        "species_chinese": sp["chinese"],
                        "species_english": sp["english"],
                        "file_path": filepath,
                        "xc_id": rec["id"],
                        "quality": rec.get("quality", ""),
                    }
                )
        print(
            f"  -> {downloaded}/{len(downloadable)} downloaded (total available: {len(recordings)})"
        )

        time.sleep(1)  # Rate limiting

    # Save manifest
    manifest_path = data_path / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"Dataset manifest saved: {manifest_path} ({len(manifest)} recordings)")
    return manifest


def get_species_list():
    """Return the Chinese bird species list with metadata."""
    return CHINA_BIRD_SPECIES


def get_species_count():
    """Return number of species in the database."""
    return len(CHINA_BIRD_SPECIES)
