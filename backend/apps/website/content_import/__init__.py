"""Bulk content import (Мероприятия / Достижения / Новости) from XLSX or CSV.

    reader.py    safe XLSX / CSV reading (size, zip, row and cell limits; no URL fetching)
    schema.py    columns of each content type, header aliases, allowed values
    validate.py  per-row validation: blocking errors vs warnings, duplicates
    service.py   preview → commit (per-record transactions), never publishes
    template.py  downloadable XLSX (README + 3 sheets) and CSV templates

Docs: backend/docs/content_import.md
"""
