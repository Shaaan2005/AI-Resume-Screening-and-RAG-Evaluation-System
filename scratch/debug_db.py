from chroma_search import get_collection

coll = get_collection()
total = coll.count()
print(f"Total count from count(): {total}")

# Get all items in batches
all_metadatas = []
limit = 100
offset = 0
while True:
    res = coll.get(limit=limit, offset=offset)
    metas = res.get('metadatas', [])
    if not metas:
        break
    all_metadatas.extend(metas)
    offset += len(metas)

print(f"Total metadatas fetched: {len(all_metadatas)}")
categories = set(m.get('category') for m in all_metadatas if m)
print(f"Unique categories found: {categories}")
