# KJV data reference (KJV only)

The Strong's lookups should be performed against the local KJV dataset:

- **Path**: `app/data/kjv_strongs.json`
- **Shape**:

```json
{
  "metadata": { ... },
  "verses": [
    {
      "book_name": "Genesis",
      "book": 1,
      "chapter": 1,
      "verse": 1,
      "text": "In the beginning{H7225} God{H430} created{H1254}{(H8804)}{H853} ..."
    }
  ]
}
```

## Parsing guidance

- Each verse is a single string with Strong's markers attached to the preceding word token, e.g. `light{H216}`.
- Strip punctuation from tokens when matching the user's word.
- Match case-insensitively.
- If multiple matches exist for the same word, present verse references and ask the user to confirm.
