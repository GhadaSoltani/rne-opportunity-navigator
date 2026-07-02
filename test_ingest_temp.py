from ingest import ingest_pdf
from db.documents import ensure_indexes
ensure_indexes()
doc_id, status = ingest_pdf(r'samples\1899271W.pdf')
print(f'Status: {status}, ID: {doc_id}')
