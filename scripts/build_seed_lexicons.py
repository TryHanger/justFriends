"""Regenerate the seed soft lexicons: python -m scripts.build_seed_lexicons.

The entries are a starting point for module B (candidate extraction). Meanings are
conventional symbolic readings to help recall and RAG; they are not decisions that a
given occurrence is metaphorical. Experts extend and correct data/lexicons/*.json.
"""

from pathlib import Path

from app.nlp.corpus import save_json

ROOT = Path(__file__).resolve().parents[1]


def e(
    term,
    entity_type,
    meanings,
    sentiment="neutral",
    source="",
    forms=None,
    variants=None,
    note=None,
):
    entry = {"term": term, "entity_type": entity_type, "meanings": meanings, "sentiment": sentiment}
    if source:
        entry["source_domain"] = source
    if forms:
        entry["forms"] = forms
    if variants:
        entry["variants"] = variants
    if note:
        entry["note"] = note
    return entry


ZH = [
    # Plants: the fragrant-herb tradition of Chu Ci and later lyric poetry.
    e(
        "兰",
        "plant",
        ["благородный муж", "добродетель"],
        "positive",
        "plant",
        variants=["蘭", "兰草", "蘭草"],
    ),
    e("蕙", "plant", ["добродетель", "благоухание души"], "positive", "plant"),
    e("芷", "plant", ["чистота помыслов"], "positive", "plant"),
    e("江离", "plant", ["добродетель"], "positive", "plant", variants=["江離"]),
    e("薜荔", "plant", ["добродетель"], "positive", "plant"),
    e("椒", "plant", ["благоухание", "достоинство"], "positive", "plant"),
    e("萧艾", "plant", ["недостойные люди"], "negative", "plant", variants=["蕭艾"]),
    e("菊", "plant", ["отшельничество", "стойкость"], "positive", "plant"),
    e("梅", "plant", ["стойкость", "чистота"], "positive", "plant"),
    e("竹", "plant", ["прямота", "стойкость"], "positive", "plant"),
    e("松", "plant", ["стойкость", "долголетие"], "positive", "plant"),
    e("柳", "plant", ["разлука", "прощание"], "negative", "plant"),
    e("莲", "plant", ["чистота среди скверны"], "positive", "plant", variants=["蓮", "荷"]),
    e("桃花", "plant", ["красота", "весна"], "positive", "plant"),
    e("落花", "plant", ["увядание", "утрата"], "negative", "plant"),
    e("浮萍", "plant", ["скитания"], "negative", "plant"),
    e("飞蓬", "plant", ["скиталец"], "negative", "plant", variants=["飛蓬"]),
    e("桂", "plant", ["благородство"], "positive", "plant"),
    # Animals.
    e("狐", "animal", ["хитрость", "коварство"], "negative", "animal"),
    e("鹤", "animal", ["долголетие", "отшельник"], "positive", "animal", variants=["鶴"]),
    e("雁", "animal", ["весть", "тоска по дому"], "negative", "animal", variants=["鸿雁", "鴻雁"]),
    e("鸳鸯", "animal", ["супружеская любовь"], "positive", "animal", variants=["鴛鴦"]),
    e(
        "杜鹃",
        "animal",
        ["скорбь", "тоска по родине"],
        "negative",
        "animal",
        variants=["杜鵑", "子规", "子規"],
    ),
    e("猿", "animal", ["печаль"], "negative", "animal", variants=["猨"]),
    e(
        "凤",
        "animal",
        ["благородный муж", "мудрец"],
        "positive",
        "animal",
        variants=["鳳", "凤凰", "鳳凰"],
    ),
    e("龙", "animal", ["государь", "сила"], "positive", "animal", variants=["龍"]),
    e("鸷鸟", "animal", ["несгибаемость"], "positive", "animal", variants=["鷙鳥"]),
    e("鸩", "animal", ["клеветник"], "negative", "animal", variants=["鴆"]),
    e("马", "animal", ["талант", "странствие"], "neutral", "animal", variants=["馬"]),
    e("蝉", "animal", ["чистота", "бренность"], "neutral", "animal", variants=["蟬"]),
    e(
        "乌鸦",
        "animal",
        ["дурное предзнаменование", "запустение"],
        "negative",
        "animal",
        variants=["烏鴉"],
    ),
    # Natural phenomena, celestial bodies, landscape.
    e("明月", "celestial", ["тоска по дому", "разлука"], "neutral", "light"),
    e("月", "celestial", ["тоска по дому", "разлука"], "neutral", "light"),
    e(
        "夕阳",
        "celestial",
        ["старость", "закат жизни"],
        "negative",
        "light",
        variants=["夕陽", "斜阳", "斜陽"],
    ),
    e(
        "浮云",
        "natural_phenomenon",
        ["скитания", "препятствие"],
        "negative",
        "nature",
        variants=["浮雲"],
    ),
    e("云", "natural_phenomenon", ["скитания"], "neutral", "nature", variants=["雲"]),
    e("风", "natural_phenomenon", ["перемены", "влияние"], "neutral", "nature", variants=["風"]),
    e("雨", "natural_phenomenon", ["печаль"], "negative", "water"),
    e("雪", "natural_phenomenon", ["чистота"], "positive", "nature"),
    e("霜", "natural_phenomenon", ["старость", "седина"], "negative", "nature"),
    e("露", "natural_phenomenon", ["бренность"], "negative", "water"),
    e("流水", "landscape", ["течение времени"], "neutral", "water"),
    e("江", "landscape", ["время", "печаль"], "neutral", "water"),
    e("山", "landscape", ["незыблемость"], "neutral", "space"),
    e("春", "natural_phenomenon", ["молодость", "надежда"], "positive", "time"),
    e("秋", "natural_phenomenon", ["печаль", "увядание"], "negative", "time"),
    # Abstract concepts.
    e("心", "abstract", ["душа", "чувства"], "neutral", "body"),
    e("愁", "abstract", ["тоска"], "negative", "emotion"),
    e("梦", "abstract", ["иллюзия", "мечта"], "neutral", "mind", variants=["夢"]),
]

KK = [
    # Animals.
    e("арыстан", "animal", ["мужество", "сила"], "positive", "animal"),
    e("бөрі", "animal", ["свобода", "сила рода"], "positive", "animal"),
    e("қасқыр", "animal", ["свобода", "хищность"], "neutral", "animal"),
    e("тұлпар", "animal", ["герой", "благородство"], "positive", "animal"),
    e("арғымақ", "animal", ["благородство"], "positive", "animal"),
    e("сұңқар", "animal", ["батыр", "свобода"], "positive", "animal"),
    e("қыран", "animal", ["герой", "зоркость"], "positive", "animal"),
    e("бүркіт", "animal", ["сила", "высота духа"], "positive", "animal"),
    e("аққу", "animal", ["красота", "чистота", "верность"], "positive", "animal"),
    e("қарлығаш", "animal", ["весна", "вестник"], "positive", "animal"),
    e("бұлбұл", "animal", ["поэт", "красноречие"], "positive", "animal"),
    e("түлкі", "animal", ["хитрость"], "negative", "animal"),
    e("жылан", "animal", ["коварство"], "negative", "animal"),
    e("құлан", "animal", ["свобода", "степь"], "positive", "animal"),
    e(
        "қой",
        "animal",
        ["кротость", "покорность"],
        "neutral",
        "animal",
        forms=["қой", "қойдай", "қойлар", "қойы"],
        note="омоним: повелительное «положи»",
    ),
    e(
        "ат",
        "animal",
        ["верный спутник"],
        "neutral",
        "animal",
        forms=["ат", "атым", "аты", "атқа", "аттың", "атпен"],
        note="омоним: «имя», «стреляй»",
    ),
    # Plants.
    e("бәйтерек", "plant", ["род", "опора народа"], "positive", "plant"),
    e("терек", "plant", ["стойкость", "опора"], "positive", "plant"),
    e("жусан", "plant", ["родина", "тоска по родине"], "positive", "plant"),
    e(
        "гүл",
        "plant",
        ["красота", "юность"],
        "positive",
        "plant",
        forms=["гүл", "гүлі", "гүлдер", "гүлдей", "гүлге", "гүлдің", "гүлім"],
    ),
    e("раушан", "plant", ["красота", "любовь"], "positive", "plant"),
    e("бәйшешек", "plant", ["весна", "юность"], "positive", "plant"),
    e("қамыс", "plant", ["хрупкость"], "neutral", "plant"),
    e(
        "тал",
        "plant",
        ["гибкость", "юность"],
        "neutral",
        "plant",
        forms=["тал", "талдай", "талы", "талдар"],
        note="омоним: «утомись»",
    ),
    # Celestial, natural phenomena, landscape.
    e(
        "ай",
        "celestial",
        ["красавица", "свет"],
        "positive",
        "light",
        forms=["ай", "айым", "айдай", "айға", "айдың", "айы", "айдан"],
        note="также «месяц»; основа не сопоставляется с айт-",
    ),
    e(
        "күн",
        "celestial",
        ["жизнь", "свет", "радость"],
        "positive",
        "light",
        forms=["күн", "күні", "күндей", "күнге", "күннің", "күнім"],
        note="также «день»",
    ),
    e("жұлдыз", "celestial", ["судьба", "надежда"], "positive", "light"),
    e(
        "жел",
        "natural_phenomenon",
        ["перемены", "молва"],
        "neutral",
        "nature",
        forms=["жел", "желі", "желдей", "желге", "желдің"],
    ),
    e("бұлт", "natural_phenomenon", ["печаль", "препятствие"], "negative", "nature"),
    e("боран", "natural_phenomenon", ["бедствие", "смута"], "negative", "nature"),
    e(
        "қар",
        "natural_phenomenon",
        ["чистота", "старость"],
        "neutral",
        "nature",
        forms=["қар", "қары", "қардай"],
    ),
    e("өзен", "landscape", ["течение жизни", "время"], "neutral", "water"),
    e("теңіз", "landscape", ["безбрежность чувств", "мудрость"], "neutral", "water"),
    e(
        "тау",
        "landscape",
        ["величие", "незыблемость"],
        "positive",
        "space",
        forms=["тау", "тауы", "таудай", "тауға", "таудың", "таулар"],
    ),
    e("дала", "landscape", ["родина", "простор", "свобода"], "positive", "space"),
    e(
        "от",
        "natural_phenomenon",
        ["страсть", "очаг рода"],
        "neutral",
        "fire",
        forms=["от", "оты", "оттай", "отқа", "оттың"],
    ),
    e(
        "су",
        "natural_phenomenon",
        ["жизнь", "очищение"],
        "neutral",
        "water",
        forms=["су", "суы", "судай", "суға", "судың"],
    ),
    # Body and abstract concepts.
    e("жүрек", "body", ["чувства", "мужество"], "neutral", "body"),
    e("көңіл", "abstract", ["душа", "настроение"], "neutral", "emotion"),
    e(
        "жан",
        "abstract",
        ["душа", "жизнь"],
        "neutral",
        "life",
        forms=["жан", "жаным", "жаны", "жанға", "жанның"],
        note="омоним: «бок», «рядом»",
    ),
    e("өмір", "abstract", ["жизнь"], "neutral", "life"),
    e("ғылым", "abstract", ["знание"], "positive", "mind"),
    e("ақыл", "abstract", ["разум"], "positive", "mind"),
    e("уақыт", "abstract", ["время"], "neutral", "time"),
]


def main():
    for language, entries in (("zh", ZH), ("kk", KK)):
        save_json(
            ROOT / "data/lexicons" / f"{language}.json",
            {
                "version": "0.1",
                "language": language,
                "status": (
                    "seed: стартовый словарь, требует проверки филологами; значения — "
                    "традиционные символические прочтения, а не решение о метафоричности"
                ),
                "matching": (
                    "zh: подстрока, длиннейшее совпадение; kk: словоформа, начинающаяся с "
                    "основы (от 4 букв, с чередованием к/г, қ/ғ, п/б) или из списка forms"
                ),
                "entries": entries,
            },
        )


if __name__ == "__main__":
    main()
