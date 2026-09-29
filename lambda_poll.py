"""Poll a Remotion Lambda render via progress.json in S3. Usage: python3 lambda_poll.py <renderId> <bucket>"""
import boto3, json, sys, time
from datetime import datetime, timezone

render_id, bucket = sys.argv[1], sys.argv[2]
s3 = boto3.client('s3', region_name='us-east-1')
with open('/home/hatch/workspace/history-video/projects/battle-off-samar-1944_script/lambda_start_ts.txt') as f:
    start_ts = int(f.read().strip())

def get_progress():
    for a in range(8):
        try:
            r = s3.get_object(Bucket=bucket, Key=f'renders/{render_id}/progress.json')
            return json.loads(r['Body'].read())
        except Exception as e:
            print(f's3 read failed ({a+1}): {str(e)[:70]}', flush=True)
            time.sleep(7)
    raise RuntimeError('s3 unreadable')

last_log = 0
while True:
    p = get_progress()
    now = time.time()
    if now - last_log > 25:
        chunks = p.get('chunks') or []
        if chunks and isinstance(chunks[0], dict):
            done_chunks = sum(1 for c in chunks if c.get('done'))
            total_chunks = len(chunks)
        else:
            total_chunks = chunks[0] if chunks else 0
            done_chunks = p.get('chunksDone', 0)
        print(f"[{datetime.now(timezone.utc).isoformat()}] chunks {done_chunks}/{total_chunks} fatal={p.get('fatalErrorEncountered')}", flush=True)
        last_log = now
    if p.get('done'):
        mins = (now - start_ts) / 60
        print('DONE', datetime.now(timezone.utc).isoformat(), '| ELAPSED MINUTES:', round(mins, 2), flush=True)
        print('OUTPUT:', p.get('outputFile'), flush=True)
        with open('/home/hatch/workspace/history-video/projects/battle-off-samar-1944_script/lambda_result.json', 'w') as f:
            json.dump({'renderId': render_id, 'bucketName': bucket, 'outputFile': p.get('outputFile'),
                       'elapsedMinutes': round(mins, 2)}, f, indent=2)
        break
    errs = [e for e in (p.get('errors') or []) if e.get('isFatal')]
    if p.get('fatalErrorEncountered') or errs:
        print('FATAL:', (errs[0].get('message') if errs else '?')[:300], flush=True)
        sys.exit(2)
    time.sleep(12)
