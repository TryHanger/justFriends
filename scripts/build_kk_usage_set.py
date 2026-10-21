"""Kazakh literal/metaphorical usage set from the 15-volume explanatory dictionary.

«Қазақ әдеби тілінің сөздігі» (Institute of Linguistics, 2011; published on sozdikqor.kz)
marks figurative senses with «ауыс.» and illustrates every sense with quotations from
literature, the headword in bold. A quotation under an «ауыс.» sense is an expert
judgement that the word is used figuratively there; a quotation under a direct sense is
a literal use. This gives module C (usage_type) test data without our own annotators.

The dictionary is copyrighted: the set is for research evaluation only and stays out of
git (data/raw, data/processed). Pages are cached, requests are spaced by --delay seconds.

    python -m scripts.build_kk_usage_set
"""

import argparse
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from app.nlp.lexicon import Lexicon

SITE = "https://sozdikqor.kz"
DICTIONARY = "Қазақ әдеби тілінің сөздігі. Он бес томдық"
CACHE = Path("data/raw/sozdikqor")
OUTPUT = Path("data/processed/kk_usage/kk_usage_dictionary.jsonl")
# Typical image words of Kazakh poetry, on top of the project lexicon and ensemble images.
SEED_WORDS = """
жалын шоқ мұз тас темір алтын күміс гауһар інжу маржан айна шам нұр сәуле көлеңке
түн таң жарық қараңғы бал у ащы тәтті жылы суық ыстық бұлақ толқын дауыл жаңбыр
жапырақ тамыр жеміс дән бұтақ қанат ұя ит есек шошқа жолбарыс көбелек жол соқпақ
көпір есік кілт қамал қорған сауыт қылыш найза оқ жебе жара дерт ем соқыр саңырау
бауыр көз тіл қол бас қан сүйек көкірек тұман шың құз жартас шөл кірпіш базар
күзетші жендет керуен майдан қорғаныш шырақ түнек сел көл мұхит жер аспан
""".split()


def get(url: str, delay: float) -> str:
    key = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:20] + ".html")
    if key.exists():
        return key.read_text(encoding="utf-8")
    time.sleep(delay)
    request = urllib.request.Request(url, headers={"User-Agent": "justFriends-research/0.1"})
    text = urllib.request.urlopen(request, timeout=60).read().decode("utf-8", "replace")
    key.write_text(text, encoding="utf-8")
    return text


def entries_for(word: str, delay: float) -> list[str]:
    """Entry URLs whose headword is exactly the word. The source title is not always shown
    in search results, so entries are kept by shape instead: only senses illustrated by
    quotations with a "(volume,page)" citation, the style of the 15-volume dictionary,
    produce records."""
    page = get(f"{SITE}/search?q={urllib.parse.quote(word)}", delay)
    urls = []
    for item in re.findall(r"<li>(.*?)</li>", page, re.S):
        # Slugs use the new Kazakh Latin script with diacritics: a=Júrek, a=QYRAN1.
        link = re.search(r'href="(/soz\?id=\d+&(?:amp;)?a=[^"]+)">([^<]+)</a>', item)
        if not link:
            continue
        headword = re.sub(r"\d+$", "", link.group(2).strip()).lower()
        if headword == word.lower():
            urls.append(SITE + urllib.parse.quote(html.unescape(link.group(1)), safe="/?=&"))
    return urls


def entry_text(page: str) -> str:
    """Entry body with bold headword occurrences as ⟦…⟧ and italic labels as ‹…›."""
    page = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    # Spaces around bold: the source often glues the bold word to its neighbours.
    page = page.replace("<b>", " ⟦").replace("</b>", "⟧ ").replace("<i>", "‹").replace("</i>", "›")
    page = re.sub(r"</p>|<br\s*/?>", "\n", page)
    page = re.sub(r"<(?:div|h\d|li)[^>]*>", "\n", page)
    text = html.unescape(re.sub(r"<[^>]+>", "", page))
    text = re.sub(r" +([,.;:!?])", r"\1", re.sub(r"[ \t]+", " ", text))
    start = re.search(r"lat: \S+\n", text)
    if not start:
        return ""
    end = text.find("Telegram мессенджерін")
    return text[start.end() : end if end > 0 else None].strip()


# Two layouts. Older volumes: "‹ауыс›." and citations "(4,144)". Newer volumes:
# "ауыспалы мағына." in plain text, citations "(М.Дүзенов, Ақәже)" or "(ҚҰЭ)", and the
# headword letter-spaced in bold: "⟦ж ү р е к⟧". Some put the whole sense header in
# italics: "‹2. ауыспалы мағына. Мейірлену, көңілі түсу.›".
KK_UPPER = "А-ЯЁӘҒҚҢӨҰҮҺІA-Z"
KK_LOWER = "а-яёәғқңөұүһі"
CITATION = re.compile(rf"\(\s*(?:\d+\s*,\s*[\d ]+|[{KK_UPPER}][^()]{{0,80}})\)\s*\.?")
SENSE = re.compile(rf"(?:^|(?<=[\s.)‹]))(\d{{1,2}})\s?\.\s+(?=[‹<{KK_UPPER}{KK_LOWER}])")
LABELS = re.compile(rf"^\s*(?:(?:‹[^›]*›|ауыспалы мағына|[{KK_LOWER}]{{2,12}})\s?\.\s*)*")
FIGURATIVE = re.compile(r"‹\s*ауыс|(?:^|\s)ауыс\s?\.|ауыспалы мағына")
BOLD = re.compile(r"⟦([^⟧]+)⟧")


def unspace(match: re.Match) -> str:
    tokens = match.group(1).split()
    if tokens and sum(len(t) == 1 for t in tokens) * 2 >= len(tokens):
        return "⟦" + "".join(tokens) + "⟧"
    return "⟦" + " ".join(tokens) + "⟧"


def quotations(sense: str) -> tuple[str, list[tuple[str, str]]]:
    """(definition, [(quotation with ⟦⟧, citation)]) of one sense, labels removed."""
    sense = LABELS.sub("", sense)
    pieces = CITATION.split(sense)
    citations = CITATION.findall(sense)
    if not citations:
        return sense.strip(), []
    # The definition ends at the first full stop of the text before the first citation.
    stop = re.search(r"\s?\.›?(?:\s|$)|›", pieces[0])
    split = stop.end() if stop else 0
    definition, rest = pieces[0][:split], pieces[0][split:]
    quotes = [(rest, citations[0])] + list(zip(pieces[1:], citations[1:], strict=False))
    return definition.strip(" .‹›"), [
        (q.strip(" ‹›"), c.strip(" .")) for q, c in quotes if "⟦" in q
    ]


def records_for(word: str, url: str, body: str) -> list[dict]:
    # Phraseological units after ◊ or ♦ are idioms, not senses of the word itself.
    body = BOLD.sub(unspace, re.split(r"[◊♦]", body)[0])
    parts = SENSE.split(body)
    senses = (
        [("1", parts[0])] if len(parts) == 1 else list(zip(parts[1::2], parts[2::2], strict=True))
    )
    records = []
    for number, sense in senses:
        head = LABELS.match(sense)
        figurative = bool(head and FIGURATIVE.search(head.group(0)))
        definition, quotes = quotations(sense)
        for quote, citation in quotes:
            text = re.sub(r"\s*\n\s*", "\n", quote).strip()
            target = re.search(r"⟦\s*([^⟧]+?)\s*⟧", text)
            if not target or " " in target.group(1):
                continue  # a multiword bold phrase is an idiom, not the headword alone
            clean = re.sub(r"⟦\s*([^⟧]+?)\s*⟧", r"\1", text)
            word_start = len(re.sub(r"⟦\s*([^⟧]+?)\s*⟧", r"\1", text[: target.start()]))
            # Punctuation is sometimes set in bold with the word: "⟦шам,⟧".
            form = target.group(1).rstrip(",.;:!?–—-")
            records.append(
                {
                    "id": "kkdict-" + hashlib.sha256(f"{word}\n{clean}".encode()).hexdigest()[:12],
                    "headword": word,
                    "entry_url": url,
                    "sense": int(number),
                    "definition": definition,
                    "usage_type": "metaphorical" if figurative else "literal",
                    "text": clean,
                    "target": form,
                    "start": word_start,
                    "end": word_start + len(form),
                    "citation": citation,
                    "source": f"{DICTIONARY} (Алматы, 2011), via sozdikqor.kz",
                }
            )
    return records


def ensemble_words() -> set[str]:
    words = set()
    for path in Path("data/processed/kk_ensemble").glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            for span in json.loads(line).get("spans", []):
                if " " not in span["text"].strip():
                    words.add(span["text"].strip().lower())
    return words


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    words = sorted(
        {e["term"] for e in Lexicon.load("kk").entries} | set(SEED_WORDS) | ensemble_words()
    )
    records, seen, missing = [], set(), []
    for i, word in enumerate(words):
        urls = entries_for(word, args.delay)
        if not urls:
            missing.append(word)
        for url in urls:
            for record in records_for(word, url, entry_text(get(url, args.delay))):
                if record["id"] not in seen:
                    seen.add(record["id"])
                    records.append(record)
        if i % 25 == 0:
            print(f"{i}/{len(words)} words, {len(records)} quotations", flush=True)
    with OUTPUT.open("w", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    report = {
        "words": len(words),
        "words_without_entry": missing,
        "quotations": len(records),
        "usage_type": Counter(r["usage_type"] for r in records),
        "headwords_with_figurative": len(
            {r["headword"] for r in records if r["usage_type"] == "metaphorical"}
        ),
    }
    OUTPUT.with_name("build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "words_without_entry"}, ensure_ascii=False
        ),
        "without entry:",
        len(missing),
    )


if __name__ == "__main__":
    main()
