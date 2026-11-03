# Run the complete application locally

Use Python 3.12+ and Node 22.12+ (Node 24 also works). From this repository:

```sh
./run.sh
```

The launcher installs pinned Python dependencies and locked frontend packages, builds the UI, creates the SQLite database, prepares a small fictional demo ranking on first use, and starts one API/UI service on port 8000. Set `PORT` to use a different free port. Existing candidate data and jobs are preserved. To reuse a Python environment, set `APP_VENV` to its directory.

1. Open the application through your local machine's port 8000 or your development host's port access.
2. Open Rankings and select **Senior AI Engineer — demo** to see the initial result.
3. Open Candidates to inspect profiles, career histories, skills and model features.
4. To use your own candidates, choose a JSONL file in **Import candidates**. Each nonempty line is one candidate object. Imports are additive, with matching IDs updated. Invalid imports make no database changes. Uploads are limited to 50 MiB; larger datasets can be supplied through `CANDIDATES_PATH` inside `DATA_DIR`.
5. Create a job with its full description, open Pipeline and run ranking. The default run uses the current database candidates; an imported dataset can also be ranked on its own. Open the completed run's rankings to inspect scores and supporting evidence.

An example JSONL record (the name is fictional):

```json
{"candidate_id":"EXAMPLE_001","anonymized_name":"Example Engineer","profile":{"current_title":"ML Engineer","summary":"Builds Python retrieval and recommendation systems","years_of_experience":6},"skills":[{"name":"Python","proficiency":"expert","duration_months":60,"endorsements":10}],"career_history":[{"company":"Example Team","title":"ML Engineer","description":"Deployed retrieval models to production","duration_months":48}],"education":[],"redrob_signals":{}}
```

The CPU model combines TF-IDF text similarity, skills explicitly mentioned in the job, and career evidence. It runs without external AI credentials or model downloads. Scores express profile matches, not calibrated hiring probabilities. Assessments of real hiring quality require representative real data and human review. The original challenge CLI retains its specialized scoring when no custom job description is supplied.

SQLite and per-run model artifacts live in `precomputed/` by default. Set `DATA_DIR` before starting to use another persistent directory. Do not delete a database to refresh candidate data; use the import flow. To create a consistent backup without overwriting an existing file:

```sh
venv/bin/python -m backend.manage backup ./backups/candidates.sqlite
```

To run regression checks after installing development dependencies:

```sh
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q
# With the application running and Chromium available:
npm run test:e2e --prefix frontend
```

Deployment is a separate next step; see DEPLOYMENT.md when local validation is complete.
