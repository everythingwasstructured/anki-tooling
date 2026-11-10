# Audit brief

You are reading a finished Anki deck you did not write. **Report findings only. Edit nothing.**
No corrected deck, no rewritten `cards.json`, no patch file.

## The job

- **Lecture:** {{LECTURE}} ({{LECTURER}}). {{SOURCES}}
- **Deck:** {{COUNTS}}.
- **Exam it serves:** MBChB Year 1 written papers. Single best answer: a clinical scenario, five
  options, one best, about 72 seconds an item, no negative marking.

## Files

```
01-cards.json             every note: uid, type, text or front/back, extra, source, image
02-slides-extracted.txt   every slide. Each text line has an id such as [7.3] (slide 7, line 3).
                          [N7.2] is a speaker-note line. [B]/[I]/[U] are the lecturer's own emphasis.
{{CAPTIONS}}
media/                    every figure the cards use, under the filenames in cards.json
```

Cite slide text by its line id. Cite cards by `uid`.

## Scope decisions made by the student (facts, not excuses)

{{SCOPE}}

## Conventions you would otherwise misread

{{CONVENTIONS}}
- A cloze written as `Question?<br><br>{{c1::whole answer}}` is deliberate. It keeps a card's
  review history when a Basic card had to be rewritten. Do not report it.
- A comparison-table row is one grouping cloze with every value under `c1`. Deliberate.

**You are deliberately not given the plan, the cut list or any build notes.** Reach your own
verdict from the cards and the sources. If a card looks wrong, report it.

## The rules the deck was built to

1. **Every in-scope slide line is carded**, unless the student excluded it or the lecturer
   disowned it in his own words. Overlap with other lectures is not a reason to leave it out.
2. **Off-slide content** (speaker notes, transcript) is a card only where the lecturer marks
   it as important or examinable in his own words. Otherwise it is context in `Extra`, marked
   as spoken or from the notes, or it is absent. Examples he mentions in passing are absent.
3. **One fact, one card** within this deck. A set is carded once: one grouping cloze, or one
   card per member, never both. A contrast is one discrimination card.
4. **A card about one member of a set names that member.** "One advantage of X is ___" is a
   defect: any member fills the blank. A split set shows the members it is not testing.
5. **Content, not label.** The blank is the meaning, mechanism, value or consequence, not the
   name of the thing the sentence is about. Discrimination cards hide the distinguishing
   properties, not the two names.
6. **No card gives itself away**: not from its own visible words, a cliché, grammar, a
   50% guess, or common sense without the lecture.
7. Clozes are bare (no hints), determinate from the stem, and each deletion index hides at
   most 60% of the sentence. Median card about 120 characters of plain text.
8. **Each card carries its slide's heading context** and can be understood without the slide.
9. Cards run in slide order. Where a deck has a card for what something *is* and one for
   what it *does*, the "is" card comes first.
10. Figures are on the back, and each one shows what its card tests.
11. Only what the source supports. Where sources conflict, the card follows the slide and
    `Extra` says so plainly. A description is never turned into a definition.

## What to check

- **Truth.** Is each card supported by the line it cites? Flag imported knowledge, a definition
  built from a figure caption, a precise value that rests on the transcript alone, and any card
  whose answer comes only from notes or transcript without the lecturer marking it important.
- **Examinability.** Find every place the lecturer says what he will or will not examine. Is
  anything he disowned carded? Is anything he explicitly stressed missing?
- **Duplication.** One fact tested twice under different wording. Name the pair.
- **Recall target.** Cover the answer, read what is left. Flag label-only clozes, hidden names
  on discrimination cards, uncued set members, and cards that give themselves away.
- **Coverage.** Walk every in-scope line id. Name any with no card.
- **Figures.** Open every image. Is it the figure the card is about? Does the caption or
  `Extra` describe it correctly? Does the picture itself show the answer on a labelling card?
- **Order and context.** Slide order, is-before-does, heading context.

## Do not report these. They have been ruled on, and reporting them wastes the read

- **"Cut this card, it is obvious / trivia / illustrative / guessable."** Slide text is never
  cut on those grounds. If the *card as written* gives itself away, report that and propose a
  rewrite that tests the lecture's specific version. Never recommend deletion of slide text.
- Bold, underline, italics and other formatting or house-style points.
- Overlap with decks for other lectures.
- Card length measured with HTML tags, `Extra` or captions included. Measure plain text of
  the question and answer only, clozes unwrapped.
- The 60% limit applied to one span. It applies to one deletion index across the sentence.
- A missing card for something that is only in the notes or transcript and that the lecturer
  did not mark as important.
- Emphasis you infer. "Stressed" needs his words, quoted. Likewise a disownment: remarks about
  pace ("we'll move on", "I won't go into detail today") are not disownments.

## How to work

- Open every figure before saying anything about it.
- Recompute any number before reporting it.
- Every finding carries its evidence: a line id or an exact quote.
- Counting is not checking. The finding is always in the cards.

## What to hand back

One markdown file, `<slug>-audit.md`, and nothing else. One table per section, in this order:

1. **Wrong** (truth errors, wrong figure, disowned content carded)
2. **Missing** (uncarded line ids; stressed points with no card)
3. **Duplicates**
4. **Gives itself away / wrong recall target** (with a proposed rewrite)
5. **Order and context**
6. **Needs the student's decision** (anything that would remove or re-scope slide text)

Columns: `uid(s)` | `evidence (line id or quote)` | `what is wrong` | `proposed fix`.
End with one line: how many cards you read and how many figures you opened.
