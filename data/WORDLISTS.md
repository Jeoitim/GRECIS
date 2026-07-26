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
GRECIS only labels an entry as GRE expansion when it is absent from the local
SUBTLEX-US top-20K list.
