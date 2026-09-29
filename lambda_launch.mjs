// Launch ONLY: starts the Lambda render, prints renderId, exits. Poll with lambda_poll.py
import { renderMediaOnLambda } from '@remotion/lambda';
import { NodeHttpHandler } from '@smithy/node-http-handler';
import { HttpsProxyAgent } from 'https-proxy-agent';
import { readFileSync, writeFileSync } from 'fs';

const proxyAgent = new HttpsProxyAgent('http://hatch-egress-proxy:3128');
const requestHandler = new NodeHttpHandler({ httpsAgent: proxyAgent });
const inputProps = JSON.parse(readFileSync('/home/hatch/workspace/history-video/projects/battle-off-samar-1944_script/props.json', 'utf8'));

const startTs = Date.now();
writeFileSync('/home/hatch/workspace/history-video/projects/battle-off-samar-1944_script/lambda_start_ts.txt', String(Math.floor(startTs / 1000)));
console.log('RENDER START:', new Date(startTs).toISOString());

const { renderId, bucketName } = await renderMediaOnLambda({
  region: 'us-east-1',
  functionName: 'remotion-render-4-0-527-mem3008mb-disk10240mb-900sec',
  serveUrl: 'https://remotionlambda-useast1-r5lxcie5hs.s3.us-east-1.amazonaws.com/sites/samar-1944/index.html',
  composition: 'HistoryDoc',
  inputProps,
  codec: 'h264',
  requestHandler,
  framesPerLambda: 800,
});
console.log('RENDERID:' + renderId);
console.log('BUCKET:' + bucketName);
process.exit(0);
