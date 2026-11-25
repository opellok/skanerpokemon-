import asyncio
import hashlib
import json
import os
import random
import re
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

MAX_BUDGET_PLN = 600.0
MIN_DISCOUNT_PLN = 15.0
MIN_PRICE_RATIO = 0.45
SEEN_FILE = "seen_offers_v2.json"

TARGET_SETS = {
    "ascended_heroes": {"name": "Ascended Heroes", "keywords": ["ascended heroes", "ascended hero", "ascended"]},
    "30th_celebration_classic": {
        "name": "30th Celebration — Classic Collection Booster",
        "keywords": ["30th celebration", "30th anniversary", "celebrations 30", "30th"],
        "required_all": ["classic"],
        "allowed_types": ["booster_pack", "sleeved_booster", "checklane_blister"],
    },
    "prismatic_evolutions": {"name": "Prismatic Evolutions", "keywords": ["prismatic evolutions", "prismatic evolution", "prismatic", "sv8.5"]},
    "mega_evolution_base": {"name": "Mega Evolution (Base Set)", "keywords": ["mega evolution", "mega evolutions"]},
    "black_bolt": {"name": "Black Bolt", "keywords": ["black bolt", "blackbolt"]},
    "white_flare": {"name": "White Flare", "keywords": ["white flare", "whiteflare"]},
    "sv_151": {"name": "Scarlet & Violet — 151", "keywords": ["pokemon 151", "scarlet & violet 151", "scarlet violet 151", "sv 151", "sv151", "mew 151", " 151 ", "151"]},
    "crown_zenith": {"name": "Crown Zenith", "keywords": ["crown zenith", "zenith"]},
    "evolving_skies": {"name": "Evolving Skies", "keywords": ["evolving skies", "evolving"]},
    "chilling_reign": {"name": "Chilling Reign", "keywords": ["chilling reign", "chilling"]},
    "fusion_strike": {"name": "Fusion Strike", "keywords": ["fusion strike"]},
    "cosmic_eclipse": {"name": "Cosmic Eclipse", "keywords": ["cosmic eclipse"]},
    "hidden_fates": {"name": "Hidden Fates", "keywords": ["hidden fates"]},
    "unified_minds": {"name": "Unified Minds", "keywords": ["unified minds"]},
    "unbroken_bonds": {"name": "Unbroken Bonds", "keywords": ["unbroken bonds"]},
    "team_up": {"name": "Team Up", "keywords": ["team up", "teamup"]},
    "lost_thunder": {"name": "Lost Thunder", "keywords": ["lost thunder"]},
    "ultra_prism": {"name": "Ultra Prism", "keywords": ["ultra prism"]},
    "celestial_storm": {"name": "Celestial Storm", "keywords": ["celestial storm"]},
    "ancient_origins": {"name": "Ancient Origins", "keywords": ["ancient origins"]},
    "primal_clash": {"name": "Primal Clash", "keywords": ["primal clash"]},
    "roaring_skies": {"name": "Roaring Skies", "keywords": ["roaring skies"]},
    "breakthrough": {"name": "BREAKthrough", "keywords": ["breakthrough", "break through"]},
    "phantom_forces": {"name": "Phantom Forces", "keywords": ["phantom forces"]},
    "flashfire": {"name": "Flashfire", "keywords": ["flashfire", "flash fire"]},
    "legendary_treasures": {"name": "Legendary Treasures", "keywords": ["legendary treasures"]},
    "plasma_blast": {"name": "Plasma Blast", "keywords": ["plasma blast"]},
    "plasma_freeze": {"name": "Plasma Freeze", "keywords": ["plasma freeze"]},
    "plasma_storm": {"name": "Plasma Storm", "keywords": ["plasma storm"]},
    "dragons_exalted": {"name": "Dragons Exalted", "keywords": ["dragons exalted", "dragon exalted"]},
    "dark_explorers": {"name": "Dark Explorers", "keywords": ["dark explorers"]},
    "boundaries_crossed": {"name": "Boundaries Crossed", "keywords": ["boundaries crossed"]},
    "call_of_legends": {"name": "Call of Legends", "keywords": ["call of legends"]},
    "undaunted": {"name": "Undaunted", "keywords": ["undaunted"]},
    "triumphant": {"name": "Triumphant", "keywords": ["triumphant"]},
    "rising_rivals": {"name": "Rising Rivals", "keywords": ["rising rivals"]},
    "supreme_victors": {"name": "Supreme Victors", "keywords": ["supreme victors"]},
}

NON_ENGLISH_BLACKLIST = [
    "jpn", "jap", "japanese", "japoński", "japońskie", "japonski", "japonskie",
    "deu", "ger", "german", "niemiecki", "niemieckie", "deutsch",
    "fra", "fre", "french", "francuski", "francuskie", "français",
    "esp", "spa", "spanish", "hiszpański", "hiszpańskie", "hiszpanski",
    "ita", "italian", "włoski", "włoskie", "wloski",
    "kor", "korean", "koreański", "koreańskie", "koreanski",
    "chn", "chi", "chinese", "chiński", "chińskie", "chinski",
    "po polsku", "język polski", "jezyk polski", "sv2a", "s8b", "s12a", "sv8a", "sv4a",
]

FAKE_JUNK_BLACKLIST = [
    "proxy", "zamiennik", "replika", "replica", "custom", "fake", "podróbka", "podrobka",
    "fan art", "fanart", "oro", "złote karty", "zlote karty", "srebrne karty", "czarne karty",
    "55 sztuk", "55 szt", "100 sztuk", "100 szt", "360 kart", "324 karty",
    "pusty", "pusta", "puste", "bez kart", "bez boosterów", "bez boosterow", "same pudełko", "samo pudełko",
    "otwarty", "otwarta", "otwarte", "rozpakowany", "rozpakowane", "unsealed", "opened",
    "kod", "kody", "code card", "tcg live", "online", "koszulki", "sleeves", "mata", "playmat",
    "album", "segregator", "binder", "single", "singiel", "psa ", "cgc ", "bgs ", "graded",
]

SEALED_PRODUCT_TYPES = [
    ("booster_box", ["booster box", "boosterbox", "display", "36 boosterów", "36 boosterow", "36 paczek", "36 saszetek"]),
    ("pc_etb", ["pokemon center elite trainer", "pokemon center etb", "pc etb"]),
    ("etb", ["elite trainer box", "elite trainer", "etb", "zestaw trenera", "pudełko trenera", "pudelko trenera"]),
    ("booster_bundle", ["booster bundle", "boosterbundle", "bundle", "6 boosterów", "6 boosterow", "6 paczek", "6 saszetek"]),
    ("upc", ["ultra premium collection", "upc", "super premium collection", "spc", "premium collection"]),
    ("poster_collection", ["poster collection", "poster box", "zestaw z plakatem", "pudełko z plakatem"]),
    ("binder_collection", ["binder collection", "binder box", "zestaw z albumem"]),
    ("3pack_blister", ["3-pack blister", "3 pack blister", "3pack blister", "triple blister", "3 boostery", "3 paczki", "trójpak"]),
    ("checklane_blister", ["checklane blister", "1-pack blister", "1 pack blister", "blister"]),
    ("sleeved_booster", ["sleeved booster", "sleeved pack", "booster w kartoniku", "w kartoniku"]),
    ("mini_tin", ["mini tin", "minitin", "mała puszka", "mala puszka"]),
    ("tin", ["tin", "puszka", "metalowe pudełko", "metalowe pudelko"]),
    ("collection_box", ["collection box", "ex box", "v box", "vmax box", "vstar box", "tech sticker", "zestaw kolekcjonerski"]),
    ("booster_pack", ["booster pack", "booster", "saszetka", "saszetki", "paczka", "paczki", "paczuszka", "10 kart"]),
]

MARKET_PRICES_PLN = {
    "ascended_heroes__booster_pack": 35.0, "ascended_heroes__booster_bundle": 210.0, "ascended_heroes__etb": 360.0,
    "30th_celebration_classic__booster_pack": 70.0,
    "prismatic_evolutions__booster_pack": 48.0, "prismatic_evolutions__booster_bundle": 270.0, "prismatic_evolutions__etb": 460.0,
    "prismatic_evolutions__poster_collection": 180.0, "prismatic_evolutions__binder_collection": 260.0, "prismatic_evolutions__mini_tin": 95.0,
    "mega_evolution_base__booster_pack": 30.0, "mega_evolution_base__booster_bundle": 180.0, "mega_evolution_base__etb": 310.0,
    "black_bolt__booster_pack": 32.0, "black_bolt__booster_bundle": 185.0, "black_bolt__etb": 320.0,
    "white_flare__booster_pack": 32.0, "white_flare__booster_bundle": 185.0, "white_flare__etb": 320.0,
    "sv_151__booster_pack": 58.0, "sv_151__booster_bundle": 330.0, "sv_151__etb": 580.0,
    "sv_151__poster_collection": 210.0, "sv_151__binder_collection": 290.0, "sv_151__mini_tin": 105.0,
    "crown_zenith__booster_pack": 40.0, "crown_zenith__booster_bundle": 240.0, "crown_zenith__etb": 420.0, "crown_zenith__mini_tin": 85.0,
    "evolving_skies__booster_pack": 95.0, "evolving_skies__sleeved_booster": 110.0, "evolving_skies__3pack_blister": 290.0,
    "chilling_reign__booster_pack": 38.0, "chilling_reign__etb": 370.0,
    "fusion_strike__booster_pack": 42.0, "fusion_strike__etb": 390.0,
    "cosmic_eclipse__booster_pack": 115.0, "hidden_fates__booster_pack": 135.0, "hidden_fates__tin": 430.0,
    "unified_minds__booster_pack": 105.0, "unbroken_bonds__booster_pack": 115.0, "team_up__booster_pack": 290.0,
    "lost_thunder__booster_pack": 90.0, "ultra_prism__booster_pack": 105.0, "celestial_storm__booster_pack": 95.0,
    "ancient_origins__booster_pack": 155.0, "primal_clash__booster_pack": 115.0, "roaring_skies__booster_pack": 145.0,
    "breakthrough__booster_pack": 95.0, "phantom_forces__booster_pack": 230.0, "flashfire__booster_pack": 310.0,
    "legendary_treasures__booster_pack": 330.0, "plasma_blast__booster_pack": 290.0, "plasma_freeze__booster_pack": 380.0,
    "plasma_storm__booster_pack": 420.0, "dragons_exalted__booster_pack": 320.0, "dark_explorers__booster_pack": 370.0,
    "boundaries_crossed__booster_pack": 290.0, "call_of_legends__booster_pack": 550.0,
    "undaunted__booster_pack": 430.0, "triumphant__booster_pack": 490.0, "rising_rivals__booster_pack": 450.0, "supreme_victors__booster_pack": 520.0,
}

POLISH_STORES = [
    ("Rebel.pl", "https://www.rebel.pl/szukaj?phrase={q}"),
    ("Planszostrefa", "https://planszostrefa.pl/pl/searchquery/{q}/1/phot/5"),
    ("Adeptus", "https://adeptus.pl/pl/searchquery/{q}/1/phot/5"),
    ("PokeStop", "https://pokestop.pl/?s={q}&post_type=product"),
    ("CardShop", "https://cardshop.pl/?s={q}&post_type=product"),
    ("TCGShop", "https://tcgshop.pl/?s={q}&post_type=product"),
    ("PokeShop", "https://pokeshop.pl/?s={q}&post_type=product"),
    ("GrailPoint", "https://grailpoint.com/?s={q}&post_type=product"),
    ("LootQuest", "https://lootquest.pl/?s={q}&post_type=product"),
    ("KawaiiShop", "https://kawaiishop.pl/pl/searchquery/{q}/1/phot/5"),
    ("GeekUP", "https://geekup.pl/?s={q}&post_type=product"),
    ("Mroczny Rycerz", "https://mrocznyrycerz.pl/pl/searchquery/{q}/1/phot/5"),
    ("ManaLeak", "https://manaleak.pl/?s={q}&post_type=product"),
    ("SunTCG", "https://suntcg.pl/?s={q}&post_type=product"),
    ("PokeKarty", "https://pokekarty.pl/?s={q}&post_type=product"),
    ("KolekcjonerzyKart", "https://kolekcjonerzykart.pl/?s={q}&post_type=product"),
    ("StrefaMTG", "https://strefamtg.pl/pl/searchquery/{q}/1/phot/5"),
    ("Baszta", "https://baszta.shop/pl/searchquery/{q}/1/phot/5"),
    ("Fliper", "https://fliper.pl/?s={q}&post_type=product"),
    ("X-Games", "https://x-games.com.pl/pl/searchquery/{q}/1/phot/5"),
    ("Alchemik", "https://sklep.alchemik.pl/pl/searchquery/{q}/1/phot/5"),
    ("SklepTCG", "https://skleptcg.pl/?s={q}&post_type=product"),
    ("3Trolle", "https://3trolle.pl/szukaj?controller=search&s={q}"),
    ("KartyKolekcjonerskie", "https://kartykolekcjonerskie.pl/?s={q}&post_type=product"),
    ("PokeBox", "https://pokebox.pl/?s={q}&post_type=product"),
]

SEARCH_QUERIES = [
    "pokemon", "karty pokemon", "pokemon booster", "pokemon etb", "pokemon bundle", "pokemon box",
    "paczki pokemon", "saszetki pokemon", "zestaw pokemon", "puszka pokemon",
    "pokemon 151", "prismatic", "evolving skies", "crown zenith", "team up",
    "hidden fates", "cosmic eclipse", "fusion strike", "chilling reign",
    "ascended heroes", "30th celebration", "mega evolution", "black bolt", "white flare"
]


def norm(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return " " + cleaned + " "


def evaluate_offer(title: str, desc: str, price: float):
    if price <= 0 or price > MAX_BUDGET_PLN:
        return None
    full_norm = norm(title + " " + desc)

    if any(b in full_norm for b in NON_ENGLISH_BLACKLIST):
        return None
    if any(j in full_norm for j in FAKE_JUNK_BLACKLIST):
        return None

    matched_set_id, matched_set = None, None
    for sid, sdata in TARGET_SETS.items():
        if any(kw in full_norm for kw in sdata["keywords"]):
            if "required_all" in sdata and not all(r in full_norm for r in sdata["required_all"]):
                continue
            matched_set_id, matched_set = sid, sdata
            break
    if not matched_set_id:
        return None

    prod_type = None
    for ptype, pkws in SEALED_PRODUCT_TYPES:
        if any(p in full_norm for p in pkws):
            prod_type = ptype
            break
    if not prod_type:
        return None

    if "allowed_types" in matched_set and prod_type not in matched_set["allowed_types"]:
        return None

    sku = matched_set_id + "__" + prod_type
    market_price = MARKET_PRICES_PLN.get(sku)
    if not market_price:
        return None
    if price < market_price * MIN_PRICE_RATIO:
        return None

    discount = round(market_price - price, 2)
    if discount < MIN_DISCOUNT_PLN:
        return None

    return {
        "set_name": matched_set["name"],
        "product_type": prod_type.replace("_", " ").upper(),
        "price": round(price, 2),
        "market_price": market_price,
        "discount": discount,
        "discount_pct": round((discount / market_price) * 100, 1),
    }


async def scrape_olx(pages: int = 1):
    out = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "pl-PL,pl;q=0.9",
    }
    async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
        for q in SEARCH_QUERIES:
            for p in range(pages):
                try:
                    r = await client.get("https://www.olx.pl/api/v1/offers/", params={
                        "offset": p * 40, "limit": 40, "query": q, "sort_by": "created_at:desc", "filter_float_price:to": int(MAX_BUDGET_PLN)
                    })
                    if r.status_code != 200:
                        continue
                    for item in r.json().get("data", []):
                        price = next((float(pr["value"]["value"]) for pr in item.get("params", []) if pr.get("key") == "price"), 0.0)
                        photos = item.get("photos", [])
                        img = photos[0].get("link", "").replace("{width}", "600").replace("{height}", "600") if photos else ""
                        if price > 0:
                            out.append({"id": "olx_" + str(item["id"]), "source": "OLX", "title": item.get("title", ""), "desc": item.get("description", ""), "price": price, "url": item.get("url", ""), "image": img})
                    await asyncio.sleep(random.uniform(0.7, 1.3))
                except Exception:
                    pass
    return out


async def scrape_vinted(pages: int = 1):
    out = []
    async with AsyncSession(impersonate="chrome124") as session:
        try:
            await session.get("https://www.vinted.pl/catalog?search_text=pokemon", timeout=15)
            await asyncio.sleep(1.5)
        except Exception:
            return []
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "pl-PL,pl;q=0.9",
            "Referer": "https://www.vinted.pl/catalog",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        for q in SEARCH_QUERIES:
            for p in range(1, pages + 1):
                try:
                    r = await session.get("https://www.vinted.pl/api/v2/catalog/items", params={
                        "search_text": q, "order": "newest_first", "price_to": int(MAX_BUDGET_PLN), "currency": "PLN", "per_page": 40, "page": p
                    }, headers=headers, timeout=15)
                    if r.status_code != 200:
                        continue
                    for item in r.json().get("items", []):
                        p_obj = item.get("price", {})
                        price = float(p_obj.get("amount", 0)) if isinstance(p_obj, dict) else float(item.get("price_numeric", 0) or 0)
                        url = item.get("url", "")
                        if url and not url.startswith("http"):
                            url = "https://www.vinted.pl" + url
                        photo = item.get("photo", {})
                        img = photo.get("url", "") if isinstance(photo, dict) else ""
                        if price > 0:
                            out.append({"id": "vinted_" + str(item["id"]), "source": "Vinted", "title": item.get("title", ""), "desc": "", "price": price, "url": url, "image": img})
                    await asyncio.sleep(random.uniform(1.0, 1.8))
                except Exception:
                    pass
    return out


async def scrape_stores():
    out = []
    store_qs = ["pokemon 151", "prismatic", "crown zenith", "evolving skies", "chilling reign", "fusion strike", "ascended heroes", "30th celebration", "mega evolution", "black bolt", "white flare", "team up", "hidden fates", "cosmic eclipse", "booster pokemon"]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
    async with httpx.AsyncClient(headers=headers, timeout=12.0, follow_redirects=True) as client:
        for sname, surl in POLISH_STORES:
            for q in store_qs:
                try:
                    url = surl.format(q=urllib.parse.quote_plus(q))
                    r = await client.get(url)
                    if r.status_code != 200:
                        continue
                    soup = BeautifulSoup(r.text, "lxml")
                    for card in soup.select("li.product, div.product-inner-wrap, div.product, article.product-miniature, div.product-tile")[:15]:
                        txt = card.get_text(" ", strip=True).lower()
                        if any(w in txt for w in ["brak w magazynie", "wyprzedane", "niedostępny", "brak towaru", "out of stock"]):
                            continue
                        a = card.select_one("a.woocommerce-LoopProduct-link, a.prodname, h2 a, h3 a, a.product-name, a")
                        ptag = card.select_one("ins .woocommerce-Price-amount, .woocommerce-Price-amount, .price em, .price, .product-price")
                        if not a or not ptag:
                            continue
                        cleaned = re.sub(r"[^0-9,.]", "", ptag.get_text()).replace(",", ".")
                        if cleaned.count(".") > 1:
                            parts = cleaned.split(".")
                            cleaned = "".join(parts[:-1]) + "." + parts[-1]
                        price = float(cleaned) if cleaned else 0.0
                        href = a.get("href", "")
                        if href and not href.startswith("http"):
                            href = "/".join(url.split("/")[:3]) + "/" + href.lstrip("/")
                        img_tag = card.select_one("img")
                        img = (img_tag.get("data-src") or img_tag.get("src") or "") if img_tag else ""
                        if 0 < price <= MAX_BUDGET_PLN and href:
                            out.append({"id": "store_" + sname + "_" + str(hash(href)), "source": sname, "title": (a.get("title") or a.get_text(" ", strip=True)).strip(), "desc": "", "price": price, "url": href, "image": img})
                except Exception:
                    pass
    return out


async def send_telegram_text(text: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post("https://api.telegram.org/bot" + token + "/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
        return r.status_code == 200


async def send_telegram(offer, deal):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    msg = (
        "<b>OKAZJA POKEMON TCG (" + str(offer["source"]) + ")</b>\n\n"
        "<b>Set:</b> " + str(deal["set_name"]) + "\n"
        "<b>Produkt:</b> " + str(deal["product_type"]) + "\n"
        "<b>Ogloszenie:</b> " + str(offer["title"]) + "\n\n"
        "<b>Cena oferty:</b> <b>" + f"{deal['price']:.2f}" + " zl</b>\n"
        "<b>Cena rynkowa PL:</b> ~" + f"{deal['market_price']:.2f}" + " zl\n"
        "<b>Taniej o:</b> <b>-" + f"{deal['discount']:.2f}" + " zl (-" + str(deal["discount_pct"]) + "%)</b>\n\n"
        "<a href=\"" + str(offer["url"]) + "\">OTWORZ OFERTE TERAZ</a>"
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        if offer.get("image"):
            r = await client.post("https://api.telegram.org/bot" + token + "/sendPhoto", json={"chat_id": chat_id, "photo": offer["image"], "caption": msg, "parse_mode": "HTML"})
            if r.status_code == 200:
                return True
        r = await client.post("https://api.telegram.org/bot" + token + "/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})
        return r.status_code == 200


async def main():
    seen = set(json.load(open(SEEN_FILE, "r", encoding="utf-8"))) if os.path.exists(SEEN_FILE) else set()
    first_run = len(seen) == 0
    pages = 5 if first_run else 1

    olx_items, vinted_items, store_items = await asyncio.gather(scrape_olx(pages), scrape_vinted(pages), scrape_stores())
    all_offers = olx_items + vinted_items + store_items

    sent_count = 0
    for off in all_offers:
        oid = str(off["id"])
        raw_sig = str(off["source"]) + "|" + str(off["title"]).lower() + "|" + str(off["price"])
        ohash = "h_" + hashlib.md5(raw_sig.encode()).hexdigest()
        if oid in seen or ohash in seen:
            continue
        seen.add(oid)
        seen.add(ohash)

        deal = evaluate_offer(off["title"], off["desc"], off["price"])
        if deal:
            if await send_telegram(off, deal):
                sent_count += 1
                await asyncio.sleep(0.5)

    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-50000:], f)

    if first_run:
        raport = (
            "<b>RAPORT PIERWSZEGO SKANU (DEEP SCAN)</b>\n\n"
            "OLX pobrano: <b>" + str(len(olx_items)) + "</b> ofert\n"
            "Vinted pobrano: <b>" + str(len(vinted_items)) + "</b> ofert\n"
            "Sklepy PL pobrano: <b>" + str(len(store_items)) + "</b> ofert\n"
            "Wyslano okazji: <b>" + str(sent_count) + "</b>"
        )
        await send_telegram_text(raport)


if __name__ == "__main__":
    asyncio.run(main()) 
