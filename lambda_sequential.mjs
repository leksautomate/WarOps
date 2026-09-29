// Sequential Lambda renders: 4 chunks, one at a time, no concurrency.
// Each renders a frame range as a single-chunk Lambda, then we stitch locally.
import { renderMediaOnLambda, getRenderProgress } from '@remotion/lambda';
import { NodeHttpHandler } from '@smithy/node-http-handler';
import { HttpsProxyAgent } from 'https-proxy-agent';
import { readFileSync, writeFileSync } from 'fs';

const proxyAgent = new HttpsProxyAgent('http://hatch-egress-proxy:3128');
const requestHandler = new NodeHttpHandler({ httpsAgent: proxyAgent });
const inputProps = JSON.parse(readFileSync('/home/hatch/workspace/history-video/projects/battle-off-samar-1944_script/props.json', 'utf8'));

const FUNCTION = 'remotion-render-4-0-527-mem3008mb-disk10240mb-900sec';
const BUCKET = 'remotionlambda-useast1-r5lxcie5hs';
const SERVE_URL = `https://${BUCKET}.s3.us-east-1.amazonaws.com/sites/samar-1944/index.html`;

// 4 ranges covering 6804 frames
const ranges = [[0, 1700], [1701, 3400], [3401, 5100], [5101, 6803]];
const renderIds = [];

for (let i = 0; i < ranges.length; i++) {
  const [from, to] = ranges[i];
  console.log(`\n=== Chunk ${i+1}/4: frames ${from}-${to} ===`);
  const startTs = Date.now();
  
  const { renderId } = await renderMediaOnLambda({
    region: 'us-east-1',
    functionName: FUNCTION,
    serveUrl: SERVE_URL,
    composition: 'HistoryDoc',
    inputProps,
    codec: 'h264',
    requestHandler,
    frameRange: [from, to],
    framesPerLambda: 2000, // ensure single chunk
    outName: `samar-part${i}.mp4`,
  });
  
  console.log(`RenderId: ${renderId}`);
  renderIds.push({ renderId, from, to, startTs });
  
  // Poll until done
  while (true) {
    await new Promise(r => setTimeout(r, 30000));
    try {
      const p = await getRenderProgress({
        region: 'us-east-1',
        functionName: FUNCTION,
        bucketName: BUCKET,
        renderId,
        requestHandler,
      });
      const mins = ((Date.now() - startTs) / 60000).toFixed(1);
      console.log(`  [${mins}m] done=${p.done} fatal=${!!p.fatalErrorEncountered}`);
      if (p.done) {
        console.log(`  Output: ${p.outputFile}`);
        break;
      }
      if (p.fatalErrorEncountered) {
        console.log(`  FATAL: ${p.fatalErrorEncountered.slice(0,200)}`);
        process.exit(1);
      }
    } catch (e) {
      console.log(`  poll error (retrying): ${e.message.slice(0,80)}`);
    }
  }
}

writeFileSync('/home/hatch/workspace/history-video/sequential_render_ids.json', JSON.stringify(renderIds, null, 2));
console.log('\nAll 4 chunks done!');
console.log(JSON.stringify(renderIds.map(r => r.renderId)));
process.exit(0);
