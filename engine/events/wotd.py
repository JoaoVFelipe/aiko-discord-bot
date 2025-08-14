import re
import aiohttp
import xml.etree.ElementTree as ET
from pytz import timezone

API_RANDOM = "https://api.dicionario-aberto.net/random"
API_WORD = "https://api.dicionario-aberto.net/word"

TZ = timezone("America/Sao_Paulo")


def _collapse_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _clean_markup(text: str) -> str:
    text = re.sub(r"\[\[([^:\]]+)(?::\d+)?\]\]", r"\1", text or "")
    text = re.sub(r"_([^_]+)_", r"\1", text)
    return _collapse_spaces(text)


def _parse_xml(xml_str: str) -> dict:
    root = ET.fromstring(xml_str)
    orth = root.findtext(".//form/orth") or "—"
    senses = []
    for sense in root.findall(".//sense"):
        gram = _collapse_spaces(sense.findtext("gramGrp"))
        defs = []
        for d in sense.findall("def"):
            full = _collapse_spaces("".join(d.itertext()))
            if full:
                defs.append(_clean_markup(full))

        if defs:
            senses.append({"gram": gram, "def": " ".join(defs)})
    return {"orth": orth, "senses": senses}


def _best_entry_from_payload(payload) -> dict | None:
    candidates = []
    if isinstance(payload, dict) and payload.get("xml"):
        candidates.append(payload["xml"])
    elif isinstance(payload, list):
        for it in payload:
            if isinstance(it, dict) and it.get("xml"):
                candidates.append(it["xml"])

    for xml in candidates:
        entry = _parse_xml(xml)
        if entry.get("senses"):
            return entry

    return _parse_xml(candidates[0]) if candidates else None


async def _fetch_entry_payload(word: str, sense: int | None = None):
    url = f"{API_WORD}/{word}" if sense is None else f"{API_WORD}/{word}/{sense}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=15) as r:
            r.raise_for_status()
            return await r.json()


async def fetch_random_word():
    async with aiohttp.ClientSession() as session:
        async with session.get(API_RANDOM, timeout=15) as r:
            r.raise_for_status()
            rnd = await r.json()

        lookup = rnd.get("word")        # ex.: "fenigma"  (use para /word)
        sense = rnd.get("sense")        # pode ser None

        payload = await _fetch_entry_payload(lookup, sense)

    entry = _best_entry_from_payload(payload)
    if not entry:
        # fallback mínimo
        return {"orth": lookup or "—", "lookup": lookup or "—", "description": "Sem definição disponível."}
    lines = []
    for i, s in enumerate(entry["senses"][:3], start=1):
        tag = f"_{s['gram']}_" if s.get("gram") else ""
        lines.append(f"**{i}.** {tag} {s['def']}".strip())
    description = "\n".join(lines) if lines else "Sem definição disponível."

    return {"orth": entry["orth"], "lookup": lookup or entry["orth"], "description": description}


async def fetch_description_for_word(lookup_or_orth: str) -> str:
    payload = await _fetch_entry_payload(lookup_or_orth)
    entry = _best_entry_from_payload(payload)
    if not entry or not entry.get("senses"):
        return "Sem definição disponível."

    lines = []
    for i, s in enumerate(entry["senses"][:3], start=1):
        tag = f"_{s['gram']}_" if s.get("gram") else ""
        lines.append(f"**{i}.** {tag} {s['def']}".strip())
    return "\n".join(lines) if lines else "Sem definição disponível."


async def post_wotd(dest_channel, display_word: str, lookup_word: str | None = None, forced: bool = False):
    description = await fetch_description_for_word(lookup_word or display_word)
    if forced:
        await dest_channel.send(f"📖 **A palavra do dia é:** *{display_word}*!\n{description}")
    else:
        await dest_channel.send(f"📖 É hora da palavra do dia! 📖\n **E a palavra do dia é:** *{display_word}*!\n{description}")


async def post_random_word(dest_channel):
    info = await fetch_random_word()
    await dest_channel.send(f"**📖 A palavra aleatória é:** *{info['orth']}*!\n{info['description']}")
