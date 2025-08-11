import re
import aiohttp
import xml.etree.ElementTree as ET
from pytz import timezone

API_WOTD = "https://api.dicionario-aberto.net/wotd"
API_RANDOM = "https://api.dicionario-aberto.net/random"
API_WORD = "https://api.dicionario-aberto.net/word"

TZ = timezone("America/Sao_Paulo")

def _clean_markup(text: str) -> str:
    text = re.sub(r"\[\[([^:\]]+)(?::\d+)?\]\]", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()

def _parse_xml(xml_str: str) -> dict:
    root = ET.fromstring(xml_str)
    orth = root.findtext(".//form/orth") or "—"
    senses = []
    for sense in root.findall(".//sense"):
        gram = sense.findtext("gramGrp")
        defs = [d.text for d in sense.findall("def") if d.text]
        if defs:
            senses.append({"gram": gram, "def": _clean_markup(" ".join(defs))})
    return {"orth": orth, "senses": senses}

async def fetch_wotd():
    async with aiohttp.ClientSession() as session:
        async with session.get(API_WOTD, timeout=15) as r:
            r.raise_for_status()
            data = await r.json()
    entry = _parse_xml(data["xml"])
    lines = []
    for i, s in enumerate(entry["senses"][:3], start=1):
        tag = f"_{s['gram']}_" if s.get("gram") else ""
        lines.append(f"**{i}.** {tag} {s['def']}".strip())
    description = "\n".join(lines) if lines else "Sem definição disponível."
    return entry["orth"], description

async def fetch_random_word():
    """
    Passo 1: /random -> {'word': '...', 'wid': ..., 'sense': ...}
    Passo 2: /word/{word}[/{sense}] -> pega XML e parseia
    """
    async with aiohttp.ClientSession() as session:
        # pega a palavra aleatória
        async with session.get(API_RANDOM, timeout=15) as r:
            r.raise_for_status()
            rnd = await r.json()
        word = rnd["word"]
        sense = rnd.get("sense")

        # busca o verbete completo (se vier sense, tenta usá-lo)
        url = f"{API_WORD}/{word}" if not sense else f"{API_WORD}/{word}/{sense}"
        async with session.get(url, timeout=15) as r:
            r.raise_for_status()
            payload = await r.json()

    # payload pode ser lista (várias aceções) ou obj único
    xml_str = payload["xml"] if isinstance(payload, dict) else payload[0]["xml"]
    entry = _parse_xml(xml_str)

    lines = []
    for i, s in enumerate(entry["senses"][:3], start=1):
        tag = f"_{s['gram']}_" if s.get("gram") else ""
        lines.append(f"**{i}.** {tag} {s['def']}".strip())
    description = "\n".join(lines) if lines else "Sem definição disponível."
    # entry["orth"] aqui deve coincidir com word, mas preferimos o orth normalizado do XML
    return entry["orth"], description

async def post_wotd(dest_channel):
    word, description = await fetch_wotd()
    await dest_channel.send(f"**A palavra do dia é:** *{word}*!!!\n{description}")

async def post_random_word(dest_channel):
    word, description = await fetch_random_word()
    await dest_channel.send(f"**A palavra aleatória é:** *{word}*!!!\n{description}")

