"""Bangladesh-only filter and tower/Edotco topic scoring, ported from NewsBot.pyw (Bangla-aware matching, trusted / blocked outlets, strictness levels)."""
import re
import unicodedata
import urllib.parse
from collections import Counter

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
BN_RANGE = "\u0980-\u09FF"


def norm(s):
    """Normalise text so Bangla/English matching is consistent."""
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("\u200c", "").replace("\u200d", "").translate(BN_DIGITS).lower()
    for ch in "-\u2013\u2014_":
        s = s.replace(ch, " ")
    return " ".join(s.split())


def has_bangla(s):
    return bool(re.search("[" + BN_RANGE + "]", s or ""))


# Bangla endings that stick to words (টাওয়ার -> টাওয়ারে, টাওয়ারের, টাওয়ারগুলো ...)
BN_SUFFIX = unicodedata.normalize("NFC", r"(?:গুলোর|গুলো|ের|কেও|কে|তে|টি|য়|র|ে|ও)?")
BN_STRIP = [unicodedata.normalize("NFC", x) for x in ("গুলোর", "গুলো", "ের", "কেও", "কে", "তে", "টি")]


def term_regex(term):
    """Whole-word matcher: 'রবি' must not match 'রবিবার'; 'tower' also matches 'towers'."""
    t = norm(term)
    words = t.split()
    if not words:
        return re.compile(r"(?!x)x")
    if has_bangla(t):
        body = r"\s+".join(re.escape(w) + BN_SUFFIX for w in words)
        return re.compile("(?<![" + BN_RANGE + "])" + body + "(?![" + BN_RANGE + "])")
    body = r"\s+".join(re.escape(w) for w in words)
    return re.compile(r"(?<![a-z0-9])" + body + r"(?:s|es)?(?![a-z0-9])")


def compile_terms(terms):
    return [term_regex(t) for t in terms]


# ----------------------------------------------------------------------------
# KNOWLEDGE FROM THE RESEARCH (what the bot "knows")
# ----------------------------------------------------------------------------

# Terms that almost always mean the tower industry / Edotco story
CORE = compile_terms([
    "edotco", "ইডটকো", "tower sharing", "টাওয়ার শেয়ারিং", "towerco", "টাওয়ারকো",
    "tower company", "tower companies", "টাওয়ার কোম্পানি", "summit towers", "summit tower",
    "সামিট টাওয়ার", "kirtonkhola", "kirtankhola", "কীর্তনখোলা", "frontier tower",
    "ফ্রন্টিয়ার টাওয়ার", "pinnacle towers", "ab hightech", "ab hi tech", "এবি হাইটেক",
    "infrastructure sharing", "অবকাঠামো ভাগাভাগি", "ইনফ্রাস্ট্রাকচার শেয়ারিং",
    "army transmission company", "আর্মি ট্রান্সমিশন", "atcl", "এটিসিএল", "bangla phone",
    "বাংলা ফোন", "greencon", "গ্রিনকন", "national infrastructure and connectivity",
    "tower infrastructure", "টাওয়ার অবকাঠামো",
])

# Clearly about mobile/telecom towers
STRONG = compile_terms([
    "mobile tower", "মোবাইল টাওয়ার", "telecom tower", "টেলিকম টাওয়ার", "cell tower",
    "mobile phone tower", "মোবাইল ফোন টাওয়ার", "মুঠোফোন টাওয়ার", "network tower",
    "নেটওয়ার্ক টাওয়ার", "5g tower", "ফাইভ জি টাওয়ার", "tower site", "টাওয়ার সাইট",
    "tower rent", "টাওয়ার ভাড়া", "tower sale", "টাওয়ার বিক্রি", "tower theft",
    "টাওয়ার চুরি", "টাওয়ারের ব্যাটারি", "টাওয়ার ব্যাটারি", "টাওয়ার নির্মাণ", "টাওয়ার স্থাপন",
    "টাওয়ার বসানো", "টাওয়ার বসাতে", "tower rollout", "tower tenancy",
])

# Context words: they make a plain "tower" count as telecom
CONTEXT = compile_terms([
    "btrc", "বিটিআরসি", "mno", "mobile operator", "মোবাইল অপারেটর", "telecom operator",
    "robi", "রবি", "grameenphone", "গ্রামীণফোন", "banglalink", "বাংলালিংক", "teletalk",
    "টেলিটক", "5g", "4g", "ফাইভ জি", "ফোর জি", "telecom", "টেলিকম", "telecommunication",
    "টেলিযোগাযোগ", "network", "নেটওয়ার্ক", "spectrum", "স্পেকট্রাম", "fibre", "fiber",
    "ফাইবার", "nttn", "এনটিটিএন", "passive infrastructure", "smp", "এসএমপি",
    "significant market power", "মোবাইল ফোন", "mobile phone",
])

TOWER_ANY = compile_terms(["tower", "টাওয়ার"])

# Not what we want: landmark towers, control towers, power pylons, high-rise buildings
NOISE = compile_terms([
    "eiffel", "আইফেল", "clock tower", "ক্লক টাওয়ার", "ঘড়ি টাওয়ার", "twin towers", "টুইন টাওয়ার",
    "trump tower", "ট্রাম্প টাওয়ার", "burj", "tower hamlets", "টাওয়ার হ্যামলেটস",
    "tokyo tower", "leaning tower", "ivory tower", "water tower", "ওয়াটার টাওয়ার",
    "tower bridge", "tower of london", "watchtower", "watch tower", "ওয়াচ টাওয়ার",
    "tower block", "cn tower", "sky tower", "grenfell", "control tower", "কন্ট্রোল টাওয়ার",
    "cooling tower", "tower crane", "টাওয়ার ক্রেন", "transmission tower",
    "ট্রান্সমিশন টাওয়ার", "power tower", "বিদ্যুতের টাওয়ার", "বিদ্যুৎ টাওয়ার", "pylon",
    "tower defense", "tower hotel",
])
BUILDING = compile_terms([
    "fire", "আগুন", "flat", "ফ্ল্যাট", "apartment", "বহুতল", "residential", "আবাসিক",
    "ভবন", "building", "plaza", "shopping", "mall", "collapse", "ধস",
])

# Proof it is about Bangladesh
BD_HINTS = compile_terms([
    "bangladesh", "bangladeshi", "বাংলাদেশ", "dhaka", "ঢাকা", "btrc", "বিটিআরসি", "robi", "রবি",
    "grameenphone", "গ্রামীণফোন", "banglalink", "বাংলালিংক", "teletalk", "টেলিটক", "taka",
    "bdt", "chattogram", "chittagong", "চট্টগ্রাম", "sylhet", "সিলেট", "khulna", "খুলনা",
    "rajshahi", "রাজশাহী", "barishal", "barisal", "বরিশাল", "rangpur", "রংপুর",
    "mymensingh", "ময়মনসিংহ", "cox s bazar", "কক্সবাজার", "gazipur", "গাজীপুর",
    "narayanganj", "নারায়ণগঞ্জ", "summit", "সামিট", "kirtonkhola", "কীর্তনখোলা",
    "bangla phone", "বাংলা ফোন", "ictd", "nttn", "এনটিটিএন",
])

# Other countries (only counted against a headline that has no Bangladesh hint)
FOREIGN = compile_terms([
    "india", "indian", "ভারত", "কলকাতা", "kolkata", "west bengal", "পশ্চিমবঙ্গ", "delhi", "দিল্লি",
    "mumbai", "মুম্বাই", "pakistan", "পাকিস্তান", "nepal", "নেপাল", "bhutan", "sri lanka",
    "শ্রীলঙ্কা", "malaysia", "malaysian", "মালয়েশিয়া", "kuala lumpur", "indonesia",
    "ইন্দোনেশিয়া", "thailand", "vietnam", "myanmar", "মিয়ানমার", "cambodia", "philippines",
    "africa", "nigeria", "kenya", "uganda", "ghana", "usa", "u s", "united states", "america",
    "আমেরিকা", "যুক্তরাষ্ট্র", "uk", "london", "china", "চীন", "dubai", "saudi", "uae",
])

# Sites we accept (any host ending in .bd is also accepted automatically)
TRUSTED = """
thedailystar.net tbsnews.net dhakatribune.com thefinancialexpress.com.bd newagebd.net
observerbd.com theindependentbd.com unb.com.bd bssnews.net bss.gov.bd daily-sun.com
dailyasianage.com bangladeshpost.net thebangladeshtoday.com businesspostbd.com bdnews24.com
prothomalo.com dhakapost.com dailynewnation.com thedailynewnation.com bonikbarta.com
businessinsiderbd.com dailyindustry.news digibanglatech.news techshohor.com bangladeshpratidin.com
bd-pratidin.com kalerkantho.com jugantor.com samakal.com ittefaq.com.bd dailyinqilab.com
dailysangram.com mzamin.com manabzamin.com dailynayadiganta.com janakantha.com
dailyjanakantha.com amardesh.com kalbela.com protidinersangbad.com sangbad.net.bd
bhorerkagoj.com jaijaidinbd.com ajkerpatrika.com banglatribune.com bd24live.com risingbd.com
banglanews24.com jagonews24.com ntvbd.com rtvonline.com somoynews.tv jamuna.tv channel24bd.tv
channelionline.com ekattor.tv independent.tv dbcnews.tv maasranga.tv news24bd.tv
dhakatimes24.com banglamail24.com sarabangla.net kholakagojbd.com bssnews.net
newsbangla24.com bdtechnews.net itbd.news ictdivision.gov.bd btrc.gov.bd
""".split()

# Sites we never accept: social media, aggregators, blogs, foreign Bangla sites, company pages
BLOCKED = """
facebook.com fb.com fb.watch youtube.com youtu.be twitter.com x.com instagram.com tiktok.com
linkedin.com reddit.com pinterest.com quora.com threads.net telegram.org t.me whatsapp.com
vimeo.com medium.com wordpress.com blogspot.com tumblr.com wikipedia.org msn.com yahoo.com
dailyhunt.in newsbreak.com pressreader.com flipboard.com
anandabazar.com eisamay.com bartamanpatrika.com sangbadpratidin.in aajkaal.in
timesofindia.indiatimes.com indiatimes.com hindustantimes.com ndtv.com thehindu.com
indianexpress.com economictimes.com livemint.com business-standard.com zeenews.india.com
news18.com dawn.com tribune.com.pk thestar.com.my freemalaysiatoday.com nst.com.my
bernama.com theedgemarkets.com theedgemalaysia.com thesun.my malaysiakini.com
edotcogroup.com axiata.com
""".split()


def get_host(url):
    try:
        h = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


def host_in(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def classify_host(host):
    if not host:
        return "unknown"
    if host_in(host, BLOCKED):
        return "blocked"
    if host_in(host, TRUSTED) or host.endswith(".bd"):
        return "trusted"
    return "unknown"


# ----------------------------------------------------------------------------
# SMART SCORING
# ----------------------------------------------------------------------------

def count_hits(rx_list, text):
    return sum(1 for r in rx_list if r.search(text))


def any_hit(rx_list, text):
    return any(r.search(text) for r in rx_list)


def topic_score(text):
    """How strongly does this headline look like a mobile-tower / Edotco story? 0 = no."""
    core = count_hits(CORE, text)
    strong = count_hits(STRONG, text)
    ctx = count_hits(CONTEXT, text)
    gen = any_hit(TOWER_ANY, text)
    if core == 0 and strong == 0:
        if not gen:
            return 0.0
        if any_hit(NOISE, text) or any_hit(BUILDING, text):
            return 0.0
        return 1.5 + min(ctx, 3)  # a plain 'tower': needs telecom context to score well
    s = min(core, 2) * 3.0 + min(strong, 2) * 2.5 + min(ctx, 3) * 1.0
    if gen:
        s += 0.5
    return s


STOP = set("""the and for with that this from have has was were will are not but its his her they their said says
after over into new also than which been more about who what when where while their there would could should
because during against between under until can may you your our out one two all any each most other some such
only own same too very just here how why""".split()) | {norm(w) for w in """এবং ও এর এই যে থেকে করে করা হয় হবে হয়েছে
জন্য সঙ্গে সাথে না তার তাদের একটি এক দিয়ে নিয়ে বলে বলেন আরও কিন্তু তবে এ সে আমি কোনো পর মধ্যে ছিল রয়েছে করেছে
করেন হচ্ছে করতে তিনি এছাড়া যায় যাবে ওই সব অন্য বা এখন আজ""".split()}


def stem(tok):
    if has_bangla(tok):
        for suf in BN_STRIP:
            if tok.endswith(suf) and len(tok) - len(suf) >= 2:
                return tok[: -len(suf)]
    return tok


def tokenize(text):
    t = norm(text)
    return [x for x in re.split(r"[\s.,;:!?\"'()\[\]{}\u201c\u201d\u2018\u2019\u0964/\\|]+", t) if x]


def query_terms(q):
    """Turn a search line into matchable terms ('exact phrase' stays together)."""
    phrases = re.findall(r'"([^"]+)"', q)
    rest = re.sub(r'"[^"]+"', " ", q)
    rest = re.sub(r"\b(after|before|site|when):\S+", " ", rest, flags=re.I)
    out = [norm(p) for p in phrases]
    for tok in tokenize(rest):
        if tok in STOP or tok == "or" or len(tok) < (2 if has_bangla(tok) else 3):
            continue
        out.append(stem(tok))
    seen, res = set(), []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            res.append(t)
    return res


def article_terms(text, n=8):
    """Pick the most telling words of a news article (headline words count double)."""
    lines = [l for l in (text or "").splitlines() if l.strip()]
    head = lines[0] if lines else ""
    cnt = Counter()
    for w in tokenize(head):
        if w not in STOP and len(w) >= (2 if has_bangla(w) else 3):
            cnt[stem(w)] += 3
    for w in tokenize(text):
        if w not in STOP and len(w) >= (2 if has_bangla(w) else 3) and not w.isdigit():
            cnt[stem(w)] += 1
    return [w for w, _ in cnt.most_common(n)]


def similarity(text, term_sets):
    best = 0.0
    for rxs in term_sets:
        if rxs:
            best = max(best, sum(1 for r in rxs if r.search(text)) / len(rxs))
    return best


def geo_hits(text):
    return count_hits(BD_HINTS, text), count_hits(FOREIGN, text)


THRESH_TOPIC = {"Strict": 3.0, "Balanced": 2.5, "Wide": 1.5}
THRESH_QUERY = {"Strict": 1.0, "Balanced": 0.67, "Wide": 0.5}
THRESH_ARTICLE = {"Strict": 0.4, "Balanced": 0.25, "Wide": 0.15}


def evaluate(item, ctx):
    """Return the item (with a score) if it passes all checks, else None."""
    text = norm(item["title"])
    cls = classify_host(item["host"])
    level = ctx["level"]
    if cls == "blocked":
        return None
    bd, fo = geo_hits(text)
    if cls == "unknown":
        if level == "Strict" or bd == 0 or fo > 0:
            return None
    elif fo > 0 and bd == 0:
        return None

    kind = ctx["kind"]
    if kind == "default":
        topic = topic_score(text)
        if topic < THRESH_TOPIC[level]:
            return None
        pct = topic * 12
    else:
        sim = similarity(text, ctx["term_sets"])
        thr = (THRESH_ARTICLE if kind == "article" else THRESH_QUERY)[level]
        if sim < thr or sim == 0:
            return None
        topic = 2.5 + sim * 3
        pct = sim * 70
    pct += (20 if cls == "trusted" else 0) + 5 * min(bd, 2)
    item["topic"] = topic
    item["score"] = int(min(100, round(pct)))
    item["trusted"] = cls == "trusted"
    return item


KEYWORDS = """
# NewsBot default keywords - one search per line. Lines starting with # are ignored.
# Language is detected automatically: Bangla letters = Bangla search, otherwise English.
# Quotes "..." mean exact phrase. Add or delete lines freely.

edotco
edotco Bangladesh
"tower company" Bangladesh
"tower companies" Bangladesh
"mobile tower" Bangladesh
"telecom tower" Bangladesh
"tower sharing" Bangladesh
BTRC tower
"infrastructure sharing" BTRC
"Summit Towers"
Kirtonkhola Tower
"Frontier Tower" Bangladesh
"Pinnacle Towers" Bangladesh
"AB Hightech" tower
"TowerCo Association" Bangladesh
ATCL "Army Transmission" tower
Banglalink tower sale
Robi tower sale
Grameenphone tower Bangladesh
"5G tower" Bangladesh
"tower rent" Bangladesh
"tower theft" Bangladesh
Bangladesh telecom infrastructure licence BTRC

ইডটকো
ইডটকো বাংলাদেশ
মোবাইল টাওয়ার
টেলিকম টাওয়ার
টাওয়ার কোম্পানি
টাওয়ার শেয়ারিং
বিটিআরসি টাওয়ার
অবকাঠামো ভাগাভাগি লাইসেন্স
সামিট টাওয়ার
কীর্তনখোলা টাওয়ার
ফ্রন্টিয়ার টাওয়ার
টাওয়ারকো অ্যাসোসিয়েশন
আর্মি ট্রান্সমিশন কোম্পানি
বাংলালিংক টাওয়ার বিক্রি
রবি টাওয়ার বিক্রি
গ্রামীণফোন টাওয়ার
ফাইভ-জি টাওয়ার
টাওয়ার ভাড়া
টাওয়ারের ব্যাটারি চুরি
টাওয়ার নির্মাণ বিটিআরসি
এসএমপি টাওয়ার কোম্পানি
"""

PROMPT = """
ROLE
You are the relevance checker for a Bangladesh media-monitoring bot. You receive news
headlines (Bangla or English) and decide which ones to KEEP.

SCOPE - KEEP a headline only if BOTH are true
1) It is news from or about BANGLADESH, published by a Bangladeshi news/media outlet.
2) Its subject is the MOBILE TOWER / TOWER COMPANY / TELECOM INFRASTRUCTURE field,
   especially EDOTCO Bangladesh.

DROP
- Other countries (India, West Bengal/Kolkata Bangla sites, Pakistan, Malaysia-only,
  Africa, etc.), even if the company is the same. Edotco Malaysia/Indonesia/Pakistan = drop.
- Social media, blogs, forums, video sites, company press pages, press-release farms.
- Landmark/other towers: Eiffel, clock towers, Twin Towers, Trump Tower, control towers,
  water towers, cooling towers, tower cranes, power-transmission pylons, tower block fires,
  residential/commercial high-rise buildings named "Tower".
- General telecom news with no tower/infrastructure angle (plain Robi/GP/Banglalink
  offers, packages, tariffs, SIM rules, internet speed) unless towers are mentioned.

FIELD KNOWLEDGE (researched, Nov 2026)
- Regulator: BTRC (বিটিআরসি), Ministry of Posts, Telecommunications and ICT.
- Tower sharing guideline 2018. On 1 Nov 2018 BTRC licensed four tower companies:
  edotco Bangladesh (ইডটকো), Summit Towers/TASC Summit Tower (সামিট টাওয়ার),
  Kirtonkhola Tower Bangladesh (কীর্তনখোলা, American Tower), AB Hightech Consortium
  (later acquired by Pinnacle Towers). Frontier Tower was licensed later (2020).
- Edotco Bangladesh: Malaysian edotco Group (Axiata) subsidiary, operating since 2013,
  market leader (roughly 17,000-18,000 towers). Declared SMP (significant market power)
  in 2022, limited in new-tower share. Local partner Getco (via Greencon Tower); BRAC
  reported as shareholder. Innovations: bamboo tower, FRP/fibreglass tower, hybrid
  solar-wind, span prestressed concrete tower, smart pole/street furniture, 5G-ready
  Tower Operation Centre (Jan 2025), CSR "Tower to Power". Country MDs over time:
  Ricky Steyn, Sunil Isaac, and a newer appointment reported later.
- Deals: Robi sold 5,258 towers to edotco (2015); Summit bought ~2,000 Banglalink towers
  for about Tk 1,100 crore (2023, with leaseback); Robi/Grameenphone tower sale talks.
- Industry bodies/events: Bangladesh TowerCo Association; tower rent and SLA disputes
  between MNOs and towercos; tower revenue-share on asset sales; tower theft/battery
  theft; local opposition or radiation fears; 5G readiness.
- Licensing reform 2025-26: NTTN and tower-sharing licences merged into a National
  Infrastructure and Connectivity Services licence; in May 2026 Army Transmission
  Company Ltd (ATCL, Army Welfare Trust) and Bangla Phone received Telecommunication
  Infrastructure Sharing licences.
- Operators: Grameenphone (গ্রামীণফোন), Robi (রবি), Banglalink (বাংলালিংক), Teletalk (টেলিটক).

TRUSTED SOURCES (examples; any *.bd domain is also fine)
English: The Daily Star, The Business Standard (tbsnews.net), Dhaka Tribune, The Financial
Express, New Age, The Independent, Daily Observer, Daily Sun, Asian Age, Bangladesh Post,
Business Post, UNB, BSS, bdnews24, Prothom Alo English, Dhaka Post, Daily Industry.
Bangla: Prothom Alo, Kaler Kantho, Jugantor, Samakal, Ittefaq, Bangladesh Pratidin,
Janakantha, Inqilab, Naya Diganta, Manab Zamin, Amar Desh, Kalbela, Protidiner Sangbad,
Ajker Patrika, Bonik Barta, Banglanews24, Jagonews24, RisingBD, Bangla Tribune,
Techshohor, Digibanglatech, TV: Somoy, Jamuna, Channel 24, NTV, RTV, Independent, DBC,
Ekattor, Maasranga. E-papers of the same newspapers.

OUTPUT FORMAT
Reply with ONLY JSON, nothing else: {"keep": [list of the headline numbers to keep]}
When unsure and the headline is clearly about Bangladesh mobile towers, KEEP it.
"""
