# Science Diagram Maker

Live app: [https://science-diagram-maker-cc51.onrender.com](https://science-diagram-maker-cc51.onrender.com). The free Render service may take about 50 seconds to wake up.

The app asks Gemini for animated SVG diagrams for five GCSE science concepts, validates each SVG, and lets a reviewer approve or reject it. The five saved results load from `data/results.json` without making an API call. The active generation model is `gemini-3.6-flash`.

## Run locally

```powershell
git clone https://github.com/Kshitij9137/science-diagram-maker.git
cd science-diagram-maker
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

Add your Gemini API key to `.env` as `GEMINI_API_KEY=...`, then start the app:

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. To generate or regenerate diagrams, run:

```powershell
python -m scripts.generate_all
python -m scripts.generate_all --only 4
python -m scripts.generate_all --only 4 --force
```

The generator saves results even when validation fails; failed results remain marked as `failed` in `data/results.json`. Install development dependencies and run the tests with:

```powershell
pip install -r requirements-dev.txt
pytest
```

## Saved results

| # | Concept | Result | Estimated cost (USD) | Retries (API / validation) |
|---|---------|--------|----------------------|----------------------------|
| 1 | Pythagoras' theorem | Pass | $0.007648 | 3 / 0 |
| 2 | Parts of a circle | Pass | $0.004837 | 2 / 0 |
| 3 | Series circuit | Fail | $0.008737 | 3 / 1 |
| 4 | Photosynthesis | Pass | $0.038887 | 0 / 0 |
| 5 | States of matter | Fail | $0.009002 | 6 / 1 |

These are paid-tier cost estimates; Gemini's free tier charges $0. Results 1, 2, 3, and 5 were generated with `gemini-3.5-flash-lite`; result 4 was generated with `gemini-3.6-flash`. New generations use the current model in `app/config.py`.

## SVG checks

Each generated diagram is checked for:

1. Valid XML with an `<svg>` root; DOCTYPE and ENTITY declarations are rejected.
2. Drawing bounds within the SVG `viewBox`.
3. A non-empty `<title>` and at least three text labels.
4. At least one animation (CSS keyframes count only when used by an animation declaration).
5. Security: no script or embedded active content, event-handler attributes, or external references.

If a check fails, the model gets one correction attempt with the failed checks and their reasons. Each attempt and its token usage is recorded in the result.

## What failed and what I learned

- Gemini returned intermittent 429/503 responses. The generator retries these with backoff and honors Gemini's suggested delay where available.
- The saved series-circuit result (concept 3) still fails the bounds check: the checker detects labels and animated circles extending outside the viewBox, even after its one correction attempt.
- The saved states-of-matter result (concept 5) still fails the bounds check because two text labels extend past the right edge, even after its one correction attempt.
- Photosynthesis (concept 4) was generated successfully with `gemini-3.6-flash` and passed all five checks. Results were saved by the generator, not edited to hide failures.

## Reviews

Approve/reject choices and notes are stored in browser `localStorage`, keyed by concept ID. This survives refreshes and works on a host with an ephemeral disk, but reviews are local to each browser and are not shared across reviewers.

## With one more day

- Improve viewBox measurement for SVG paths and animated elements.
- Render diagrams headlessly to detect visual overlap and layout problems that bounds checks cannot catch.
- Store reviews server-side so reviewers can share decisions.

## AI tools used
- Claude: planning and code generation.
- Copilot: implementation assistance, test updates, and README editing.
- Gemini: generated the science diagrams through the application.
