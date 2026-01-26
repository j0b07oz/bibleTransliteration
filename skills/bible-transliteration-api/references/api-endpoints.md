# API endpoints used by this skill

## Render chapter

- **Endpoint**: `GET /`
- **Query params**: `book`, `chapter`, optional `focus`
- **Purpose**: Render the transliterated chapter view.

## Dictionary editor

- **Endpoint**: `POST /edit_dict`
- **Purpose**: Add/update/delete Strong's entries.
- **Payload**:

```json
{
  "actions": [
    {
      "action": "add|update|delete",
      "strong_number": "H7225",
      "translations": ["beginning"],
      "color": "#FF5733"
    }
  ]
}
```

## Dictionary export/import (optional)

- **Endpoint**: `GET /export_dict` (download JSON)
- **Endpoint**: `POST /upload_dict` (upload JSON)
