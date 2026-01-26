---
name: bible-transliteration-api
description: Use when an agent must plan or execute Bible transliteration workflows for this project, including updating the user Strong's dictionary, resolving Strong's numbers from KJV verse context, and rendering chapters via the site's API.
---

# Bible Transliteration API Skill

Use this skill to help an agent resolve Strong's numbers from KJV context and call the site's API endpoints to update the user's dictionary and render chapters with custom transliterations.

## Quick workflow

1. **Parse the user intent.** Identify the book, chapter, and target word(s).
2. **Resolve Strong's numbers (KJV-only).**
   - If the user provides a Strong's ID, use it directly.
   - If the user provides a book/chapter context (e.g., "Genesis 1"), resolve Strong's by scanning the KJV data in `app/static/kjv_strongs.json`.
   - If no context is provided, ask for a specific KJV reference (book/chapter/verse) or ask for the Strong's ID explicitly.
3. **Update the dictionary.** Call `POST /edit_dict` with `action: add|update` and `translations` set to the desired transliteration.
4. **Render the chapter.** Call `GET /?book=<Book>&chapter=<N>` (optionally add `focus=<Strong>` for highlighting).
5. **Respond with the rendered output.** If multiple Strong's candidates exist, present options and ask the user to choose.

## Strong's resolution from KJV context

Follow this procedure when the user gives a word plus a KJV reference:

1. Load `app/static/kjv_strongs.json` and filter `verses` to the specified book + chapter.
2. For each verse `text`, parse word tokens and attached Strong's markers (e.g., `light{H216}`).
3. Match the user's word case-insensitively (strip punctuation). Capture the Strong's tag immediately attached to the matching word.
4. If multiple Strong's values appear for the same word in the chapter, report the verse references and ask the user to pick the correct one.
5. If no match is found, ask for a more specific reference (chapter + verse) or ask for the Strong's ID directly.

For parsing guidance and data shapes, see:
- `references/kjv-data.md`
- `references/api-endpoints.md`

## API usage patterns

### Update dictionary

```
POST /edit_dict
Content-Type: application/json

{
  "actions": [
    {
      "action": "add",
      "strong_number": "H216",
      "translations": ["owr"],
      "color": null
    }
  ]
}
```

### Render chapter

```
GET /?book=Genesis&chapter=1
```

### Render with highlight

```
GET /?book=Genesis&chapter=1&focus=H216
```
