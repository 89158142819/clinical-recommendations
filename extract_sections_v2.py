result = {
    "document_id": DOCUMENT_ID,
    "title": source_data.get("title", "Без названия"),
    "source": source_data.get("source"),
    **sections,
}
