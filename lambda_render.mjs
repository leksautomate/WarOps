// Direct Lambda render via @remotion/lambda API (bypasses CLI prepareServer).
// Run with: NODE_OPTIONS="--require /home/hatch/workspace/history-video/proxy-preload.cjs" node lambda_render.mjs
import { renderMediaOnLambda, getRenderProgress } from '@remotion/lambda';
import { NodeHttpHandler } from '@smithy/node-http-handler';
import { HttpsProxyAgent } from 'https-proxy-agent';
import { readFileSync, writeFileSync } from 'fs';

const REGION = 'us-east-1';
const FUNCTION_NAME = 'remotion-render-4-0-527-mem3008mb-disk10240mb-900sec';
const SERVE_URL = 'https://remotionlambda-useast1-r5lxcie5hs.s3.us-east-1.amazonaws.com/sites/samar-1944/index.html';
const PROPS_PATH = '/home/hatch/workspace/history-video/projects/battle-off-samar-1944_script/props.json';

// Remotion's Lambda client sets a custom httpsAgent (maxSockets) which bypasses
// the global-agent proxy patch. Inject a proxy-aware request handler instead.
const proxyAgent = new HttpsProxyAgent('http://hatch-egress-proxy:3128');
const requestHandler = new NodeHttpHandler({ httpsAgent: proxyAgent });

const inputProps = JSON.parse(readFileSync(PROPS_PATH, 'utf8'));

// Resume an existing render: node lambda_render.mjs <renderId> <bucketName>
const resumeRenderId = process.argv[2];
const resumeBucket = process.argv[3];

const startTs = Date.now();
let renderId, bucketName;

if (resumeRenderId && resumeBucket) {
  renderId = resumeRenderId; bucketName = resumeBucket;
  console.log('RESUMING renderId:', renderId);
} else {
  writeFileSync('/home/hatch/workspace/history-video/projects/battle-off-samar-1944_script/lambda_start_ts.txt', String(Math.floor(startTs / 1000)));
  console.log('RENDER START:', new Date(startTs).toISOString());
  ({ renderId, bucketName } = await renderMediaOnLambda({
    region: REGION,
    functionName: FUNCTION_NAME,
    serveUrl: SERVE_URL,
    composition: 'HistoryDoc',
    inputProps,
    codec: 'h264',
    requestHandler,
    framesPerLambda: 1400, // account allows only 10 concurrent Lambdas -> ~5 chunks
  }));
  console.log('renderId:', renderId, '| bucket:', bucketName);
}

async function safeProgress() {
  for (let attempt = 1; attempt <= 5; attempt++) {
    try {
      return await getRenderProgress({ region: REGION, functionName: FUNCTION_NAME, bucketName, renderId, requestHandler });
    } catch (e) {
      console.log(`progress poll failed (attempt ${attempt}): ${e.message} — retrying`);
      await new Promise(r => setTimeout(r, 8000));
    }
  }
  throw new Error('progress polling failed 5x in a row');
}

let lastLog = 0;
for (;;) {
  const progress = await safeProgress();
  const now = Date.now();
  if (now - lastLog > 15000) {
    console.log(`[${new Date().toISOString()}] ${Math.round((progress.overallProgress || 0) * 100)}% | ${progress.chunks}/${progress.renderMetadata?.totalChunks ?? '?'} chunks | fatal: ${progress.fatalErrorEncountered}`);
    lastLog = now;
  }
  if (progress.done) {
    const endTs = Date.now();
    const elapsedMin = ((endTs - startTs) / 60000).toFixed(2);
    console.log('RENDER DONE:', new Date(endTs).toISOString());
    console.log('ELAPSED MINUTES:', elapsedMin);
    console.log('OUTPUT:', progress.outputFile);
    writeFileSync('/home/hatch/workspace/history-video/projects/battle-off-samar-1944_script/lambda_result.json', JSON.stringify({
      renderId, bucketName, outputFile: progress.outputFile,
      startIso: new Date(startTs).toISOString(), endIso: new Date(endTs).toISOString(),
      elapsedMinutes: Number(elapsedMin),
    }, null, 2));
    break;
  }
  if (progress.fatalErrorEncountered) {
    console.error('FATAL:', JSON.stringify(progress.errors.slice(0, 2)));
    process.exit(2);
  }
  await new Promise(r => setTimeout(r, 5000));
}
