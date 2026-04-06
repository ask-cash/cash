"""
email_classifier.py — Claude-powered email classification with feedback learning.

Classifies emails into: important, low_priority, spam
Learns from user feedback stored in user_data/memory/email_preferences.json
"""

import os
import json
import logging
import datetime as dt
import anthropic
from typing import Optional

logger = logging.getLogger(__name__)

PREFS_DIR = "user_data/memory"
PREFS_PATH = os.path.join(PREFS_DIR, "email_preferences.json")
SEEN_PATH = os.path.join(PREFS_DIR, "email_seen.json")


def _ensure_dir():
    os.makedirs(PREFS_DIR, exist_ok=True)


def _load_preferences() -> dict:
    """Load email classification preferences and feedback history."""
    _ensure_dir()
    if os.path.exists(PREFS_PATH):
        with open(PREFS_PATH) as f:
            return json.load(f)
    return {
        "important_senders": [],
        "spam_senders": [],
        "important_keywords": [],
        "spam_keywords": [],
        "feedback_log": [],
    }


def _save_preferences(prefs: dict):
    _ensure_dir()
    with open(PREFS_PATH, "w") as f:
        json.dump(prefs, f, indent=2)


def _load_seen() -> dict:
    """Load set of already-seen email IDs with their classification."""
    _ensure_dir()
    if os.path.exists(SEEN_PATH):
        with open(SEEN_PATH) as f:
            return json.load(f)
    return {}


def _save_seen(seen: dict):
    _ensure_dir()
    with open(SEEN_PATH, "w") as f:
        json.dump(seen, f, indent=2)


def is_email_seen(email_id: str) -> bool:
    seen = _load_seen()
    return email_id in seen


def mark_email_seen(email_id: str, classification: str):
    seen = _load_seen()
    seen[email_id] = {
        "classification": classification,
        "seen_at": dt.datetime.now().isoformat(),
    }
    # Keep only last 500 entries to avoid unbounded growth
    if len(seen) > 500:
        sorted_ids = sorted(seen.keys(), key=lambda k: seen[k].get("seen_at", ""))
        for old_id in sorted_ids[:len(seen) - 500]:
            del seen[old_id]
    _save_seen(seen)


def record_feedback(email_id: str, from_email: str, subject: str, old_label: str, new_label: str):
    """Record user feedback when they reclassify an email. Updates sender/keyword rules."""
    prefs = _load_preferences()

    prefs["feedback_log"].append({
        "email_id": email_id,
        "from": from_email,
        "subject": subject,
        "old_label": old_label,
        "new_label": new_label,
        "timestamp": dt.datetime.now().isoformat(),
    })

    # Keep feedback log bounded
    if len(prefs["feedback_log"]) > 200:
        prefs["feedback_log"] = prefs["feedback_log"][-200:]

    # Learn sender preferences from feedback
    if new_label == "important" and from_email:
        if from_email not in prefs["important_senders"]:
            prefs["important_senders"].append(from_email)
        if from_email in prefs["spam_senders"]:
            prefs["spam_senders"].remove(from_email)

    elif new_label == "spam" and from_email:
        if from_email not in prefs["spam_senders"]:
            prefs["spam_senders"].append(from_email)
        if from_email in prefs["important_senders"]:
            prefs["important_senders"].remove(from_email)

    _save_preferences(prefs)


def _build_feedback_context(prefs: dict) -> str:
    """Build context string from learned preferences for Claude."""
    sections = []

    if prefs["important_senders"]:
        sections.append(f"ALWAYS IMPORTANT senders: {', '.join(prefs['important_senders'][-20:])}")
    if prefs["spam_senders"]:
        sections.append(f"ALWAYS SPAM senders: {', '.join(prefs['spam_senders'][-20:])}")
    if prefs["important_keywords"]:
        sections.append(f"Important keywords: {', '.join(prefs['important_keywords'][-15:])}")
    if prefs["spam_keywords"]:
        sections.append(f"Spam keywords: {', '.join(prefs['spam_keywords'][-15:])}")

    # Include recent corrections so Claude learns patterns
    recent_corrections = prefs["feedback_log"][-15:]
    if recent_corrections:
        sections.append("RECENT USER CORRECTIONS (learn from these):")
        for fb in recent_corrections:
            sections.append(
                f"  - '{fb['subject'][:60]}' from {fb['from']} was {fb['old_label']} "
                f"→ user said {fb['new_label']}"
            )

    return "\n".join(sections) if sections else "No learned preferences yet."


def classify_emails(emails: list[dict]) -> list[dict]:
    """
    Classify a batch of emails using Claude.
    Each email gets a label: important, low_priority, or spam.
    Returns the emails with 'classification' and 'reason' fields added.
    """
    if not emails:
        return []

    prefs = _load_preferences()

    # Fast-path: check sender rules first
    needs_ai = []
    results = []
    for email in emails:
        sender = email.get("from_email", "").lower()
        if sender in [s.lower() for s in prefs.get("spam_senders", [])]:
            email["classification"] = "spam"
            email["reason"] = "Sender marked as spam by you"
            results.append(email)
        elif sender in [s.lower() for s in prefs.get("important_senders", [])]:
            email["classification"] = "important"
            email["reason"] = "Sender marked as important by you"
            results.append(email)
        else:
            needs_ai.append(email)

    if not needs_ai:
        return results

    # Build email summaries for Claude
    email_summaries = []
    for i, email in enumerate(needs_ai):
        email_summaries.append(
            f"[{i}] From: {email['from_name']} <{email['from_email']}>\n"
            f"    Subject: {email['subject']}\n"
            f"    Snippet: {email['snippet'][:200]}"
        )

    feedback_context = _build_feedback_context(prefs)

    prompt = f"""You are an email classifier for a busy professional named Suhail. Classify each email as:
- "important": Personal emails, work-related, financial alerts, calendar invites, emails from real people who expect a reply, urgent notifications
- "low_priority": Newsletters they subscribed to, social media notifications, non-urgent updates, order confirmations, routine automated emails
- "spam": Marketing/promotional, unsolicited, scams, mass-mailed offers, unsubscribed lists

USER'S LEARNED PREFERENCES (respect these absolutely):
{feedback_context}

EMAILS TO CLASSIFY:
{chr(10).join(email_summaries)}

Respond ONLY with a JSON array (no markdown, no backticks). Each element:
{{"index": <int>, "label": "important|low_priority|spam", "reason": "<short reason>"}}
"""

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        classifications = json.loads(raw)

        for cls in classifications:
            idx = cls.get("index", -1)
            if 0 <= idx < len(needs_ai):
                needs_ai[idx]["classification"] = cls.get("label", "low_priority")
                needs_ai[idx]["reason"] = cls.get("reason", "")

    except Exception as e:
        logger.error(f"Classification error: {e}")
        for email in needs_ai:
            if "classification" not in email:
                email["classification"] = "low_priority"
                email["reason"] = "Could not classify (AI error)"

    # Ensure every email has a classification
    for email in needs_ai:
        if "classification" not in email:
            email["classification"] = "low_priority"
            email["reason"] = "Unclassified"

    return results + needs_ai


def get_preferences_summary() -> str:
    """Get a human-readable summary of learned email preferences."""
    prefs = _load_preferences()
    lines = ["📧 Email Filter Preferences:\n"]

    imp = prefs.get("important_senders", [])
    if imp:
        lines.append(f"✅ Important senders ({len(imp)}):")
        for s in imp[-10:]:
            lines.append(f"  • {s}")

    spam = prefs.get("spam_senders", [])
    if spam:
        lines.append(f"\n🚫 Spam senders ({len(spam)}):")
        for s in spam[-10:]:
            lines.append(f"  • {s}")

    fb = prefs.get("feedback_log", [])
    lines.append(f"\n📊 Total feedback corrections: {len(fb)}")

    return "\n".join(lines)
