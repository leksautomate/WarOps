// Poll Lambda render progress by reading progress.json directly from S3.
// Usage: node lambda_poll.mjs <renderId> <bucketName>
import { S3Client, GetObjectCommand } from '@aws-sdk/client-s3';
import { NodeHttpHandler } from '@smithy/node-http-handler';
import { HttpsProxyAgent } from 'https-proxy-agent';
import { readFileSync, writeFileSync } from 'fs';

process.on('uncaughtException', (e) => console.log('uncaught (ignored):', e.message));

const [renderId, bucketName] = process.argv.slice(2);
const startTs = Number(readFileSync('/home/hatch/workspace/history-video/projects/battle-off-samar-1944_script/lambda_start_ts.txt', 'utf8').trim()) * 1000;

function freshS3() {
  return new S3Client({
    region: 'us-east-1',
    requestHandler: new NodeHttpHandler({
      httpsAgent: new HttpsProxyAgent('http://hatch-egress-proxy:3128'),
      connectionTimeout: 15000,
      socketTimeout: 30000,
    }),
    maxAttempts: 3,
  });
}

async function getProgress() {
  for (let a = 1; a <= 8; a++) {
    try {
      const s3 = freshS3();
      const r = await s3.send(new GetObjectCommand({ Bucket: bucketName, Key: `renders/${renderId}/progress.json` }));
      const text = await r.Body.transformToString();
      s3.destroy();
      return JSON.parse(text);
    } catch (e) {
      console.log(`s3 read failed (attempt ${a}): ${e.message.slice(0, 80)}`);
      if (a === 8) throw e;
      await new Promise(r => setTimeout(r, 7000));
    }
  }
}

let lastLog = 0;
for (;;) {
  const p = await getProgress();
  const now = Date.now();
  if (now - lastLog > 20000) {
    const pct = Math.round((p.overallProgress || 0) * 100);
    console.log(`[${new Date().toISOString()}] ${pct}% done=${p.done} fatal=${p.fatalErrorEncountered}`);
    lastLog = now;
  }
  if (p.done) {
    const elapsedMin = ((now - startTs) / 60000).toFixed(2);
    console.log('DONE at', new Date(now).toISOString(), '| ELAPSED MINUTES:', elapsedMin);
    console.log('OUTPUT:', p.outputFile);
    writeFileSync('/home/hatch/workspace/history-video/projects/battle-off-samar-1944_script/lambda_result.json', JSON.stringify({
      renderId, bucketName, outputFile: p.outputFile,
      startIso: new Date(startTs).toISOString(), endIso: new Date(now).toISOString(),
      elapsedMinutes: Number(elapsedMin),
    }, null, 2));
    break;
  }
  if (p.fatalErrorEncountered) {
    console.error('FATAL:', JSON.stringify((p.errors || []).slice(0, 1)));
    process.exit(2);
  }
  await new Promise(r => setTimeout(r, 10000));
}
