# recover.py — refresh ne jo stances 'unknown' kar diye unhe wapas classify karo.
# Standalone process (apna empty cache) — active ads ko chunks mein Opus se
# classify karta hai, running-today PEHLE, har chunk turant archive mein likhता
# hai (sirf valid stance — non-destructive). Beech mein die to progress safe.
from dotenv import load_dotenv
load_dotenv()
import sys
from collections import Counter
from datetime import date
import config, archive, classifier, meta_api

if not classifier.AI_ENABLED:
    print("ABORT: AI off (ANTHROPIC_API_KEY missing)"); sys.exit(1)

today = date.today().isoformat()


def running_today(a):
    st = (a.get("started") or a.get("start") or "")[:10]
    sp = (a.get("stop") or "")[:10]
    return st <= today and (not sp or sp >= today)


rows = archive.get_archive(status="active", limit=60000)
todo = [a for a in rows if a.get("stance") not in ("against", "support", "neutral")]
todo.sort(key=lambda a: 0 if running_today(a) else 1)  # aaj chal rahi ads pehle
print("MODEL: %s | active: %d | to reclassify: %d"
      % (config.CLASSIFY_MODEL, len(rows), len(todo)), flush=True)

PH = archive.PH
UPD = ("UPDATE ads_archive SET stance=%s, party=%s, narrative=%s, "
       "narrative_summary=%s WHERE id=%s" % (PH, PH, PH, PH, PH))

CHUNK = 250
done = 0
total_chunks = (len(todo) + CHUNK - 1) // CHUNK
for i in range(0, len(todo), CHUNK):
    chunk = todo[i:i + CHUNK]
    try:
        classifier.enrich_ads(chunk)
        meta_api.correct_proxy_party(chunk)
    except Exception as e:
        print("  chunk classify error: %s" % e, flush=True)
        continue
    stmts = []
    for a in chunk:
        st = a.get("stance")
        if st in ("against", "support", "neutral"):
            stmts.append((UPD, (st, a.get("party"), a.get("narrative"),
                                a.get("narrative_summary"), a.get("id"))))
    if stmts:
        archive._write(stmts)
        done += len(stmts)
    print("chunk %d/%d done | updated total: %d"
          % (i // CHUNK + 1, total_chunks, done), flush=True)

print("FINAL updated: %d" % done, flush=True)
final = archive.get_archive(status="active", limit=60000)
print("active stance now:", dict(Counter(a.get("stance") for a in final)), flush=True)
