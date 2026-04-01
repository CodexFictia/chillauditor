import base64
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from PIL import Image

import requests
import streamlit as st

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")
NOTION_VERSION = os.getenv("NOTION_VERSION", "2022-06-28")

st.set_page_config(page_title="AI UX Audit", page_icon="🧪", layout="wide")

HEURISTICS = [
    "visibility_of_system_status",
    "match_between_system_and_real_world",
    "user_control_and_freedom",
    "consistency_and_standards",
    "error_prevention",
    "recognition_over_recall",
    "flexibility_and_efficiency",
    "aesthetic_and_minimalist_design",
    "help_users_recover_from_errors",
    "help_and_documentation",
]

DESIGN_FIELDS = [
    "visual_consistency",
    "typography_consistency",
    "color_system_usage",
    "spacing_and_layout_grid",
    "component_reusability",
    "icon_style_fidelity",
    "motion_readiness",
    "brand_alignment",
]

UX_FIELDS = [
    "navigation_clarity",
    "cta_clarity",
    "cognitive_load",
    "accessibility",
    "responsiveness_readiness",
]

# Checklist items mapped to AI score keys (score >= 4 → checked)
USABILITY_CHECKLIST = [
    ("System status is visible (loading, feedback)", "visibility_of_system_status"),
    ("Language matches user understanding", "match_between_system_and_real_world"),
    ("Undo / Back options exist", "user_control_and_freedom"),
    ("UI patterns are consistent", "consistency_and_standards"),
    ("Errors are prevented proactively", "error_prevention"),
    ("Recognition > recall (autofill, suggestions)", "recognition_over_recall"),
    ("Supports beginner + expert users", "flexibility_and_efficiency"),
    ("Minimal and focused design", "aesthetic_and_minimalist_design"),
    ("Clear error messages with recovery", "help_users_recover_from_errors"),
    ("Help/documentation available", "help_and_documentation"),
]

DESIGN_CHECKLIST = [
    ("Colors follow brand palette", "color_system_usage"),
    ("Typography consistent across screens", "typography_consistency"),
    ("Layout follows grid/spacing rules", "spacing_and_layout_grid"),
    ("Components reused properly", "component_reusability"),
    ("Icons consistent (future-ready)", "icon_style_fidelity"),
]

UX_CHECKLIST = [
    ("Navigation intuitive", "navigation_clarity"),
    ("CTAs clear and visible", "cta_clarity"),
    ("Low cognitive load", "cognitive_load"),
    ("Accessibility maintained (contrast, size)", "accessibility"),
    ("Responsive across devices", "responsiveness_readiness"),
]

SYSTEM_PROMPT = """
You are a senior UX auditor, design systems architect, and accessibility specialist with 15+ years of experience auditing B2B and B2C products. You are fluent in Nielsen Norman Group heuristics, WCAG 2.1/2.2 AA/AAA guidelines, Gestalt psychology, atomic design methodology, 8-point grid systems, and platform conventions (Material Design 3, Apple HIG, Fluent Design).

Analyze the uploaded product screenshot as a real production interface. Be precise, evidence-based, and actionable.

═══════════════════════════════════════════════
SCORING DIMENSIONS & WHAT EACH ONE MEANS
═══════════════════════════════════════════════

── USABILITY HEURISTICS (Nielsen Norman Group) ──

1. visibility_of_system_status
   What to look for: Loading indicators, progress bars, skeleton screens, active/selected states, real-time feedback, toast/snack notifications, breadcrumbs, step indicators, badge counts, sync status.
   Score 5: Status is always visible and immediately understandable without any ambiguity.
   Score 3: Status exists but may be delayed, hidden, or easy to miss.
   Score 1: No feedback at all — user has no idea what the system is doing.

2. match_between_system_and_real_world
   What to look for: Plain language vs jargon, familiar metaphors (shopping cart, trash can), date/time in human format, error messages in plain English, labels that match what users call things.
   Score 5: Every label, icon, and message maps naturally to real-world concepts.
   Score 3: Some technical or ambiguous language present.
   Score 1: Heavy jargon, confusing terminology, or metaphors that don't transfer.

3. user_control_and_freedom
   What to look for: Undo/redo, cancel buttons on every modal and form, back navigation, exit flows, ability to dismiss notifications, destructive actions are reversible or confirm-gated.
   Score 5: Every action is reversible or explicitly confirm-gated; escape hatches are obvious.
   Score 3: Some flows have no undo or back option; modals lack cancel.
   Score 1: Actions are permanent with no warning; users are trapped in flows.

4. consistency_and_standards
   What to look for: Same interaction for same action across all screens, platform conventions followed (e.g., left nav on desktop, bottom nav on mobile), consistent button styles/labels, no two elements that look the same but behave differently.
   Score 5: Perfect internal and external consistency; follows platform HIG.
   Score 3: Occasional inconsistencies in labeling or component behavior.
   Score 1: Wildly inconsistent — same action has different affordances; platform norms ignored.

5. error_prevention
   What to look for: Inline validation before submit, disabled states for invalid actions, confirmation dialogs for destructive actions, forgiving input formats (phone, date, credit card), constraints that prevent invalid entry.
   Score 5: Errors are structurally impossible or caught before they happen.
   Score 3: Some validation exists but incomplete; users can still trigger common errors.
   Score 1: No validation, no guards; users frequently hit errors preventable by design.

6. recognition_over_recall
   What to look for: Autofill/autocomplete, recently used items, visible options vs buried menus, inline labels (not just placeholder text), persistent contextual help, search with suggestions.
   Score 5: All options are visible or easily surfaced; nothing requires memorization.
   Score 3: Some information is hidden behind interactions that could be visible.
   Score 1: Users must memorize system state or options; nothing is surfaced proactively.

7. flexibility_and_efficiency
   What to look for: Keyboard shortcuts, bulk actions, saved presets/favorites, progressive disclosure for advanced options, power-user shortcuts, personalization, quick actions.
   Score 5: Both novice and expert paths are optimized; accelerators exist and are discoverable.
   Score 3: Only one user type is catered to; no accelerators or advanced options.
   Score 1: One-size-fits-all with no flexibility; experts are forced through beginner flows.

8. aesthetic_and_minimalist_design
   What to look for: No redundant information, visual hierarchy is clear, whitespace used intentionally, no competing calls-to-action, irrelevant content removed, signal-to-noise ratio is high.
   Score 5: Every element earns its place; visual hierarchy is immediate and effortless.
   Score 3: Some clutter or competing elements that reduce focus.
   Score 1: Overwhelming — competing elements, redundant info, no clear focal point.

9. help_users_recover_from_errors
   What to look for: Error messages that explain what happened + why + how to fix it, inline field-level errors, no generic "Something went wrong", no error codes exposed to users, recovery paths are obvious.
   Score 5: All error states have clear, human-readable messages with explicit recovery paths.
   Score 3: Some errors are vague or lack recovery instructions.
   Score 1: Cryptic errors, raw system messages, or no error messaging at all.

10. help_and_documentation
    What to look for: Contextual tooltips, ? icons, onboarding tours, empty state guidance, FAQ links, in-app help panel, progressive disclosure of complex features.
    Score 5: Help is contextually available without leaving the flow; documentation is surfaced proactively.
    Score 3: Help exists but is buried or requires leaving the current context.
    Score 1: No help, no tooltips, no documentation; users are on their own.

── DESIGN SYSTEM FIELDS ──

11. visual_consistency
    What to look for: Same border-radius tokens across components, consistent shadow elevation levels, padding/margin follows a spacing scale (4pt, 8pt, 16pt…), no one-off custom styles.
    Score 5: Everything looks like it came from one cohesive system.
    Score 1: Components look designed by different people with no shared tokens.

12. typography_consistency
    What to look for: Max 2-3 font families, type scale (H1–body–caption), consistent font weights for hierarchy, no random font sizes, line-height and letter-spacing follow a system.
    Score 5: Clear typographic hierarchy; consistent scale; easy to read at all levels.
    Score 1: Mixed fonts, random sizes, inconsistent weights, poor readability.

13. color_system_usage
    What to look for: Primary/secondary/tertiary palette, semantic colors (success=green, error=red, warning=amber), color used consistently for the same meaning, no random decorative colors.
    Score 5: Color system is coherent, semantic, and consistently applied.
    Score 1: Colors are arbitrary, inconsistent, and convey no semantic meaning.

14. spacing_and_layout_grid
    What to look for: 8pt/4pt grid adherence, consistent margins/padding, visual rhythm, gutters consistent in grids/lists, alignment (left, right, center used intentionally).
    Score 5: Strict grid adherence; spacing creates clear visual rhythm.
    Score 1: Arbitrary spacing; elements feel randomly placed.

15. component_reusability
    What to look for: Buttons, inputs, cards, badges — do they look reused from a library or are they one-offs? Same variants used across similar contexts.
    Score 5: Components are clearly atomic; variants are consistent and reused.
    Score 1: Every component looks custom-built; no shared patterns visible.

16. icon_style_fidelity
    What to look for: Same icon library used throughout, consistent stroke weight, filled vs outlined icons not mixed, icon size consistent with touch targets, icons meaningful without labels.
    Score 5: One icon system, consistent weight/style, all icons are immediately legible.
    Score 1: Mixed icon sets, inconsistent sizes, ambiguous icons.

17. motion_readiness
    What to look for: Evidence of transition placeholders, consistent hover/focus/active states, whether the design has room for micro-interactions without cluttering.
    Score 5: States are fully defined; design is clearly ready for motion.
    Score 3: Some states defined but motion tokens not visible.
    Score 1: No state changes visible; motion would be impossible to layer in.

18. brand_alignment
    What to look for: Brand colors used correctly, brand voice in copy, logo placement and sizing, overall visual personality matches the brand (formal, playful, minimal, bold).
    Score 5: The screen is unmistakably on-brand in every detail.
    Score 1: Generic or off-brand — could belong to any product.

── UX QUALITY FIELDS ──

19. navigation_clarity
    What to look for: User can tell where they are, where they came from, where they can go. Primary nav is visible and labeled. Active states show current location. Deep links feel navigable.
    Score 5: Wayfinding is instant; user is never lost.
    Score 1: No orientation cues; primary navigation is absent or ambiguous.

20. cta_clarity
    What to look for: One clear primary CTA per screen, high contrast button, action-oriented label (verb + noun: "Save changes", "Start free trial"), CTA position follows F/Z scan pattern.
    Score 5: Primary action is unmissable; secondary actions are clearly subordinate.
    Score 1: Multiple competing CTAs; labels are vague (e.g., "Submit"); action is buried.

21. cognitive_load
    What to look for: Number of decisions per screen, form field count, use of progressive disclosure, chunking of information, reading level of copy, visual clutter.
    Score 5: Minimal decisions required; information is chunked logically; effortless to process.
    Score 1: Overwhelming — too many choices, too much text, too many inputs at once.

22. accessibility
    What to look for: Text contrast ratio (WCAG AA = 4.5:1 for body, 3:1 for large text), touch target size (min 44×44pt), focus indicators, alt text implied by design, color not the only differentiator.
    Score 5: Passes WCAG 2.1 AA on all visible criteria; inclusive design throughout.
    Score 3: Some contrast or sizing issues; partially accessible.
    Score 1: Fails multiple WCAG AA criteria; inaccessible to users with disabilities.

23. responsiveness_readiness
    What to look for: Whether layout implies fluid/fixed behavior, whether touch targets are appropriately sized, whether content would reflow gracefully at different breakpoints.
    Score 5: Design clearly adapts; responsive patterns are evident.
    Score 1: Fixed/pixel-perfect layout with no signs of responsive consideration.

═══════════════════════════════════════════════
SEVERITY LEVELS FOR ISSUES
═══════════════════════════════════════════════
High   → Blocks task completion, causes data loss, fails accessibility, or significantly damages trust.
Medium → Slows users down, causes confusion, or creates friction in key flows.
Low    → Minor polish issue, inconsistency, or nice-to-have improvement.

═══════════════════════════════════════════════
YOUR PRINCIPLE LIBRARY (use these exact names)
═══════════════════════════════════════════════
The following 10 heuristics are the canonical reference. For each issue you raise, map it to one or more of these entries using the exact heuristic name and principle statement:

1.  Visibility of System Status       → "System should always inform users about what is happening."
    Category: System feedback | Common checks: Feedback, Clarity

2.  Match Between System & Real World → "Use familiar language and concepts."
    Category: Content | Common checks: Clarity

3.  User Control & Freedom            → "Users should be able to undo or exit easily."
    Category: Navigation | Common checks: Error prevention, Affordance

4.  Consistency & Standards           → "Maintain uniformity across UI."
    Category: Visual design | Common checks: Consistency

5.  Error Prevention                  → "Prevent issues before they occur."
    Category: Error handling | Common checks: Error prevention, Feedback

6.  Recognition Over Recall           → "Reduce memory load."
    Category: Content | Common checks: Clarity, Affordance

7.  Flexibility & Efficiency          → "Support different user types."
    Category: Other | Common checks: Affordance, Clarity

8.  Minimalist Design                 → "Remove unnecessary elements."
    Category: Visual design | Common checks: Clarity, Consistency

9.  Error Recovery                    → "Help users fix issues."
    Category: Error handling | Common checks: Feedback, Error prevention

10. Help & Documentation              → "Provide guidance when needed."
    Category: Other | Common checks: Clarity, Feedback

CATEGORY taxonomy (use exactly one per issue):
  Navigation | Content | Accessibility | Forms | Visual design | System feedback | Error handling | Other

COMMON CHECKS taxonomy (use one or more per issue, from this list only):
  Clarity | Consistency | Feedback | Affordance | Error prevention | Accessibility

═══════════════════════════════════════════════
SCORING RULES
═══════════════════════════════════════════════
- Every score is an integer 1–5.
- 5 = excellent (best practice), 4 = good (minor issues), 3 = acceptable (noticeable flaws), 2 = poor (significant problems), 1 = severe (broken/absent).
- Only score what is visible. Do not invent states not shown.
- Score conservatively for anything that requires multiple screens to verify (e.g., consistency, responsiveness). Note limitations in the "notes" array.
- Your issues list must only reference elements actually visible in the screenshot.

Return STRICT JSON only — no prose, no markdown, no explanation outside the JSON.

JSON schema to return:
{
  "screen_name": "string — infer a descriptive name from visible page headings, breadcrumbs, and labels",
  "page_description": "string — EXACTLY 250 words. Structure your description as follows: (1) FEATURE IDENTITY: State clearly what module, feature, or screen this appears to be — infer from headings, nav labels, table column names, button labels, and any visible text. (2) CONTENT & DATA: Describe what data or content is currently displayed — what columns, charts, widgets, empty states, or filled states you can see and what they represent. If filters or date ranges are visible, note what is currently selected and what it implies about the data scope. (3) USER WORKFLOW: Describe the primary task a user would perform on this page — what they likely arrived here to do, what actions are available (buttons, filters, links), and the expected flow. (4) UX IMPRESSION: In 2–3 sentences give your immediate UX impression — does the layout support the workflow? Is the information hierarchy clear? Does the density feel appropriate for the user type? Write in the tone of a senior UX consultant presenting a live walkthrough. Do not pad with filler. Every sentence must add insight.",
  "summary": "string — 2–3 sentence executive headline summarising the single most important UX finding on this page",
  "scores": {
    "visibility_of_system_status": 1,
    "match_between_system_and_real_world": 1,
    "user_control_and_freedom": 1,
    "consistency_and_standards": 1,
    "error_prevention": 1,
    "recognition_over_recall": 1,
    "flexibility_and_efficiency": 1,
    "aesthetic_and_minimalist_design": 1,
    "help_users_recover_from_errors": 1,
    "help_and_documentation": 1,
    "visual_consistency": 1,
    "typography_consistency": 1,
    "color_system_usage": 1,
    "spacing_and_layout_grid": 1,
    "component_reusability": 1,
    "icon_style_fidelity": 1,
    "motion_readiness": 1,
    "brand_alignment": 1,
    "navigation_clarity": 1,
    "cta_clarity": 1,
    "cognitive_load": 1,
    "accessibility": 1,
    "responsiveness_readiness": 1
  },
  "strengths": ["string"],
  "issues": [
    {
      "title": "string",
      "severity": "High|Medium|Low",
      "category": "Navigation|Content|Accessibility|Forms|Visual design|System feedback|Error handling|Other",
      "common_checks": ["Clarity|Consistency|Feedback|Affordance|Error prevention|Accessibility"],
      "principles": ["exact heuristic name from the library above"],
      "evidence": "string — quote what you see in the screenshot",
      "recommendation": "string — specific and implementation-ready"
    }
  ],
  "quick_wins": ["string"],
  "notes": ["string"],
  "report_title": "string"
}
""".strip()


def average(values: List[int]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def clean_json(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Model did not return JSON.")
    return json.loads(text[start : end + 1])


def _bytes_to_base64_png(raw: bytes, source_hint: str = "") -> str:
    """Re-encode raw image bytes as a valid PNG via Pillow and return a data URL.

    Raises a user-friendly ValueError if the bytes aren't a recognisable image.
    """
    if not raw:
        raise ValueError("Received empty content — nothing to encode.")

    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()          # catch truncated / corrupt files early
    except Exception:
        # Try once more without verify (some valid images fail verify but open fine)
        try:
            img = Image.open(io.BytesIO(raw))
        except Exception as exc:
            preview = raw[:120]
            hint = f" (from {source_hint})" if source_hint else ""
            raise ValueError(
                f"Could not read image{hint}. "
                f"Make sure the file/URL points to a real PNG, JPEG, WebP or GIF image.\n"
                f"First bytes received: {preview!r}"
            ) from exc

    # Re-open after verify (verify() leaves the file pointer at EOF)
    img = Image.open(io.BytesIO(raw))
    if img.mode not in ("RGB", "RGBA", "L", "LA"):
        img = img.convert("RGBA" if "A" in img.mode else "RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def file_to_base64(uploaded_file) -> str:
    """Convert an uploaded Streamlit file to a base64 PNG data URL via Pillow."""
    raw = uploaded_file.getvalue()
    return _bytes_to_base64_png(raw, source_hint=uploaded_file.name)


def fetch_url_as_base64(url: str, username: str = "", password: str = "") -> str:
    """Download image from URL (with optional basic auth), re-encode as PNG data URL."""
    auth = (username, password) if username or password else None
    resp = requests.get(
        url,
        auth=auth,
        timeout=60,
        headers={"User-Agent": "Mozilla/5.0"},   # some servers block bare requests
    )
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "").lower()
    if content_type and not content_type.startswith("image/"):
        raise ValueError(
            f"URL did not return an image — Content-Type was '{content_type}'.\n"
            f"Make sure the URL points directly to an image file (PNG, JPEG, WebP, GIF)."
        )

    return _bytes_to_base64_png(resp.content, source_hint=url)


def call_openai(image_input: str, extra_context: str = "") -> Dict[str, Any]:
    """Send image to OpenAI. image_input is either a data URL or a direct image URL."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing.")

    user_prompt = (
        "Audit this screenshot for usability, UX quality, design consistency, brand/color/style fidelity, "
        "and future readiness for icons and motion."
    )
    if extra_context.strip():
        user_prompt += f"\n\nAdditional context from user:\n{extra_context.strip()}"

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_input, "detail": "high"},
                    },
                ],
            },
        ],
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }

    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    if not resp.ok:
        raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text}")
    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError(f"Unexpected OpenAI response shape: {data}")
    return clean_json(content)


def format_issue_md(issue: Dict[str, Any]) -> str:
    principles = ", ".join(issue.get("principles", [])) or "Unspecified"
    common_checks = ", ".join(issue.get("common_checks", [])) or ""
    category = issue.get("category", "")
    meta_parts = [f"**Category:** {category}"] if category else []
    if common_checks:
        meta_parts.append(f"**Common checks:** {common_checks}")
    meta_line = " · ".join(meta_parts)
    return (
        f"### {issue.get('title', 'Issue')}\n"
        f"- **Severity:** {issue.get('severity', 'Medium')}\n"
        + (f"- {meta_line}\n" if meta_line else "")
        + f"- **Heuristics:** {principles}\n"
        f"- **Evidence:** {issue.get('evidence', '')}\n"
        f"- **Recommendation:** {issue.get('recommendation', '')}\n"
    )


def checklist_line(label: str, score: int) -> str:
    mark = "x" if score >= 4 else " "
    return f"- [{mark}] {label} *(score: {score}/5)*"


def build_markdown_report(
    audit: Dict[str, Any],
    project_name: str,
    client_name: str,
    screen_name_override: str = "",
) -> str:
    scores = audit["scores"]
    usability = average([int(scores[k]) for k in HEURISTICS])
    design = average([int(scores[k]) for k in DESIGN_FIELDS])
    ux = average([int(scores[k]) for k in UX_FIELDS])
    overall = round(usability * 0.4 + ux * 0.35 + design * 0.25, 2)
    screen_name = screen_name_override.strip() or audit.get("screen_name") or "Uploaded Screen"

    def list_block(items: List[str]) -> str:
        return "\n".join(f"- {x}" for x in items) if items else "- None"

    issues_md = "\n".join(format_issue_md(i) for i in audit.get("issues", [])) or "No major issues captured."

    usability_checklist = "\n".join(
        checklist_line(label, int(scores[key])) for label, key in USABILITY_CHECKLIST
    )
    design_checklist = "\n".join(
        checklist_line(label, int(scores[key])) for label, key in DESIGN_CHECKLIST
    )
    ux_checklist = "\n".join(
        checklist_line(label, int(scores[key])) for label, key in UX_CHECKLIST
    )

    notes_block = list_block(audit.get("notes", []))

    return f"""# {audit.get('report_title', 'UX Audit Report')}

**Project:** {project_name or 'Untitled Project'}
**Client:** {client_name or 'N/A'}
**Screen / Flow:** {screen_name}
**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## Page Analysis
{audit.get('page_description', '')}

---

## Executive Summary
{audit.get('summary', '')}

## AI Scorecard
- **Usability Score:** {usability}/5
- **Design Score:** {design}/5
- **UX Quality Score:** {ux}/5
- **Overall Score:** {overall}/5

---

## 🔵 Usability Checklist
{usability_checklist}

---

## 🟣 Design System Checklist
{design_checklist}

---

## 🟠 UX Quality Checklist
{ux_checklist}

---

## Key Issues
{issues_md}

## Strengths
{list_block(audit.get('strengths', []))}

## Quick Wins
{list_block(audit.get('quick_wins', []))}

---

## 📸 Attachments
Add screenshots / recordings here

---

## 🧠 Notes
{notes_block}

---

## Recommended Next Actions
1. Fix all High severity items first.
2. Standardize components, spacing, and typography tokens.
3. Define icon and motion rules before adding designed assets.
4. Re-run the audit after revisions.
"""


# ── Notion helpers ────────────────────────────────────────────────────────────

def notion_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def get_database_schema(database_id: str) -> Dict[str, Any]:
    resp = requests.get(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers=notion_headers(),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def build_notion_properties(
    schema: Dict[str, Any],
    project_name: str,
    client_name: str,
    screen_name: str,
    overall_score: float,
) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    schema_props = schema.get("properties", {})

    title_key = next(
        (name for name, meta in schema_props.items() if meta.get("type") == "title"),
        None,
    )
    if not title_key:
        raise RuntimeError("Could not find a title property in the Notion database.")

    title_text = f"{project_name or 'Project'} — {screen_name or 'Audit'}"
    props[title_key] = {"title": [{"type": "text", "text": {"content": title_text[:2000]}}]}

    def maybe_rich_text(name: str, value: str):
        if name in schema_props and schema_props[name]["type"] == "rich_text":
            props[name] = {"rich_text": [{"type": "text", "text": {"content": value[:2000]}}]}

    def maybe_number(name: str, value: float):
        if name in schema_props and schema_props[name]["type"] == "number":
            props[name] = {"number": value}

    def maybe_select(name: str, value: str):
        if name in schema_props and schema_props[name]["type"] in {"select", "status"}:
            key = "select" if schema_props[name]["type"] == "select" else "status"
            props[name] = {key: {"name": value}}

    def maybe_date(name: str, value: str):
        if name in schema_props and schema_props[name]["type"] == "date":
            props[name] = {"date": {"start": value}}

    maybe_rich_text("Client", client_name or "N/A")
    maybe_rich_text("Screen/Flow", screen_name or "Uploaded Screen")
    maybe_date("Audit Date", datetime.now().strftime("%Y-%m-%d"))
    maybe_number("Overall Score", overall_score)
    maybe_select(
        "Priority",
        "High" if overall_score < 3 else "Medium" if overall_score < 4 else "Low",
    )
    return props


def _rt(text: str) -> List[Dict]:
    """Build a rich_text array, handling **bold** markers."""
    result = []
    for seg in re.split(r"(\*\*[^*]+\*\*)", text[:2000]):
        if seg.startswith("**") and seg.endswith("**"):
            result.append({"type": "text", "text": {"content": seg[2:-2]}, "annotations": {"bold": True}})
        elif seg:
            result.append({"type": "text", "text": {"content": seg}})
    return result or [{"type": "text", "text": {"content": text[:2000]}}]


def markdown_to_notion_blocks(md: str) -> List[Dict]:
    """Convert markdown string to a list of Notion block objects."""
    blocks: List[Dict] = []
    for line in md.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif re.match(r"^# [^#]", s):
            blocks.append({"object": "block", "type": "heading_1", "heading_1": {"rich_text": _rt(s[2:])}})
        elif re.match(r"^## [^#]", s):
            blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": _rt(s[3:])}})
        elif re.match(r"^### [^#]", s):
            blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": _rt(s[4:])}})
        elif re.match(r"^- \[[ x]\] ", s):
            checked = s[3] == "x"
            blocks.append({"object": "block", "type": "to_do", "to_do": {"rich_text": _rt(s[6:]), "checked": checked}})
        elif s.startswith("- ") or s.startswith("* "):
            blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rt(s[2:])}})
        elif re.match(r"^\d+\. ", s):
            blocks.append({"object": "block", "type": "numbered_list_item", "numbered_list_item": {"rich_text": _rt(re.sub(r"^\d+\. ", "", s))}})
        else:
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rt(s)}})
    return blocks


def create_notion_page(
    markdown: str,
    project_name: str,
    client_name: str,
    screen_name: str,
    overall_score: float,
) -> str:
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        raise RuntimeError("NOTION_TOKEN or NOTION_DATABASE_ID is missing.")

    schema = get_database_schema(NOTION_DATABASE_ID)
    props = build_notion_properties(schema, project_name, client_name, screen_name, overall_score)
    all_blocks = markdown_to_notion_blocks(markdown)

    # Notion allows max 100 blocks on page creation
    payload = {
        "parent": {"type": "database_id", "database_id": NOTION_DATABASE_ID},
        "properties": props,
        "children": all_blocks[:100],
    }
    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=notion_headers(),
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    page = resp.json()
    page_id = page["id"]
    page_url = page.get("url", "")

    # Append remaining blocks in batches of 100
    remaining = all_blocks[100:]
    while remaining:
        batch, remaining = remaining[:100], remaining[100:]
        patch = requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=notion_headers(),
            json={"children": batch},
            timeout=60,
        )
        patch.raise_for_status()

    return page_url


def compute_summary_scores(audit: Dict[str, Any]) -> Dict[str, float]:
    scores = audit["scores"]
    usability = average([int(scores[k]) for k in HEURISTICS])
    design = average([int(scores[k]) for k in DESIGN_FIELDS])
    ux = average([int(scores[k]) for k in UX_FIELDS])
    overall = round(usability * 0.4 + ux * 0.35 + design * 0.25, 2)
    return {"usability": usability, "design": design, "ux": ux, "overall": overall}


# ── Browser automation ────────────────────────────────────────────────────────

def ensure_playwright_browsers() -> None:
    """Install Playwright Chromium on first run (idempotent)."""
    if st.session_state.get("_pw_checked"):
        return
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        st.session_state["_pw_checked"] = True
    except Exception:
        with st.spinner("Installing Playwright browsers (one-time setup)…"):
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True, capture_output=True,
            )
        st.session_state["_pw_checked"] = True


def _perform_login(page: Any, login_url: str, username: str, password: str) -> None:
    """Navigate to login_url and attempt to fill + submit the login form."""
    page.goto(login_url, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(1_500)

    # Fill username / email
    for sel in [
        "input[type='email']", "input[name='email']", "input[name='username']",
        "input[name='login']", "input[id*='email' i]", "input[id*='user' i]",
        "input[placeholder*='email' i]", "input[placeholder*='username' i]",
        "input[type='text']",
    ]:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.fill(username)
            break

    # Fill password
    loc = page.locator("input[type='password']").first
    if loc.count() and loc.is_visible():
        loc.fill(password)

    # Submit
    submitted = False
    for sel in [
        "button[type='submit']", "input[type='submit']",
        "button:has-text('Log in')", "button:has-text('Login')",
        "button:has-text('Sign in')", "button:has-text('Continue')",
        "button:has-text('Next')",
    ]:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.click()
            submitted = True
            break

    if not submitted:
        page.keyboard.press("Enter")

    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass
    page.wait_for_timeout(1_000)


def discover_pages(
    base_url: str,
    username: str = "",
    password: str = "",
    login_url: str = "",
    max_pages: int = 30,
) -> Dict[str, Any]:
    """
    Two-pass discovery:
      Pass 1 — static: extract every <a href> from the landing page DOM.
      Pass 2 — dynamic: click every visible nav/sidebar/menu element,
               observe URL changes via history.pushState (SPA-friendly),
               navigate back to base and repeat.
    Returns a dict with 'pages' list and 'summary' diagnostic info.
    """
    from playwright.sync_api import sync_playwright

    parsed_base = urlparse(base_url)

    SKIP_EXTS = {".pdf", ".zip", ".png", ".jpg", ".jpeg", ".svg",
                 ".css", ".js", ".ico", ".xml", ".json", ".woff", ".woff2"}

    # Selectors tried in order for the dynamic nav-click pass
    NAV_SELECTORS = [
        "nav a", "aside a",
        "[role='navigation'] a",
        "[aria-label*='nav' i] a", "[aria-label*='menu' i] a", "[aria-label*='sidebar' i] a",
        "[class*='sidebar'] a", "[class*='side-nav'] a", "[class*='sidenav'] a",
        "[class*='nav-item'] a", "[class*='navitem'] a",
        "[class*='menu-item'] a", "[class*='menuitem'] a",
        "[class*='nav-link'] a", "[class*='navlink'] a",
        # non-anchor clickable nav items
        "[role='menuitem']", "[role='treeitem']", "[role='tab']",
        "[class*='nav-item']:not(a)", "[class*='menu-item']:not(a)",
    ]

    def _normalize(url: str) -> str:
        p = urlparse(url.split("#")[0])
        return f"{p.scheme}://{p.netloc}{p.path}" + (f"?{p.query}" if p.query else "")

    def _accept(url: str) -> bool:
        p = urlparse(url)
        return (
            p.netloc == parsed_base.netloc
            and p.scheme in ("http", "https")
            and not any(p.path.lower().endswith(ext) for ext in SKIP_EXTS)
        )

    seen: set = set()
    pages: List[Dict[str, str]] = []
    stats = {"via_href": 0, "via_click": 0, "nav_elements_found": 0, "login_detected": False}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # ── Login ─────────────────────────────────────────────────────────────
        if username and password:
            _perform_login(page, login_url or base_url, username, password)
            stats["login_detected"] = True

        page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2_000)

        base_title = page.title() or base_url
        norm_base = _normalize(base_url)
        seen.add(norm_base)
        pages.append({"url": norm_base, "title": base_title, "source": "base"})

        # ── Pass 1 : static href extraction ───────────────────────────────────
        raw_links = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({href: e.href, text: (e.innerText||'').trim().slice(0,80)}))",
        )
        for link in raw_links:
            if len(pages) >= max_pages:
                break
            href = (link.get("href") or "").strip().split("#")[0]
            if not href or not _accept(href):
                continue
            norm = _normalize(href)
            if norm not in seen:
                seen.add(norm)
                label = link.get("text") or urlparse(norm).path or norm
                pages.append({"url": norm, "title": label[:80], "source": "href"})
                stats["via_href"] += 1

        # ── Pass 2 : click nav / sidebar elements ─────────────────────────────
        if len(pages) < max_pages:
            # Collect candidate elements from all nav selectors
            candidate_handles = []
            for sel in NAV_SELECTORS:
                try:
                    els = page.locator(sel).all()
                    candidate_handles.extend(els)
                except Exception:
                    pass

            stats["nav_elements_found"] = len(candidate_handles)

            clicked_labels: set = set()
            for loc in candidate_handles:
                if len(pages) >= max_pages:
                    break
                try:
                    if not loc.is_visible():
                        continue
                    label = (loc.inner_text() or "").strip()[:60]
                    if not label or label in clicked_labels:
                        continue
                    clicked_labels.add(label)

                    # Prefer reading href without clicking (faster, less side-effects)
                    href = loc.get_attribute("href") or ""
                    if href and not href.startswith("#") and not href.startswith("javascript:"):
                        full = urljoin(base_url, href).split("#")[0]
                        if _accept(full):
                            norm = _normalize(full)
                            if norm not in seen:
                                seen.add(norm)
                                pages.append({"url": norm, "title": label or norm, "source": "nav-href"})
                                stats["via_click"] += 1
                            continue

                    # No usable href → actually click and observe URL change
                    loc.scroll_into_view_if_needed()
                    loc.click()
                    page.wait_for_timeout(700)
                    new_url = page.url.split("#")[0]
                    if _accept(new_url):
                        norm = _normalize(new_url)
                        if norm not in seen:
                            seen.add(norm)
                            title = page.title() or label or norm
                            pages.append({"url": norm, "title": title, "source": "nav-click"})
                            stats["via_click"] += 1

                    # Return to base so the sidebar stays intact for the next click
                    if page.url.rstrip("/") != base_url.rstrip("/"):
                        page.goto(base_url, wait_until="domcontentloaded", timeout=15_000)
                        page.wait_for_timeout(800)

                except Exception:
                    # Single element failure must not abort the whole pass
                    try:
                        page.goto(base_url, wait_until="domcontentloaded", timeout=10_000)
                        page.wait_for_timeout(600)
                    except Exception:
                        pass

        browser.close()

    return {"pages": pages, "stats": stats}


def _interact_before_screenshot(page: Any) -> None:
    """
    Try to reveal real content before screenshotting:
    - Expand collapsed sections
    - Set date-range filters to a wide window so data shows
    - Pick "All" in any visible select/dropdown
    - Dismiss cookie banners / modals
    - Scroll to bottom then back to top so lazy images render
    Failures are silently swallowed — this is best-effort.
    """
    try:
        # 1. Dismiss common overlay patterns (cookie banners, welcome modals)
        for sel in [
            "button:has-text('Accept')", "button:has-text('Got it')",
            "button:has-text('Dismiss')", "button:has-text('Close')",
            "button:has-text('OK')", "[aria-label='Close']",
            "[class*='cookie'] button", "[class*='banner'] button",
            "[class*='modal'] button[class*='close']",
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible():
                    loc.click()
                    page.wait_for_timeout(400)
                    break
            except Exception:
                pass

        # 2. Try to set date-range / period filters to the widest available option
        for sel in [
            "select[name*='period' i]", "select[name*='range' i]", "select[name*='date' i]",
            "select[id*='period' i]", "select[id*='range' i]", "select[id*='date' i]",
            "select[class*='period' i]", "select[class*='range' i]",
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible():
                    # Try to pick the last (usually "All time" / "Max") option
                    options = loc.locator("option").all()
                    if options:
                        last_val = options[-1].get_attribute("value")
                        if last_val:
                            loc.select_option(value=last_val)
                            page.wait_for_timeout(600)
            except Exception:
                pass

        # 3. Try common "All" or "Show all" selects / buttons
        for sel in [
            "select option[value='all' i]", "select option[value='' i]",
            "button:has-text('Show all')", "button:has-text('View all')",
            "button:has-text('Load more')",
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible():
                    loc.click()
                    page.wait_for_timeout(500)
            except Exception:
                pass

        # 4. Expand any collapsed accordion / expand-all buttons
        for sel in [
            "button:has-text('Expand all')", "button:has-text('Expand')",
            "[aria-expanded='false']",
        ]:
            try:
                locs = page.locator(sel).all()
                for loc in locs[:4]:          # limit to avoid exploding huge trees
                    if loc.is_visible():
                        loc.click()
                        page.wait_for_timeout(300)
            except Exception:
                pass

        # 5. Slow-scroll to bottom so lazy-load images/charts render, then scroll back
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(800)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(400)

    except Exception:
        pass   # never block a screenshot


def capture_pages(
    page_urls: List[str],
    username: str = "",
    password: str = "",
    login_url: str = "",
    on_progress=None,          # optional callback(i, url, title)
) -> List[Dict[str, Any]]:
    """Navigate to each URL, interact to reveal real content, then screenshot."""
    from playwright.sync_api import sync_playwright

    results: List[Dict[str, Any]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        if username and password:
            _perform_login(page, login_url or page_urls[0], username, password)

        for i, url in enumerate(page_urls):
            if on_progress:
                on_progress(i, url, "")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(1_500)            # initial render settle

                _interact_before_screenshot(page)       # reveal real content
                page.wait_for_timeout(600)              # let any triggered loads finish

                title = page.title() or url
                shot_bytes = page.screenshot(full_page=True, type="png")
                b64 = base64.b64encode(shot_bytes).decode("utf-8")
                results.append({
                    "url": url,
                    "title": title,
                    "screenshot_bytes": shot_bytes,
                    "screenshot_b64": b64,
                })
                if on_progress:
                    on_progress(i, url, title)
            except Exception as exc:
                results.append({"url": url, "title": url, "error": str(exc)})

        browser.close()

    return results


# ── Multi-page report ──────────────────────────────────────────────────────────

def build_multipage_report(
    page_audits: List[Dict[str, Any]],
    project_name: str,
    client_name: str,
    base_url: str = "",
) -> str:
    """Aggregate per-page audits into a single combined markdown report."""
    if not page_audits:
        return "# No pages audited."

    n = len(page_audits)

    # ── Aggregate scores ──────────────────────────────────────────────────────
    def avg_score(key: str) -> float:
        vals = [int(pa["audit"]["scores"][key]) for pa in page_audits if key in pa["audit"].get("scores", {})]
        return round(sum(vals) / len(vals), 1) if vals else 0.0

    agg: Dict[str, float] = {k: avg_score(k) for k in HEURISTICS + DESIGN_FIELDS + UX_FIELDS}
    usability = average(list(agg[k] for k in HEURISTICS))
    design    = average(list(agg[k] for k in DESIGN_FIELDS))
    ux        = average(list(agg[k] for k in UX_FIELDS))
    overall   = round(usability * 0.4 + ux * 0.35 + design * 0.25, 2)

    # ── Aggregate checklists (auto-checked if avg >= 4) ───────────────────────
    def agg_checklist(items):
        return "\n".join(
            f"- [{'x' if agg[key] >= 4 else ' '}] {label} *(avg: {agg[key]}/5)*"
            for label, key in items
        )

    # ── Cross-page recurring issues ───────────────────────────────────────────
    all_issue_titles = [
        issue["title"]
        for pa in page_audits
        for issue in pa["audit"].get("issues", [])
    ]
    recurring = [title for title, count in Counter(all_issue_titles).items() if count >= 2]

    lowest_pages = sorted(page_audits, key=lambda pa: pa["score_summary"]["overall"])[:3]

    recurring_md = (
        "\n".join(f"- {t}" for t in recurring) if recurring else "- No recurring cross-page issues detected."
    )
    lowest_md = "\n".join(
        f"- **{pa['title']}** ({pa['url']}) — Overall: {pa['score_summary']['overall']}/5"
        for pa in lowest_pages
    )

    # ── Per-page sections ─────────────────────────────────────────────────────
    per_page_sections = ""
    for i, pa in enumerate(page_audits, 1):
        per_page_sections += f"\n---\n\n### Page {i}: {pa['title']}\n**URL:** {pa['url']}\n\n"
        per_page_sections += pa["markdown"]

    return f"""# Multi-Page UX Audit: {project_name}

**Client:** {client_name or 'N/A'}
**Website:** {base_url or 'N/A'}
**Pages audited:** {n}
**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## Aggregate Scorecard

- **Avg Usability:** {usability}/5
- **Avg Design:** {design}/5
- **Avg UX Quality:** {ux}/5
- **Avg Overall:** {overall}/5

---

## 🔵 Usability Checklist (Aggregate)
{agg_checklist(USABILITY_CHECKLIST)}

---

## 🟣 Design System Checklist (Aggregate)
{agg_checklist(DESIGN_CHECKLIST)}

---

## 🟠 UX Quality Checklist (Aggregate)
{agg_checklist(UX_CHECKLIST)}

---

## 🔁 Cross-Page Findings

### Recurring Issues (2+ pages)
{recurring_md}

### Highest Priority Pages
{lowest_md}

---

## 📸 Attachments
Add screenshots / recordings here

---

## 🧠 Notes
Write observations here

---

## Per-Page Detailed Reports
{per_page_sections}
"""


# ── UI ────────────────────────────────────────────────────────────────────────

SEV_ICON = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}


def _render_issues(issues: List[Dict[str, Any]], key_prefix: str = "") -> None:
    for idx, issue in enumerate(issues):
        sev = issue.get("severity", "Medium")
        with st.expander(f"{SEV_ICON.get(sev,'⚪')} {sev} — {issue.get('title','Issue')}", expanded=False):
            ca, cb = st.columns(2)
            with ca:
                if issue.get("category"):
                    st.caption(f"📂 **{issue['category']}**")
                st.write(f"**Heuristics:** {', '.join(issue.get('principles', []))}")
            with cb:
                if issue.get("common_checks"):
                    st.caption(f"🏷 {', '.join(issue['common_checks'])}")
            st.divider()
            st.write(f"**Evidence:** {issue.get('evidence', '')}")
            st.write(f"**Recommendation:** {issue.get('recommendation', '')}")


def _render_notion_push(report_md: str, project_name: str, client_name: str,
                         screen_label: str, overall: float, btn_key: str) -> None:
    st.info("Pushes the combined report to your Notion database.")
    if st.button("Create Notion page", key=btn_key):
        try:
            with st.spinner("Pushing to Notion…"):
                page_url = create_notion_page(report_md, project_name, client_name, screen_label, overall)
            st.success(f"✅ Created: {page_url}" if page_url else "✅ Created in Notion.")
        except Exception as exc:
            st.exception(exc)


# ── Page header ────────────────────────────────────────────────────────────────

st.title("🧪 AI UX Auditor")
st.caption("Audit any website with a headless browser + GPT-4o vision → generate a full UX report → push to Notion.")

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("⚙️ Configuration")
    st.write(f"OpenAI model: `{OPENAI_MODEL}`")
    st.write(f"OpenAI key: `{'✓ set' if OPENAI_API_KEY else '✗ missing'}`")
    st.write(f"Notion token: `{'✓ set' if NOTION_TOKEN else '✗ missing'}`")
    st.write(f"Notion DB: `{'✓ set' if NOTION_DATABASE_ID else '✗ missing'}`")
    st.divider()
    st.caption("Set OPENAI_API_KEY, NOTION_TOKEN, NOTION_DATABASE_ID in your shell environment.")

# ── Project metadata ───────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    project_name = st.text_input("Project name", value="Demo Product")
    client_name  = st.text_input("Client / product", value="Internal")
with col2:
    extra_context = st.text_area(
        "Optional context",
        placeholder="Brand personality, target user, platform, known constraints…",
        height=108,
    )

st.divider()

# ── Mode toggle ────────────────────────────────────────────────────────────────
audit_mode = st.radio(
    "Audit mode",
    ["🌐 Audit a website", "🖼 Upload a screenshot"],
    horizontal=True,
)

# ══════════════════════════════════════════════════════════════════════════════
# MODE A — WEBSITE AUDIT
# ══════════════════════════════════════════════════════════════════════════════
if audit_mode == "🌐 Audit a website":

    ensure_playwright_browsers()

    website_url = st.text_input(
        "Website URL",
        placeholder="https://your-product.com",
        key="website_url",
    )

    with st.expander("🔐 Login credentials (optional — for auth-gated sites)"):
        login_url_val = st.text_input(
            "Auth / SSO URL",
            placeholder="https://auth.company.com/realms/your-realm/…  (Keycloak, Okta, Azure AD…)",
            help=(
                "The URL of the login or SSO page. Can be on a completely different domain "
                "from the site being audited — e.g. a Keycloak realm URL. "
                "Leave blank to start login from the website URL above."
            ),
            key="login_url",
        )
        login_username = st.text_input("Username / email", key="login_user")
        login_password = st.text_input("Password", type="password", key="login_pass")

    max_discover = st.slider("Max pages to discover", 3, 30, 15, key="max_discover")

    # ── Step 1 : Discover ──────────────────────────────────────────────────────
    if st.button("🔍 Discover pages", disabled=not website_url.strip()):
        for k in ("discovered_pages", "discover_stats", "selected_urls", "captured_pages",
                  "page_audits", "multipage_report", "multipage_scores"):
            st.session_state.pop(k, None)
        try:
            with st.spinner("Launching browser — crawling links + clicking nav items…"):
                result = discover_pages(
                    base_url=website_url.strip(),
                    username=login_username,
                    password=login_password,
                    login_url=login_url_val.strip() or website_url.strip(),
                    max_pages=max_discover,
                )
            st.session_state["discovered_pages"] = result["pages"]
            st.session_state["discover_stats"]   = result["stats"]
        except Exception as exc:
            st.error(f"Discovery failed: {exc}")

    # ── Step 2 : Discovery summary + page selection ────────────────────────────
    if "discovered_pages" in st.session_state:
        discovered = st.session_state["discovered_pages"]
        stats      = st.session_state.get("discover_stats", {})

        # ── Summary panel ──────────────────────────────────────────────────────
        s_href  = stats.get("via_href", 0)
        s_click = stats.get("via_click", 0)
        s_nav   = stats.get("nav_elements_found", 0)
        s_login = stats.get("login_detected", False)
        total   = len(discovered)

        st.success(f"**{total} page{'s' if total != 1 else ''} discovered**")

        ci1, ci2, ci3, ci4 = st.columns(4)
        ci1.metric("Total pages",        total)
        ci2.metric("Via static links",   s_href)
        ci3.metric("Via nav clicks",     s_click)
        ci4.metric("Nav elements found", s_nav)

        if s_login:
            st.caption("🔐 Login was performed before crawling.")
        if s_nav == 0:
            st.warning("No sidebar / nav elements were found. The app may need a longer load time or use a non-standard nav pattern.")
        elif s_click == 0 and s_nav > 0:
            st.info(f"Found {s_nav} nav elements but all had readable `href` attributes — no JS-click needed.")

        # ── Source breakdown table ─────────────────────────────────────────────
        with st.expander("📋 All discovered pages", expanded=True):
            source_icon = {"base": "🏠", "href": "🔗", "nav-href": "🧭", "nav-click": "👆"}
            for p in discovered:
                icon = source_icon.get(p.get("source", ""), "•")
                st.markdown(f"{icon} **{p['title']}**  \n`{p['url']}`")

        # ── Multi-select ───────────────────────────────────────────────────────
        options = {f"{p['title']}  —  {p['url']}": p["url"] for p in discovered}
        default_labels = list(options.keys())[:5]

        selected_labels = st.multiselect(
            "Select pages to audit",
            options=list(options.keys()),
            default=default_labels,
            key="page_multiselect",
        )
        st.session_state["selected_urls"] = [options[l] for l in selected_labels]

        if len(selected_labels) > 7:
            st.info("ℹ️ Auditing many pages takes several minutes and uses OpenAI tokens.")

    # ── Step 3 : Run audit ─────────────────────────────────────────────────────
    can_audit = bool(st.session_state.get("selected_urls"))
    if st.button("🚀 Run multi-page audit", type="primary", disabled=not can_audit):
        selected_urls = st.session_state["selected_urls"]

        # Phase A – screenshots
        progress = st.progress(0.0, text="📸 Capturing pages…")
        status   = st.empty()

        def _on_progress(i, url, title):
            frac = (i + 0.5) / len(selected_urls)
            progress.progress(frac, text=f"📸 {i+1}/{len(selected_urls)} — {url}")

        try:
            captured = capture_pages(
                page_urls=selected_urls,
                username=login_username,
                password=login_password,
                login_url=login_url_val.strip() or website_url.strip(),
                on_progress=_on_progress,
            )
            st.session_state["captured_pages"] = captured
        except Exception as exc:
            st.error(f"Screenshot capture failed: {exc}")
            st.stop()

        # Phase B – AI analysis per page
        page_audits: List[Dict[str, Any]] = []
        for i, cap in enumerate(captured):
            progress.progress((i + 1) / len(captured), text=f"🤖 Analysing {i+1}/{len(captured)}: {cap.get('title','')}")
            if "error" in cap:
                status.warning(f"Skipped {cap['url']}: {cap['error']}")
                continue
            try:
                data_url = f"data:image/png;base64,{cap['screenshot_b64']}"
                audit    = call_openai(data_url, extra_context)
                scores   = compute_summary_scores(audit)
                md       = build_markdown_report(audit, project_name, client_name, cap["title"])
                page_audits.append({
                    "url": cap["url"], "title": cap["title"],
                    "screenshot_bytes": cap["screenshot_bytes"],
                    "audit": audit, "score_summary": scores, "markdown": md,
                })
            except Exception as exc:
                status.warning(f"AI failed for {cap['url']}: {exc}")

        st.session_state["page_audits"] = page_audits
        progress.empty()

        if not page_audits:
            st.error("No pages were successfully audited.")
            st.stop()

        # Phase C – aggregate
        combined_md = build_multipage_report(page_audits, project_name, client_name, website_url.strip())
        st.session_state["multipage_report"] = combined_md
        all_s = [pa["score_summary"] for pa in page_audits]
        st.session_state["multipage_scores"] = {
            "usability": average([s["usability"] for s in all_s]),
            "design":    average([s["design"]    for s in all_s]),
            "ux":        average([s["ux"]        for s in all_s]),
            "overall":   average([s["overall"]   for s in all_s]),
        }
        st.success(f"✅ Audit complete — {len(page_audits)} pages analysed.")

    # ── Step 4 : Results ───────────────────────────────────────────────────────
    if "page_audits" in st.session_state and st.session_state["page_audits"]:
        page_audits  = st.session_state["page_audits"]
        agg_scores   = st.session_state["multipage_scores"]
        combined_md  = st.session_state["multipage_report"]

        # Aggregate metrics
        a, b, c, d = st.columns(4)
        a.metric("Avg Usability", agg_scores["usability"])
        b.metric("Avg Design",    agg_scores["design"])
        c.metric("Avg UX",        agg_scores["ux"])
        d.metric("Avg Overall",   agg_scores["overall"])

        st.subheader("Results")

        tab_labels = [f"{'🟢' if pa['score_summary']['overall']>=4 else '🟡' if pa['score_summary']['overall']>=3 else '🔴'} {pa['title'][:30]}" for pa in page_audits]
        tab_labels += ["📋 Combined Report", "📤 Push to Notion"]
        tabs = st.tabs(tab_labels)

        for i, pa in enumerate(page_audits):
            with tabs[i]:
                st.caption(pa["url"])

                left_col, right_col = st.columns([1, 1])

                with left_col:
                    st.image(pa["screenshot_bytes"], caption=pa["title"], use_container_width=True)

                with right_col:
                    s = pa["score_summary"]
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Usability", s["usability"])
                    m2.metric("Design",    s["design"])
                    m3.metric("UX",        s["ux"])
                    m4.metric("Overall",   s["overall"])

                    st.divider()

                    # 250-word deep description
                    page_desc = pa["audit"].get("page_description", "")
                    if page_desc:
                        st.subheader("📖 Page Analysis")
                        st.write(page_desc)
                        st.divider()

                    # One-line executive headline
                    headline = pa["audit"].get("summary", "")
                    if headline:
                        st.caption(f"**Key finding:** {headline}")

                _render_issues(pa["audit"].get("issues", []), key_prefix=f"page_{i}")
                st.download_button(
                    "⬇ Download page report",
                    pa["markdown"].encode(),
                    file_name=f"ux_audit_page_{i+1}.md",
                    mime="text/markdown",
                    key=f"dl_page_{i}",
                )

        with tabs[-2]:   # Combined Report
            st.markdown(combined_md)
            st.download_button(
                "⬇ Download combined report",
                combined_md.encode(),
                file_name="ux_audit_combined.md",
                mime="text/markdown",
                key="dl_combined",
            )

        with tabs[-1]:   # Push to Notion
            _render_notion_push(
                combined_md, project_name, client_name,
                f"{len(page_audits)}-page audit",
                agg_scores["overall"],
                btn_key="notion_web",
            )


# ══════════════════════════════════════════════════════════════════════════════
# MODE B — SINGLE SCREENSHOT
# ══════════════════════════════════════════════════════════════════════════════
else:
    screen_name = st.text_input("Screen / flow name", value="", key="screen_name_single")
    uploaded    = st.file_uploader("Upload screenshot", type=["png", "jpg", "jpeg", "webp"])
    image_input: Optional[str] = None

    if uploaded:
        st.image(uploaded, use_container_width=True)
        try:
            image_input = file_to_base64(uploaded)
        except ValueError as exc:
            st.error(str(exc))

    if st.button("Run AI audit", type="primary", disabled=image_input is None):
        try:
            with st.spinner("Analysing with AI…"):
                audit        = call_openai(image_input, extra_context)
                score_summary = compute_summary_scores(audit)
                markdown     = build_markdown_report(audit, project_name, client_name, screen_name)
            st.session_state.update({"audit": audit, "markdown": markdown, "score_summary": score_summary})
            st.success("Audit complete.")
        except Exception as exc:
            st.exception(exc)

    if "audit" in st.session_state:
        audit        = st.session_state["audit"]
        score_summary = st.session_state["score_summary"]
        markdown     = st.session_state["markdown"]

        a, b, c, d = st.columns(4)
        a.metric("Usability", score_summary["usability"])
        b.metric("Design",    score_summary["design"])
        c.metric("UX",        score_summary["ux"])
        d.metric("Overall",   score_summary["overall"])
        st.write(audit.get("summary", ""))

        tabs = st.tabs(["Issues", "Raw JSON", "Report", "Push to Notion"])
        with tabs[0]:
            _render_issues(audit.get("issues", []))
        with tabs[1]:
            st.json(audit)
        with tabs[2]:
            st.markdown(markdown)
            st.download_button("⬇ Download", markdown.encode(), "ux_audit_report.md", "text/markdown")
        with tabs[3]:
            _render_notion_push(
                markdown, project_name, client_name,
                screen_name or audit.get("screen_name", "Screen"),
                score_summary["overall"],
                btn_key="notion_single",
            )
