# GUI QA Plan

## Scope
- Verify the existing Crawler Config Manager UI can load locally for user inspection.

## Local Run Command
```powershell
.\.venv\Scripts\python.exe -m uvicorn crawler_app.web:app --host 127.0.0.1 --port 3000
```

## Target URL
- `http://127.0.0.1:3000/`

## Checks
- Root route returns HTTP 200.
- Existing config list page renders without TemplateResponse errors.
- Browser is opened for user inspection.

