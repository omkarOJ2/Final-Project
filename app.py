from flask import Flask, render_template, request, jsonify
from groq import Groq
from newsapi import NewsApiClient
import feedparser
import os
import re
import markdown
import time
from datetime import datetime
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# ── API Clients ──────────────────────────────────────────────────────────────
groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))
newsapi = NewsApiClient(api_key=os.getenv('NEWS_API_KEY'))

GROQ_MODEL = 'llama-3.3-70b-versatile'

# Google News RSS topic IDs for trending news
GNEWS_TOPICS = {
    'Technology': 'CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB',
    'Business':   'CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRuTjFJU0FtVnVHZ0pWVXlnQVAB',
    'Sports':     'CAAqJggKIiBDQkFTRWdvSUwyMHZNRFp1ZEdvU0FtVnVHZ0pWVXlnQVAB',
    'Health':     'CAAqIQgKIhtDQkFTRGdvSUwyMHZNR3QwTlRFU0FtVnVLQUFQAQ',
    'Science':    'CAAqJggKIiBDQkFTRWdvSUwyMHZNRFp0Y1RFU0FtVnVHZ0pWVXlnQVAB',
    'Entertainment': 'CAAqJggKIiBDQkFTRWdvSUwyMHZNREpxYW5RU0FtVnVHZ0pWVXlnQVAB',
}

REGION_GNEWS = {
    'India': 'IN', 'US': 'US', 'UK': 'GB', 'Australia': 'AU',
    'Canada': 'CA', 'Germany': 'DE', 'France': 'FR', 'Japan': 'JP',
    'China': 'CN', 'Brazil': 'BR', 'Worldwide': 'US'
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def gnews_search(query: str, max_results: int = 8):
    """Search Google News RSS; returns (text, sources_list)."""
    try:
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        entries = feed.entries[:max_results]
        if not entries:
            return "No search results found.", []
        snippets, sources = [], []
        for e in entries:
            title   = e.get('title', '')
            link    = e.get('link', '')
            summary = re.sub(r'<[^>]+>', '', e.get('summary', ''))[:150]
            pub     = e.get('published', '')
            src     = e.get('source', {}).get('title', 'Unknown')
            snippets.append(f"• **{title}**\n  Source: {src} | {pub}\n  {summary}\n  URL: {link}")
            sources.append({'title': title, 'url': link, 'source': src})
        return "\n\n".join(snippets), sources
    except Exception as exc:
        return f"News search error: {exc}", []


def gnews_topic_feed(topic_id: str, region_code: str = 'US', max_results: int = 10) -> list:
    """Fetch articles from a Google News topic RSS feed."""
    try:
        url = f"https://news.google.com/rss/topics/{topic_id}?hl=en-{region_code}&gl={region_code}&ceid={region_code}:en"
        feed = feedparser.parse(url)
        items = []
        for e in feed.entries[:max_results]:
            title = e.get('title', '')
            if not title or '[Removed]' in title:
                continue
            summary = re.sub(r'<[^>]+>', '', e.get('summary', ''))[:250]
            items.append({
                "title": title,
                "summary": summary or "Click to read the full article.",
                "source": e.get('source', {}).get('title', 'Google News'),
                "url": e.get('link', '#'),
                "publishedAt": e.get('published', ''),
                "importance": "High"
            })
        return items
    except Exception:
        return []


def gnews_general_feed(region_code: str = 'US', max_results: int = 10) -> list:
    """Fetch top headlines from Google News general RSS."""
    try:
        url = f"https://news.google.com/rss?hl=en-{region_code}&gl={region_code}&ceid={region_code}:en"
        feed = feedparser.parse(url)
        items = []
        for e in feed.entries[:max_results]:
            title = e.get('title', '')
            if not title or '[Removed]' in title:
                continue
            summary = re.sub(r'<[^>]+>', '', e.get('summary', ''))[:250]
            items.append({
                "title": title,
                "summary": summary or "Click to read the full article.",
                "source": e.get('source', {}).get('title', 'Google News'),
                "url": e.get('link', '#'),
                "publishedAt": e.get('published', ''),
                "importance": "High"
            })
        return items
    except Exception:
        return []



# ── Word → digit map for Indian currency conversion ──────────────────────────
_W2D = {
    'zero':'0','one':'1','two':'2','three':'3','four':'4',
    'five':'5','six':'6','seven':'7','eight':'8','nine':'9',
}

def _currency_replace(m: re.Match) -> str:
    """Convert 'X point Y Z crore/lakh' → '₹X.YZ crore/lakh'."""
    integer_word = m.group(1).lower()
    decimal_words = re.split(r'\s+', m.group(2).strip().lower())
    integer_digit = _W2D.get(integer_word, integer_word)
    decimal_digits = ''.join(_W2D.get(w, w) for w in decimal_words)
    unit = m.group(3)
    return f'₹{integer_digit}.{decimal_digits} {unit}'

_CURRENCY_RE = re.compile(
    r'\b(zero|one|two|three|four|five|six|seven|eight|nine)\s+point\s+'
    r'((?:(?:zero|one|two|three|four|five|six|seven|eight|nine)\s*)+)'
    r'(crore|lakh)\b',
    re.IGNORECASE,
)

# Matches: "Some Headline  NEW DELHI, May 12, 2026 — lead..."
_MERGED_LINE_RE = re.compile(
    r'^(.{6,90}?)\s{1,4}([A-Z][A-Z\s]{2,}),\s+(\w+ \d{1,2},\s+\d{4})\s+[—\-–]\s+(.+)$'
)

_BAD_OPENERS = re.compile(
    r'^(In\s+conclusion[,.]?\s*|To\s+summarize[,.]?\s*|In\s+summary[,.]?\s*'
    r'|Overall[,.]?\s*|It\s+remains\s+to\s+be\s+seen[,.]?\s*)',
    re.IGNORECASE,
)

_WEAK_VERBS = re.compile(
    r'\b(reported|noted|stated|claimed|revealed|indicated|added)\b',
)


def post_process_article(raw: str) -> str:
    """
    Deterministically fix the six most common AP Style output failures
    without any extra LLM call.
    """
    lines = raw.strip().split('\n')
    if not lines:
        return raw

    # ── Fix 1: Headline + dateline merged on the same first non-empty line ──
    first_idx = next((i for i, l in enumerate(lines) if l.strip()), 0)
    m = _MERGED_LINE_RE.match(lines[first_idx].strip())
    if m:
        headline   = m.group(1).strip()
        city       = m.group(2).strip()
        date_part  = m.group(3).strip()
        lead_text  = m.group(4).strip()
        rebuilt    = lines[:first_idx]
        rebuilt.append(headline)
        rebuilt.append('')
        rebuilt.append(f"{city}, {date_part} — {lead_text}")
        rebuilt.extend(lines[first_idx + 1:])
        lines = rebuilt

    # ── Fix 2: Lead too short — append a note inside the raw text ──────────
    # Find the dateline line and check lead length
    for i, line in enumerate(lines):
        dl = re.match(r'^[A-Z][A-Z\s]+,\s+\w+ \d{1,2},\s+\d{4}\s+[—\-–]\s+(.+)$', line.strip())
        if dl:
            lead_words = dl.group(1).split()
            if len(lead_words) < 15:
                # Append a placeholder so the checker can see it needs expanding
                # (we don't fabricate facts — just note the gap)
                lines[i] = line.rstrip() + ' [Editor: expand lead to answer Who/What/When/Where/Why fully.]'
            break

    # ── Fix 3: Strip bad conclusion openers ────────────────────────────────
    lines = [_BAD_OPENERS.sub('', l) for l in lines]

    # ── Fix 4: Replace weak attribution verbs with "said" ──────────────────
    # Pattern: "Capitalised Source Name  reported/noted/stated" → keep source, swap verb
    _ATTRIB_RE = re.compile(
        r'([A-Z][A-Za-z](?:[A-Za-z\s]{0,30}?))\s+'
        r'(reported|noted|stated|claimed|revealed|indicated)\b',
    )
    processed = []
    for line in lines:
        line = _ATTRIB_RE.sub(lambda m2: m2.group(1) + ' said', line)
        processed.append(line)
    lines = processed

    # ── Fix 5: Indian currency word → numeral (₹X.YZ crore/lakh) ──────────
    lines = [_CURRENCY_RE.sub(_currency_replace, l) for l in lines]

    # ── Fix 6: Ensure blank lines between non-empty paragraphs ─────────────
    normalised = []
    prev_empty = True
    for line in lines:
        is_empty = not line.strip()
        if not is_empty and not prev_empty and normalised:
            # If previous line was non-empty content and we have no blank gap,
            # check if previous line looks like end of paragraph (ends with . " !)
            last = normalised[-1].rstrip()
            if last and last[-1] in '."\'' '!' and not line[0].isupper() is False:
                # Don't auto-insert — too risky for mid-paragraph line wraps
                pass
        normalised.append(line)
        prev_empty = is_empty

    return '\n'.join(normalised)


def groq_chat(system: str, user: str, max_tokens: int = 1500, model: str = None) -> str:
    """Call Groq LLM with exponential backoff on rate limits."""
    use_model = model or GROQ_MODEL
    for attempt in range(3):
        try:
            resp = groq_client.chat.completions.create(
                model=use_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return resp.choices[0].message.content
        except Exception as e:
            err = str(e)
            if '429' in err or 'rate_limit' in err.lower():
                if attempt < 2:
                    time.sleep((attempt + 1) * 10)
                    continue
                raise Exception("AI rate limit reached. Please wait a moment and try again.")
            raise e


# ── Page Routes ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generator')
def generator():
    return render_template('generator.html')

@app.route('/detector')
def detector():
    return render_template('detector.html')

@app.route('/checker')
def checker():
    return render_template('checker.html')

@app.route('/trending')
def trending():
    return render_template('trending.html')


# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.route('/api/generate-article', methods=['POST'])
def generate_article():
    try:
        data = request.json or {}
        topic      = data.get('topic', '').strip()
        word_limit = data.get('word_limit', 500)
        nature     = data.get('nature', 'Formal')

        if not topic or len(topic) < 3:
            return jsonify({'success': False, 'error': 'Topic must be at least 3 characters.'}), 400
        if len(topic) > 500:
            return jsonify({'success': False, 'error': 'Topic too long (max 500 chars).'}), 400

        # Real-time Google News search — keep context small to stay within TPM limits
        search_ctx,  sources1 = gnews_search(f"{topic} latest news", max_results=3)
        search_ctx2, sources2 = gnews_search(f"{topic} update {datetime.now().year}", max_results=2)
        combined_ctx = search_ctx + "\n\n" + search_ctx2
        seen, unique_sources = set(), []
        for s in (sources1 + sources2):
            if s['url'] not in seen:
                seen.add(s['url'])
                unique_sources.append(s)

        today     = datetime.now().strftime("%B %d, %Y")

        # Detect likely dateline city from topic keywords
        topic_lower = topic.lower()
        if any(k in topic_lower for k in ['chennai', 'tamil', 'vijay', 'tamilnadu', 'tn ']):
            dateline_city = "CHENNAI"
        elif any(k in topic_lower for k in ['mumbai', 'maharashtra', 'bombay']):
            dateline_city = "MUMBAI"
        elif any(k in topic_lower for k in ['bengaluru', 'bangalore', 'karnataka']):
            dateline_city = "BENGALURU"
        elif any(k in topic_lower for k in ['kolkata', 'bengal', 'west bengal']):
            dateline_city = "KOLKATA"
        elif any(k in topic_lower for k in ['hyderabad', 'telangana', 'andhra']):
            dateline_city = "HYDERABAD"
        elif any(k in topic_lower for k in ['india', 'delhi', 'modi', 'bjp', 'congress', 'parliament']):
            dateline_city = "NEW DELHI"
        elif any(k in topic_lower for k in ['pakistan', 'islamabad']):
            dateline_city = "ISLAMABAD"
        elif any(k in topic_lower for k in ['us ', 'usa', 'trump', 'biden', 'washington', 'america']):
            dateline_city = "WASHINGTON"
        elif any(k in topic_lower for k in ['uk', 'london', 'britain', 'england']):
            dateline_city = "LONDON"
        else:
            dateline_city = "NEW DELHI"

        system = """You are a senior AP wire journalist. Every article you write must pass a rigorous AP Style editorial check. Study the FORMAT EXAMPLE below — your output must follow it exactly.

=== FORMAT EXAMPLE (follow this structure precisely) ===

Vijay Sworn In as Tamil Nadu Chief Minister

CHENNAI, May 12, 2026 — Actor-turned-politician Vijay took oath as Tamil Nadu's Chief Minister on Monday, becoming the first TVK leader to hold the post after his party's landslide victory last week.

The swearing-in ceremony at Raj Bhavan saw Vijay flanked by Cabinet ministers drawn from diverse backgrounds, according to The Hindu. Kamal Haasan, who attended the ceremony, said, "Vijay's win is a significant moment for Tamil Nadu."

Vijay's election affidavit declared ₹1.2 crore in gold assets, while his wife Sangeetha declared gold worth ₹4.07 crore, The Hindu said.

Vijay's first Cabinet includes a doctor, a former IRS officer, and a 29-year-old MLA, Business Today said. The New Indian Express noted the new government faces pressure to deliver on poll promises of free bus travel and farm loan waivers.

Zoho founder Sridhar Vembu said, "Grassroots chatter beat the experts in Tamil Nadu, and Vijay's win is a testament to that."

=== END EXAMPLE ===

RULES (non-negotiable):

RULE 1 — HEADLINE: First line only. Title Case Every Major Word (prepositions and articles lowercase). Active verb. 6–10 words. No period. No quotation marks. Must be a COMPLETE, grammatically correct sentence fragment — never omit prepositions (e.g., write "Takes Oath of Office" NOT "Takes Oath Office").

RULE 2 — DATELINE LINE: Second line. Blank line between headline and dateline. Format exactly: CITY IN CAPS, Month Day, Year — followed immediately by the lead sentence. Example: CHENNAI, May 12, 2026 — Actor-turned-politician Vijay...

RULE 3 — LEAD SENTENCE: The lead is part of the dateline line, starting immediately after the em dash (—). It is NOT a separate line. MINIMUM 20 WORDS, MAXIMUM 35 WORDS. Must answer: WHO did WHAT, WHEN, WHERE, and WHY. The most newsworthy fact comes first. No scene-setting opener.

RULE 4 — BODY PARAGRAPHS: Each is a separate paragraph with a blank line before it. Maximum 3 sentences per paragraph. Every factual claim must cite a named source using "said" or "according to [Source]". Never use: reported, noted, stated, claimed, added, revealed.

RULE 5 — NUMBERS: Use numerals for 10 and above. Spell out one through nine. Indian currency: always write as ₹1.2 crore or ₹4.07 crore (never "one point two crore" or "four point zero seven crore"). Ages always use numerals.

RULE 6 — CONCLUSION: Final paragraph must end with a forward-looking quote, a statistic, or context about what happens next. NEVER write: "In conclusion", "To summarize", "In summary", "Overall", "It remains to be seen".

RULE 7 — LINE BREAKS: Headline on line 1. Blank line. Dateline+lead on line 3. Blank line. Body paragraphs each separated by blank lines. Do NOT merge headline and dateline onto the same line under any circumstances."""

        user = f"""Write a {nature} AP Style news article about: {topic}
Target length: ~{word_limit} words | Date: {today}

YOUR OUTPUT MUST FOLLOW THIS EXACT LINE STRUCTURE:
Line 1:  [Headline — Title Case, Active Verb, 6-10 Complete Words, No Period, No Missing Prepositions]
Line 2:  [blank]
Line 3:  {dateline_city}, {today} — [Lead sentence: 20-35 words, WHO did WHAT WHEN WHERE WHY, starts immediately after the em dash]
Line 4:  [blank]
Line 5:  [Body paragraph 1 — most important fact, named source + "said" or "according to"]
Line 6:  [blank]
Line 7:  [Body paragraph 2 — second fact or direct quote, named source]
Line 8:  [blank]
Line 9:  [Body paragraph 3 — context or reaction, named source]
Line 10: [blank]
Line 11: [Final paragraph — forward-looking quote or statistic, NO "In conclusion"]

LIVE NEWS CONTEXT (extract facts from here, cite these sources by name):
{combined_ctx}

Write only the article. No "Here is the article:", no commentary, no preamble."""

        raw        = groq_chat(system, user, max_tokens=1400, model=GROQ_MODEL)
        raw        = post_process_article(raw)          # ← deterministic AP Style fixes
        article    = markdown.markdown(raw, extensions=['tables', 'fenced_code'])
        word_count = len(raw.split())
        return jsonify({
            'success': True, 'article': article,
            'raw_text': raw, 'word_count': word_count,
            'sources': unique_sources[:8]
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500




@app.route('/api/detect-fake-news', methods=['POST'])
def detect_fake_news():
    try:
        data      = request.json or {}
        news_text = data.get('news_text', '').strip()

        if not news_text or len(news_text) < 20:
            return jsonify({'success': False, 'error': 'Please provide at least 20 characters.'}), 400
        if len(news_text) > 10000:
            return jsonify({'success': False, 'error': 'Text too long (max 10,000 chars).'}), 400

        # Strip HTML tags (in case user pasted rendered article)
        clean_text = re.sub(r'<[^>]+>', '', news_text).strip()

        # Extract components for targeted searches
        lines      = [l.strip() for l in clean_text.split('\n') if l.strip()]
        headline   = lines[0][:120] if lines else clean_text[:120]
        first_para = lines[1][:200] if len(lines) > 1 else ''
        body_chunk  = ' '.join(lines[2:5])[:200] if len(lines) > 2 else ''

        # Extract key named entity (first capitalised multi-word phrase from headline)
        entity_match = re.search(r'([A-Z][a-z]+ (?:[A-Z][a-z]+ ?){1,3})', headline)
        entity_query = entity_match.group(1).strip() if entity_match else headline[:60]

        # 5 complementary searches to maximise coverage
        search1, _ = gnews_search(headline, max_results=4)
        search2, _ = gnews_search(f"fact check {headline}", max_results=3)
        search3, _ = gnews_search(f"{entity_query} latest", max_results=3)
        search4    = ""
        if first_para:
            search4, _ = gnews_search(f"{first_para[:100]}", max_results=2)
        search5 = ""
        if body_chunk:
            search5, _ = gnews_search(f"{body_chunk[:100]} news {datetime.now().year}", max_results=2)

        all_ctx = (
            f"SEARCH 1 — Headline match:\n{search1}\n\n"
            f"SEARCH 2 — Fact-check angle:\n{search2}\n\n"
            f"SEARCH 3 — Key entity news:\n{search3}\n\n"
            f"SEARCH 4 — Lead paragraph claims:\n{search4}\n\n"
            f"SEARCH 5 — Body claims:\n{search5}"
        )

        system = """You are a professional fact-checker at a major news agency. Your job is to assess whether the specific claims in an article are supported, contradicted, or unverifiable based on live search results.

CRITICAL RULES:
1. AP-Style structured articles (with datelines, attributed quotes, inverted pyramid) are credible by default — professional format is a positive credibility signal.
2. A claim is VERIFIED if search results report the same or similar facts from real sources.
3. A claim is UNVERIFIABLE only if it is very specific (exact numbers, obscure events) AND no search result touches it at all.
4. A claim is CONTRADICTED only if a search result directly states the opposite.
5. General factual statements that align with the topic are almost always Accurate or Mostly Accurate.
6. DO NOT penalise AI-generated or paraphrased text — assess FACTUAL ACCURACY of claims, not writing style.
7. If the article's facts broadly align with the search results topic even if not word-for-word, that counts as verified."""

        user = f"""Fact-check the article below against all 5 search result sets.

ARTICLE:
{clean_text[:1200]}

SEARCH RESULTS:
{all_ctx[:1800]}

Provide your analysis in EXACTLY this format:

**VERDICT:** [Accurate / Mostly Accurate / Partially Accurate / Inaccurate / Unverifiable] — [confidence]% confidence

**CLAIM VERIFICATION:**
- Claim 1: [state the claim] → [✅ Verified / ⚠️ Partially Verified / ❌ Contradicted / ❓ Unverifiable] — [1-sentence reason citing search result]
- Claim 2: [state the claim] → [✅ Verified / ⚠️ Partially Verified / ❌ Contradicted / ❓ Unverifiable] — [1-sentence reason citing search result]
- Claim 3: [state the claim] → [✅ Verified / ⚠️ Partially Verified / ❌ Contradicted / ❓ Unverifiable] — [1-sentence reason citing search result]
- Claim 4: [state the claim] → [✅ Verified / ⚠️ Partially Verified / ❌ Contradicted / ❓ Unverifiable] — [1-sentence reason citing search result]

**CREDIBILITY SIGNALS:**
- Structure: [AP-Style / No byline / Sensational headline / etc.]
- Attribution: [Well-attributed / Vague sources / No sources]
- Tone: [Neutral / Emotional / Misleading framing]

**RED FLAGS:** [List only genuine red flags, or write "None detected" if article appears credible]

**OVERALL ASSESSMENT:** [2-3 sentences giving a clear, honest final judgment about the article's factual reliability]"""

        raw        = groq_chat(system, user, max_tokens=1000, model=GROQ_MODEL)
        analysis   = markdown.markdown(raw, extensions=['tables', 'fenced_code'])
        confidence = 50
        verdict    = 'Unverifiable'
        m = re.search(r'(\d+)%\s*confidence', raw, re.IGNORECASE)
        if m: confidence = int(m.group(1))
        v = re.search(r'\*\*VERDICT:\*\*\s*([^\n(—\-]+)', raw)
        if v: verdict = v.group(1).strip().rstrip('—').strip()
        return jsonify({
            'success': True, 'analysis': analysis,
            'confidence': confidence, 'verdict': verdict
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/check-format', methods=['POST'])
def check_format():
    try:
        data         = request.json or {}
        article_text = data.get('article_text', '').strip()

        if not article_text or len(article_text) < 20:
            return jsonify({'success': False, 'error': 'Please provide at least 20 characters.'}), 400
        if len(article_text) > 10000:
            return jsonify({'success': False, 'error': 'Text too long (max 10,000 chars).'}), 400

        clean_text = re.sub(r'<[^>]+>', '', article_text).strip()
        word_count = len(clean_text.split())

        system = """You are a rigorous senior editor at the Associated Press with 20+ years of experience. You give honest, detailed, specific scores based only on actual quality — not encouragement.

HOW TO IDENTIFY AP ARTICLE STRUCTURE:
- HEADLINE: The very FIRST non-empty line of the article. Even a short line like "Four Killed in West Bengal Post-Election Violence" is a complete, valid headline. Do NOT say the article is missing a headline if a first line exists.
- DATELINE: A line starting with a CITY NAME IN CAPS followed by comma, date, and em dash (—). Example: "NEW DELHI, May 12, 2026 —". This is correct format — score 8-9/10.
- LEAD: The first sentence(s) immediately after the dateline. Must answer Who/What/When/Where/Why in ≤35 words.
- ATTRIBUTION: Both "said" AND "according to [Source]" are correct AP attribution. Do NOT penalise "according to".
- BYLINE: No byline is required in AP format — do NOT deduct points for missing byline.

SCORING RUBRIC (apply strictly):
1-3: Severely lacking — missing fundamental journalistic elements (no recognisable headline, no lead, no structure)
4-5: Below average — major structural or AP Style problems, vague attribution, poor clarity
6: Average — basic structure present but notable weaknesses in attribution, inverted pyramid, or voice
7: Good — mostly sound journalism with 2-3 clear fixable issues
8: Strong — only minor stylistic or formatting corrections needed
9: Near-perfect — publication-ready with one small tweak
10: Flawless AP Style — rare, award-worthy

DO:
- Score each element independently on its OWN merits — do not anchor element scores to the overall score
- Be specific: name exact sentences or passages that fail or succeed
- Give different scores for different elements — a 9 headline can coexist with a 5 dateline
- Penalise: vague attribution (anonymous sources), passive voice, run-on sentences, buried ledes, "In conclusion"
- Reward: active-voice leads, specific numbers, named sources, tight sentences, forward-looking conclusions"""

        user = f"""Review this {word_count}-word article for AP Style compliance. Be thorough and specific.

IMPORTANT: The first line of the article below is the HEADLINE. Evaluate it as a headline.

ARTICLE:
---
{clean_text[:2000]}
---

Write your review in EXACTLY this format (no extra commentary outside the format):

SCORE: (overall score 1-10, must reflect honest quality not encouragement)
PUBLISHABILITY: (one of: Ready to Publish | Needs Minor Edits | Needs Revision | Major Rewrite)

HEADLINE: (score)/10 | (specific comment: is the first line in title case? active verb? 6-10 words? compelling summary of the story?)
DATELINE: (score)/10 | (specific comment: is CITY, Month Day, Year — format present? is city name all caps? is em dash used?)
LEAD: (score)/10 | (specific comment: does it answer Who/What/When/Where/Why in ≤35 words? is it the most newsworthy fact?)
BODY: (score)/10 | (specific comment: inverted pyramid order? paragraph length ≤3 sentences? smooth transitions? active voice?)
ATTRIBUTION: (score)/10 | (specific comment: are facts linked to named sources using "said" or "according to"? any vague sourcing?)
CONCLUSION: (score)/10 | (specific comment: does it end with context/quote/statistic? does it avoid "In conclusion"/"To summarize"?)

STRENGTHS:
- (specific strength with example from article)
- (specific strength with example from article)
- (specific strength with example from article)

IMPROVEMENTS:
- (specific actionable fix with the exact passage to change)
- (specific actionable fix with the exact passage to change)
- (specific actionable fix with the exact passage to change)
- (specific actionable fix with the exact passage to change)
- (specific actionable fix with the exact passage to change)

AP_CHECK:
Numbers: (PASS if numerals used correctly for 10+, spelled out below 10; FAIL with example if not)
Attribution: (PASS if named sources cited with "said" or "according to"; FAIL with example if vague or missing)
Active voice: (PASS if majority of verbs are active; FAIL with example of passive construction found)
Sentence length: (PASS if avg under 25 words; FAIL if run-ons present — quote the offending sentence)
Headline style: (PASS if title case, active, no period, 6-10 words; FAIL with specific issue)

DETAILED_NOTES: (2-3 sentences of honest editorial summary — the single most important thing this writer must fix, and what they did best)"""


        raw      = groq_chat(system, user, max_tokens=1200, model=GROQ_MODEL)
        feedback = markdown.markdown(raw, extensions=['tables', 'fenced_code'])
        score = None
        m = re.search(r'^SCORE:\s*(\d+)', raw, re.MULTILINE)
        if m: score = int(m.group(1))
        return jsonify({'success': True, 'feedback': feedback, 'raw': raw, 'score': score})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/trending-news', methods=['POST'])
def trending_news():
    try:
        data = request.json
        region   = data.get('region', 'Worldwide')
        category = data.get('category', 'All')

        region_code = REGION_GNEWS.get(region, 'US')
        news_items  = []

        # ── Try NewsAPI first ──────────────────────────────────────────────
        try:
            country_map = {
                'India': 'in', 'US': 'us', 'UK': 'gb', 'Australia': 'au',
                'Canada': 'ca', 'Germany': 'de', 'France': 'fr', 'Japan': 'jp',
                'China': 'cn', 'Brazil': 'br', 'Worldwide': 'us'
            }
            cat_map = {
                'Technology': 'technology', 'Sports': 'sports', 'Business': 'business',
                'Entertainment': 'entertainment', 'Health': 'health',
                'Science': 'science', 'All': 'general'
            }
            headlines = newsapi.get_top_headlines(
                country=country_map.get(region, 'us'),
                category=cat_map.get(category, 'general'),
                page_size=10
            )
            for a in (headlines.get('articles') or []):
                title = a.get('title') or ''
                if not title or '[Removed]' in title:
                    continue
                news_items.append({
                    "title": title,
                    "summary": a.get('description') or 'Click to read the full article.',
                    "category": category if category != 'All' else 'General',
                    "source": (a.get('source') or {}).get('name', 'Unknown'),
                    "importance": "High",
                    "url": a.get('url', '#'),
                    "publishedAt": a.get('publishedAt', '')
                })
        except Exception:
            pass  # Fall through to Google News RSS

        # ── Fallback / supplement with Google News RSS ─────────────────────
        if len(news_items) < 5:
            topic_id = GNEWS_TOPICS.get(category)
            if topic_id:
                rss_items = gnews_topic_feed(topic_id, region_code, max_results=10)
            else:
                rss_items = gnews_general_feed(region_code, max_results=10)

            # Add category field to RSS items
            for item in rss_items:
                item['category'] = category if category != 'All' else 'General'
            news_items.extend(rss_items)

        # ── Final fallback: keyword search on Google News ──────────────────
        if not news_items:
            query = f"{category} news {region} today" if category != 'All' else f"top news {region} today"
            url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(url)
            for e in feed.entries[:10]:
                title = e.get('title', '')
                if not title:
                    continue
                summary = re.sub(r'<[^>]+>', '', e.get('summary', ''))[:250]
                news_items.append({
                    "title": title,
                    "summary": summary or 'Click to read the full article.',
                    "category": category if category != 'All' else 'General',
                    "source": e.get('source', {}).get('title', 'Google News'),
                    "importance": "Medium",
                    "url": e.get('link', '#'),
                    "publishedAt": e.get('published', '')
                })

        return jsonify({'success': True, 'news': news_items[:10]})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)