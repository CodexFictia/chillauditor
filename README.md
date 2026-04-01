# AI UX Audit → Notion Report Generator

This app does four things:
1. Accepts a UI screenshot upload.
2. Sends it to the OpenAI Responses API for vision-based UX auditing.
3. Auto-scores usability, design consistency, brand/style fidelity, and UX quality.
4. Creates a full Notion audit page with a generated report in markdown.

## What it is built for
- Fast screenshot-based UX audits
- Product/PM review workflows
- Design QA and brand consistency reviews
- A Notion-centric audit process that stays editable after generation

## Prerequisites
- Python 3.10+
- An OpenAI API key
- A Notion internal integration token
- A Notion database or data source that your integration can edit

## 1) Install
```bash
pip install -r requirements.txt
```

## 2) Set environment variables
Copy `.env.example` into your shell environment or a local `.env` loader of your choice.

Required:
- `OPENAI_API_KEY`
- `NOTION_TOKEN`
- `NOTION_DATABASE_ID`

Optional:
- `OPENAI_MODEL` (defaults to `gpt-5.4`)
- `NOTION_VERSION` (defaults to `2026-03-11`)

## 3) Run
```bash
streamlit run app.py
```

## 4) Minimal Notion database schema
The app tries to adapt to your schema, but these fields are recommended:
- `Name` → title
- `Client` → rich_text
- `Screen/Flow` → rich_text
- `Audit Date` → date
- `Overall Score` → number
- `Priority` → select or status

Only the title field is mandatory. If the others exist with those names and types, the app will populate them.

## 5) How the Notion report is generated
The app creates a new page under your database/data source and sends the report body as markdown. This keeps the output close to your UX audit template while remaining editable in Notion.

## Notes
- This is screenshot-based analysis. For full journey audits, run it on multiple screens and combine the reports.
- The AI scores only what is visible on the screen. It does not magically inspect hidden states.
- If your Notion workspace uses a different schema, edit `build_notion_properties()` in `app.py`.

## Good next upgrades
- Multi-screenshot flow audits
- OCR extraction for dense dashboards
- Store screenshots in Notion as file/image blocks
- Generate Jira tickets from High severity issues
- Batch audit a folder of screenshots
