// scripts/lambda_launch.mjs — parameterized Lambda render launcher.
// Prints RENDERID:<id> and BUCKET:<bucket> on success, exits 0.
// Exactly one of --frames-per-lambda / --concurrency may be set
// (Remotion rejects both).
// Run with: NODE_OPTIONS="--require <project>/proxy-preload.cjs" node scripts/lambda_launch.mjs [args]
import { renderMediaOnLambda } from '@remotion/lambda';
import { NodeHttpHandler } from '@smithy/node-http-handler';
import { HttpsProxyAgent } from 'https-proxy-agent';
import { readFileSync } from 'fs';

function arg(name, def = null) {
  const i = process.argv.indexOf(name);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : def;
}

const propsPath = arg('--props');
const serveUrl = arg('--serve-url');
const region = arg('--region', 'us-east-1');
const functionName = arg('--function-name');
const framesPerLambda = arg('--frames-per-lambda');
const concurrency = arg('--concurrency');

if (!propsPath || !serveUrl || !functionName) {
  console.error('usage: node lambda_launch.mjs --props props.json --serve-url <url> --function-name <name> [--region r] [--frames-per-lambda N | --concurrency N]');
  process.exit(1);
}

// Remotion's Lambda client sets a custom httpsAgent (maxSockets) which
// bypasses the global-agent proxy patch. Inject a proxy-aware handler.
const proxyAgent = new HttpsProxyAgent('http://hatch-egress-proxy:3128');
const requestHandler = new NodeHttpHandler({ httpsAgent: proxyAgent });

const inputProps = JSON.parse(readFileSync(propsPath, 'utf8'));

const opts = {
  region,
  functionName,
  serveUrl,
  composition: 'HistoryDoc',
  inputProps,
  codec: 'h264',
  requestHandler,
};
if (framesPerLambda && concurrency) {
  console.error("error: set only one of --frames-per-lambda / --concurrency");
  process.exit(1);
}
if (framesPerLambda) opts.framesPerLambda = Number(framesPerLambda);
if (concurrency) opts.concurrency = Number(concurrency);

const startTs = Date.now();
console.log('RENDER START:', new Date(startTs).toISOString());
const { renderId, bucketName } = await renderMediaOnLambda(opts);
console.log('START_TS:' + Math.floor(startTs / 1000));
console.log('RENDERID:' + renderId);
console.log('BUCKET:' + bucketName);
process.exit(0);
