# Word-list sources

`kaoyan_5530.txt` is an alphabetized, words-only adaptation of
[`exam-data/NETEMVocabulary`](https://github.com/exam-data/NETEMVocabulary).
The source contains the 5,530 entries from the 2024 National Graduate Entrance
Examination English (I) syllabus. Its data is shared under
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).

`subtlex_us_20k.txt` contains the first 20,000 lowercase lexical entries adapted
from [`words/subtlex-word-frequencies`](https://github.com/words/subtlex-word-frequencies).
That project derives its counts from SUBTLEX-US, a 51-million-word corpus of
American-English movie subtitles, and is distributed under the ISC license.
Capitalization-dominant entries (mostly names), non-lexical tokens, and
one-letter fragments other than `a` and `I` were excluded before taking 20,000
entries.

`gre_2942.txt` is a normalized, words-only adaptation of
[`0xDkXy/GRE_vocabulary_3000`](https://github.com/0xDkXy/GRE_vocabulary_3000).
The source is distributed under the MIT license. Multi-line definitions,
phonetics and examples were omitted; 2,942 valid single-word entries remain.

The 2,942 entries are the valid single-word remainder of one curated "GRE 3000"
source, not an official or exhaustive GRE vocabulary syllabus. The
[ETS test-content overview](https://www.ets.org/gre/test-takers/general-test/prepare/content.html)
describes vocabulary understanding as a verbal-reasoning ability but does not
provide a canonical finite word list.

## Mutually exclusive reading tiers

The reader classifies every word in this order, so a word can only have one
highlight tier:

1. Gaokao 3500: not highlighted for ordinary meanings; a word may receive the
   `specialized` marker only when that article's context identifies a genuine
   uncommon meaning.
2. Kaoyan 5,530 minus Gaokao 3500: `core`.
3. SUBTLEX-US common 20K minus both exam lists: `key`.
4. GRE 2,942 minus all three preceding lists: `gre`.
5. Not covered by any list: only highlighted as `specialized` when the article
   analysis identifies it as domain terminology or contextual polysemy.

Highlight classification scans every token in the article. It is intentionally
independent from the shorter, selected vocabulary-review list stored for each
article.

The reader defaults to the quieter **review-only** scope, which highlights only
the selected database vocabulary for that article. Readers can switch to
**full word-list** scope when they want every eligible article token classified.

Inflected forms are resolved before assigning a higher tier when their base form
belongs to an earlier list: for example, `wars`, `players`, and `rules` inherit
the Gaokao tier of `war`, `player`, and `rule`. Straight and typographic
apostrophes are normalized, so `you're` and `you’re` remain one token; stray
contraction fragments such as `re` are never promoted to common-advanced words.

The per-article review list has a hard maximum of 40 entries. Ordinary Gaokao
3500 words are excluded before ranking. A Gaokao word can only be admitted as
contextual polysemy when its source sentence matches the uncommon usage; merely
appearing in the static polysemy lexicon is not enough. The selector scans
beyond the 40 most frequent raw tokens, ranks only eligible entries, and gives
validated contextual polysemy and domain terminology priority. LLM suggestions
pass through the same context check and final 40-entry cap.
