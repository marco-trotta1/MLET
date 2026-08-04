# Doc update spec — post-Kratzert, post-merge

Five edits across three files. Every edit **replaces** text; none appends.
House rule: docs get overwritten when behavior changes.

The handoff listed three edits. Reading the files turned up two more, one of
which is a false statement currently on `main`.

**Sequencing.** Edits 1 and 3 depend on the issue being filed (they cite its
number and date). Edits 2, 4, and 5 can be made now.

---

## Edit 1 — `docs/methods/NEURALHYDROLOGY_PROVENANCE.md`, lines 67–73

**Why: the current text is false.** It reads "Both are reported upstream."
Only defect 1 was reported, and by private email to a maintainer, which is not
an upstream report. Defect 2 has never been reported anywhere.

This is the one edit that is a correctness fix rather than an update, and it
should be made even if the rest of this spec is deferred.

Replace the entire `### Disposition` section with:

```markdown
### Disposition

Defect 2 (clear-sky radiation) was raised with Frederik Kratzert by email on
2026-07-26. He replied 2026-07-28 confirming it appeared to be a bug and
inviting a pull request.

Both defects were then filed as a single upstream issue on <DATE>
(<ISSUE_URL>), which records the numbers, the downstream propagation into
`datautils/climateindices.py`, and an open question about whether the
hardcoded `alpha = 1.26` absorbed part of defect 1's error during its CAMELS
calibration.

They are being submitted as two pull requests. The clear-sky fix is a single
constant with maintainer agreement already in hand. The Priestley-Taylor fix
is a 2.451x behavior change that invalidates cached climate indices for
existing users, so it is separated to avoid holding an agreed fix behind an
unresolved one.

Regression tests in `tests/test_reference_fao56_radiation.py` and
`tests/test_reference_priestley_taylor.py` pin the corrected values **and** the
ratios to the defective forms, so a future re-port cannot silently reintroduce
either.
```

**Note the numbering hazard.** In this file the Priestley-Taylor defect is
numbered 1 and clear-sky is numbered 2. Everywhere else — `UPSTREAM.md`, the
issue draft, the PR specs, the handoff — the numbering is reversed. The
replacement text above uses *this file's* numbering deliberately. Do not
"fix" it to match the others without renumbering the section headings at lines
45 and 59 as well.

---

## Edit 2 — `docs/methods/NEURALHYDROLOGY_PROVENANCE.md`, lines 93–98

**Why:** the closing paragraph names the neuralhydrology CAMELS results as the
strongest evidence against MLET's central assumption. That is no longer true.
A named expert has raised a sharper objection that attacks the assumption
directly rather than by benchmark outcome.

Replace from "The strongest published evidence" through the end of the file
with:

```markdown
corrected two defects in what it ported. The strongest objection to MLET's
central design assumption — that keeping the water balance visible is worth the
accuracy it costs — also comes from this direction, and is now twofold. The
published CAMELS results are the benchmark evidence that an unconstrained
sequence model may simply do better. The sharper objection is Frederik
Kratzert's, raised in correspondence on 2026-07-28: that conserving the mass of
*uncertain* inputs may not be desirable in the first place. Both are recorded
in [hybrid model scaffold](HYBRID_MODEL_SCAFFOLD.md) as conditions any future
hybrid result must address.
```

Keep the preceding sentence ("MLET is not a neuralhydrology fork...") intact —
the replacement picks up mid-sentence at "corrected two defects".

---

## Edit 3 — `src/mlet/reference/UPSTREAM.md`, lines 59–60

**Why:** same false claim as edit 1, milder form. "This was reported upstream"
was true-ish for defect 1 by email, but points at a disposition section that
was itself wrong.

Replace:

```markdown
This was reported upstream; see `docs/methods/NEURALHYDROLOGY_PROVENANCE.md`
for the disposition.
```

with:

```markdown
Reported to the maintainer by email 2026-07-26 and confirmed 2026-07-28; filed
upstream with the defect in section 4. See
`docs/methods/NEURALHYDROLOGY_PROVENANCE.md` for the current disposition.
```

---

## Edit 4 — `src/mlet/reference/UPSTREAM.md`, section 4, after line 101

**Why:** this file documents the defect but not its reach. The 2.451x error
does not stop at `pet.py` — it lands in two dynamic features that anyone
training on CAMELS-derived climate indices has been consuming. That is the
part a future reader needs and cannot reconstruct from what is written.

This is the one place in the spec where new text is added rather than
replacing, because no existing sentence makes the claim. Insert before the
`### 5. Priestley-Taylor alpha` heading:

```markdown
#### Downstream reach

The defect does not stop at `pet.py`. `datautils/climateindices.py:71` calls
`get_priestley_taylor_pet`, and line 172 derives `aridity = pet_mean / p_mean`
from the result. Both `pet_mean` and `aridity` are written as dynamic
climate-index features (`new_features[i, 1]` and `[i, 2]`).

Every user of `precalculate_dyn_climate_indices` therefore holds two features
that are 2.451x too small, uniformly. The clear-sky defect in section 1 reaches
the same two features, though its magnitude varies with basin elevation rather
than being constant.

The consequence for MLET is that **any upstream-derived aridity or PET feature
is unusable without regeneration**, and the consequence for upstream is that
correcting the defect makes cached indices inconsistent with regenerated ones
with nothing raising an error. That is why the fix is being proposed as a
separate pull request from the clear-sky fix.
```

---

## Edit 5 — `docs/methods/HYBRID_MODEL_SCAFFOLD.md`, lines 79–85

**Why:** condition 3 currently frames CAMELS as the thing to beat. Kratzert's
objection is not a benchmark result, so it cannot be answered by winning a
benchmark — it needs a differently *shaped* test, and the doc should say what
that shape is.

Replace item 3 and the sentence that follows it:

```markdown
3. Evidence the hybrid framing beats a well-configured pure LSTM on the same
   splits, or an honest report that it does not. The neuralhydrology CAMELS
   results are the strongest published evidence that it may not.

4. An answer to the objection Frederik Kratzert raised in correspondence on
   2026-07-28: that inputs and targets carry uncertainty, so conserving the
   mass of uncertain inputs may not be desirable in the first place.

   This bites hard here specifically. `README.md` commits MLET to inferring
   irrigation from soil-moisture increases precipitation cannot explain
   whenever grower records are absent — and irrigation is usually the largest
   term in the balance and usually unrecorded. A model that closes the balance
   is being made to conserve an inferred quantity, which converts inference
   error into state error that persists and compounds across the season. An
   unconstrained model can absorb the same error and move on.

   This cannot be settled by a benchmark win, because a win averaged over both
   cases would hide it. It requires evaluation stratified by whether irrigation
   was recorded or inferred, frozen before running. If the hybrid wins only
   where records exist, then what the constraint buys is the ability to exploit
   a trustworthy input rather than physical realism — a materially narrower
   claim than the one usually made for physically constrained models. The
   protocol is `docs/evaluation/2026-07-28-HYBRID_VS_LSTM_PROTOCOL.md`.

None of the above is in scope for the plan that created this scaffold.
```

Note the renumbering: the old item 3 splits into 3 and 4. Confirm nothing else
in the repo cites "condition 3" of this section by number before editing.

---

## Verification

- [ ] `./scripts/verify.sh` — docs-only changes should not move the 585-test
      count. If it does, something other than docs was touched.
- [ ] `grep -rn "reported upstream" docs/ src/` returns nothing unqualified.
- [ ] `grep -rn "strongest published evidence" docs/` returns nothing — the
      phrase is retired by edit 2.
- [ ] Cross-file numbering: `PROVENANCE.md` calls Priestley-Taylor "defect 1";
      everything else calls it "defect 2". Either is fine, mixed is not.
      Decide once and grep to confirm.
- [ ] `<DATE>` and `<ISSUE_URL>` placeholders in edit 1 are filled.
