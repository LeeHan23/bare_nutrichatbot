"""Swap Bahasa Indonesia words that qwen2.5 slips into Bahasa Malaysia replies.

Deterministic, whole-word only, case-preserving. Runs on the finished answer in
rag.py, so the patient, chat history and eval all see the corrected text.

Only words that are NOT also correct Malaysian Malay are listed. Left out on
purpose (valid BM in some sense, would break good sentences): dapat, senang,
waktu, tubuh, jam, setelah, sesudah, sering, agar, kebiasaan, saja, mulai,
sementara, teratur, lemas, jeruk, resep, sodium, nutrisi, stres.
Self-check: python bm_normalise.py
"""
import re

# Indonesian -> Malaysian. Multi-word entries win over their single words.
PAIRS = {
    # health / body
    "kesehatan": "kesihatan",
    "sehat": "sihat",
    "ginjal": "buah pinggang",
    "kronis": "kronik",
    "cairan": "cecair",
    "nyeri": "sakit",
    "napas": "nafas",
    "bernapas": "bernafas",
    "pusing": "pening",
    "mual": "loya",
    "obesitas": "obesiti",
    "gizi": "pemakanan",
    "bergizi": "berkhasiat",
    "potassium": "kalium",
    # care / medication
    "obat": "ubat",
    "obat-obatan": "ubat-ubatan",
    "dokter": "doktor",
    "pasien": "pesakit",
    "perawat": "jururawat",
    "rumah sakit": "hospital",
    "diresepkan": "ditetapkan",
    "efek samping": "kesan sampingan",
    "efek": "kesan",
    "cek": "periksa",
    # activity
    "aktivitas fisik": "aktiviti fizikal",
    "aktivitas": "aktiviti",
    "fisik": "fizikal",
    "olahraga": "senaman",
    "berolahraga": "bersenam",
    "istirahat": "rehat",
    "beristirahat": "berehat",
    "berenergi": "bertenaga",
    "energi": "tenaga",
    "intensitas": "intensiti",
    "frekuensi": "kekerapan",
    "durasi": "tempoh",
    "menit": "minit",
    "rutinitas": "rutin",
    # food
    "semangka": "tembikai",
    "porsi": "bahagian",
    "sendok": "sudu",
    "piring": "pinggan",
    "asin": "masin",
    "air putih": "air kosong",
    "makan siang": "makan tengah hari",
    "pola makan": "corak pemakanan",
    "makanan olahan": "makanan diproses",
    "makanan cepat saji": "makanan segera",
    "sosis": "sosej",
    "cabai": "cili",
    "kecap": "kicap",
    "saus": "sos",
    "camilan": "snek",
    "daging sapi": "daging lembu",
    "sapi": "lembu",
    "wortel": "lobak merah",
    "pepaya": "betik",
    "alpukat": "avokado",
    # verbs
    "hindari": "elakkan",
    "menghindari": "mengelakkan",
    "dihindari": "dielakkan",
    "coba": "cuba",
    "cobalah": "cubalah",
    "mencoba": "mencuba",
    "batasi": "hadkan",
    "membatasi": "mengehadkan",
    "dibatasi": "dihadkan",
    "kurangi": "kurangkan",
    "mengurangi": "mengurangkan",
    "mengonsumsi": "mengambil",
    "dikonsumsi": "diambil",
    "konsumsi": "pengambilan",
    "asupan": "pengambilan",
    "mengandung": "mengandungi",
    "mendukung": "menyokong",
    "dukungan": "sokongan",
    "disarankan": "disyorkan",
    "menyarankan": "mencadangkan",
    "saran": "cadangan",
    "rekomendasi": "cadangan",
    "kebutuhan": "keperluan",
    "membutuhkan": "memerlukan",
    "merusak": "merosakkan",
    "terbebani": "terbeban",
    # general
    "karena": "kerana",
    "kamu": "anda",
    "untukmu": "untuk anda",
    "dirimu": "diri anda",
    "aman": "selamat",
    "bisa": "boleh",
    "rencana": "pelan",
    "silakan": "sila",
    "kondisi": "keadaan",
    "bahwa": "bahawa",
    "berlanjut": "berlarutan",
    "berkonsultasi": "berbincang",
    "mengontrol": "mengawal",
    "dikontrol": "dikawal",
    "darahmu": "darah anda",
    "tubuhmu": "badan anda",
}

# Same BM detector the prompt uses: common function words, no food names, so an
# English answer that mentions nasi lemak is left alone.
_BM_WORDS = frozenset(
    "saya aku boleh tak tidak apa apakah makan minum untuk dengan ini itu yang sihat ubat "
    "berapa macam mana nak hendak bagus kalau sebab hari ke dah sudah ada kena perlu "
    "bagaimana kenapa mengapa air sakit doktor jantung darah gula garam berhenti".split()
)


def looks_malay(text: str) -> bool:
    # ponytail: word-count heuristic, swap for a language-id model if Manglish misfires
    return len(set(re.findall(r"[a-z]+", text.lower())) & _BM_WORDS) >= 2


_EN_WORDS = frozenset(
    "i can could should what how is are the my me do does you it this that for about of "
    "with to and eat drink much many which when why will would have has any".split()
)


def looks_english(text: str) -> bool:
    # Same heuristic as looks_malay; Manglish with 2+ BM words counts as Malay.
    words = set(re.findall(r"[a-z]+", text.lower()))
    return len(words & _EN_WORDS) >= 2 and not looks_malay(text)


# Longest first so "efek samping" beats "efek". (?<![\w-]) / (?![\w-]) keep
# hyphenated words (agar-agar, ubat-ubatan) and longer words untouched.
_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(k) for k in sorted(PAIRS, key=len, reverse=True)) + r")(?![\w-])",
    re.IGNORECASE,
)


def _swap(m: re.Match) -> str:
    src = m.group(0)
    out = PAIRS[src.lower()]
    if src.isupper() and len(src) > 1:
        return out.upper()
    if src[0].isupper():
        return out[0].upper() + out[1:]
    return out


def fix(answer: str) -> str:
    """Return the answer with Indonesian words swapped, only if it reads as Malay."""
    if not answer or not looks_malay(answer):
        return answer
    return _RE.sub(_swap, answer)


if __name__ == "__main__":
    assert len(PAIRS) == 100, len(PAIRS)
    cases = {
        # Indonesian in, Malaysian out
        "Coba kurangi garam untuk kesehatan ginjal kamu.": "Cuba kurangkan garam untuk kesihatan buah pinggang anda.",
        "Ubat yang diresepkan tidak boleh dihentikan. Efek samping perlu dilaporkan.":
            "Ubat yang ditetapkan tidak boleh dihentikan. Kesan sampingan perlu dilaporkan.",
        "Hindari makanan cepat saji dan sosis yang tinggi garam untuk jantung anda.":
            "Elakkan makanan segera dan sosej yang tinggi garam untuk jantung anda.",
        "Pisang mengandung potassium yang tinggi, tidak aman untuk anda.":
            "Pisang mengandungi kalium yang tinggi, tidak selamat untuk anda.",
        # valid Malaysian Malay must come back byte-identical
        "Agar-agar boleh dimakan sedikit. Ubat-ubatan perlu diambil setiap hari.": None,
        "Ikan masin tinggi garam, jadi hadkan pengambilan. Saya rumah dekat hospital.": None,
        "Mulai esok, cuba jalan kaki selepas waktu makan, tubuh badan akan rasa segar.": None,
        "Dapatkan nasihat doktor tentang ubat anda, sakit dada perlu diperiksa.": None,
        # English answers are never touched, even with listed words in them
        "Can I eat nasi lemak? Try to avoid the sambal; kamu is not a word here.": None,
    }
    for src, want in cases.items():
        got = fix(src)
        assert got == (want or src), f"\n in:  {src}\n got: {got}\n want:{want or src}"
    for q in ["Can I eat banana?", "What about rice?", "How much water should I drink?"]:
        assert looks_english(q), q
    for q in ["Boleh saya makan pisang?", "hai", "ok thanks", "nasi lemak ok ke?", "can I makan nasi tak?"]:
        assert not looks_english(q), q
    print("bm_normalise ok:", len(PAIRS), "pairs,", len(cases), "cases")
