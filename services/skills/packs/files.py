"""files pack — working with uploaded files (summarise, send, Drive, attach).

Carries the file-handling and file+event routing rules, since they only make
sense when this pack is active.
"""

from services.skills.registry import Skill, register

SKILL = register(Skill(
    id="files",
    title="Files",
    order=110,
    actions=("summarize_file", "attach_file_to_event", "send_file", "upload_to_drive"),
    flag="files",
    prompt='''- "summarize_file" — summarise or answer questions about an uploaded file (params: {"file_ref": "id or filename substring, or '' for the most recent upload", "question": "the user's actual ask — e.g. 'summarise', 'what are the action items', 'translate to Hindi'"})
- "attach_file_to_event" — create a calendar event referencing an uploaded file (params: {"file_ref": "...", "title": "...", "date": "YYYY-MM-DD", "start_time": "HH:MM", "duration_minutes": N, "calendar": "google|outlook"})
  Same date rules as create_event — always pass concrete YYYY-MM-DD.
- "send_file" — send a previously uploaded file back to the user (params: {"file_ref": "id or filename substring, or '' for the most recent upload"})
- "upload_to_drive" — put a file on the user's Google Drive and return its shareable link. If the file is ALREADY on Drive, this returns the existing link instead of uploading again (one file = one Drive link). Use this both for "upload to drive" AND for "give me/share the Drive link to X" (params: {"file_ref": "id or filename substring, or '' for the most recent upload"})

FILE HANDLING RULES:
- Recent uploads appear in the RECENT UPLOADS section below. When the user says "the file", "that PDF", "the doc I just sent", default file_ref to "" (latest).
- If the user says "summarise the resume" and there's a file whose name contains "resume", pass file_ref="resume".
- "send me the file" / "share that doc" → send_file.
- "upload to drive" / "put this on my drive" / "save to google drive" / "give me the drive link to X" / "share my resume's drive link" → upload_to_drive. YES you CAN upload to Drive — never deny this capability. If it's already on Drive, the action returns the saved link without re-uploading, so always route Drive-link requests here rather than re-uploading.

CRITICAL — FILE + EVENT ROUTING:
- If there is ANY file in RECENT UPLOADS (uploaded earlier in the conversation) AND the user asks to create/schedule/book a calendar event, ALWAYS use "attach_file_to_event" with file_ref="" (latest upload). NEVER use plain "create_event" when a recent upload exists.
- The attach_file_to_event action automatically uploads the file to Google Drive, attaches it to the event, AND puts the Drive link in the event description — this is exactly the behaviour the user wants.
- Example: user uploads resume.pdf, then says "create an interview prep session tomorrow at 4pm" → action MUST be attach_file_to_event, file_ref="", title="Interview prep session", date=tomorrow's date, start_time="16:00".
- Only fall back to plain "create_event" if RECENT UPLOADS is empty OR the user explicitly says "don't attach any file" / "without the file".''',
))
