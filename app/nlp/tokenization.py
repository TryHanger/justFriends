"""Tokenizer fertility and a Kazakh BPE tokenizer (ТЗ п. 2.2.3, модуль A, гипотеза H2).

Fertility = subword tokens per word. For Kazakh a word is a whitespace/punctuation-delimited
word form with all affixes; for Chinese the unit is one Han character, since Chinese has no
word delimiters. Lower fertility means less fragmentation of agglutinative word forms.
"""

import re
import unicodedata
from collections import Counter
from pathlib import Path

_HAN = re.compile(r"[㐀-鿿\U00020000-\U0002fa1f]")
_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")


def units(text: str, language: str) -> list[str]:
    text = unicodedata.normalize("NFC", text)
    if language == "zh":
        return _HAN.findall(text)
    if language == "kk":
        return _WORD.findall(text)
    raise ValueError("language must be zh or kk")


def fertility(tokenizer, texts: list[str], language: str) -> dict:
    """Corpus-level statistics for one tokenizer; words are counted with their frequency."""
    counts = Counter(u for text in texts for u in units(text, language))
    if not counts:
        raise ValueError("No words found for fertility measurement")
    pieces = {word: len(tokenizer(word, add_special_tokens=False)["input_ids"]) for word in counts}
    words = sum(counts.values())
    tokens = sum(pieces[w] * n for w, n in counts.items())
    split = sum(n for w, n in counts.items() if pieces[w] > 1)
    running = sum(len(tokenizer(t, add_special_tokens=False)["input_ids"]) for t in texts)
    characters = sum(len(t) for t in texts)
    unk = getattr(tokenizer, "unk_token_id", None)
    unknown = 0
    if unk is not None:
        unknown = sum(
            n
            for w, n in counts.items()
            if unk in tokenizer(w, add_special_tokens=False)["input_ids"]
        )
    return {
        "language": language,
        "unit": "han_character" if language == "zh" else "word_form",
        "words": words,
        "distinct_words": len(counts),
        "fertility": tokens / words,
        "proportion_split_words": split / words,
        "running_text_tokens": running,
        "characters_per_token": characters / running if running else None,
        "unknown_word_rate": unknown / words,
        "vocab_size": getattr(tokenizer, "vocab_size", None),
    }


def compare_tokenizers(
    names: list[str], texts: list[str], language: str, loader=None
) -> list[dict]:
    if loader is None:
        from transformers import AutoTokenizer

        def loader(name):
            return AutoTokenizer.from_pretrained(name)

    rows = [{"tokenizer": name, **fertility(loader(name), texts, language)} for name in names]
    return sorted(rows, key=lambda r: r["fertility"])


def train_bpe(
    texts: list[str], output_dir: str | Path, vocab_size: int = 50000, min_frequency: int = 2
) -> dict:
    """Train a BPE tokenizer with Unicode NFC normalization and word-boundary markers."""
    from tokenizers import Tokenizer, decoders, models, normalizers, pre_tokenizers, trainers

    if vocab_size < 100:
        raise ValueError("vocab_size is too small")
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty")
    tokenizer = Tokenizer(models.BPE(unk_token="<unk>"))
    tokenizer.normalizer = normalizers.NFC()
    tokenizer.pre_tokenizer = pre_tokenizers.Metaspace()
    tokenizer.decoder = decoders.Metaspace()
    trainer = trainers.BpeTrainer(
        vocab_size=vocab_size,
        min_frequency=min_frequency,
        special_tokens=["<pad>", "<unk>", "<s>", "</s>"],
    )
    tokenizer.train_from_iterator(texts, trainer=trainer)
    output.mkdir(parents=True, exist_ok=True)
    tokenizer.save(str(output / "tokenizer.json"))
    from transformers import PreTrainedTokenizerFast

    wrapped = PreTrainedTokenizerFast(
        tokenizer_object=tokenizer,
        unk_token="<unk>",
        pad_token="<pad>",
        bos_token="<s>",
        eos_token="</s>",
    )
    wrapped.save_pretrained(output)
    return {
        "vocab_size": tokenizer.get_vocab_size(),
        "requested_vocab_size": vocab_size,
        "texts": len(texts),
        "output": str(output),
    }
