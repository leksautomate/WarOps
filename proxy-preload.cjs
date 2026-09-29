// Preload via NODE_OPTIONS=--require /home/hatch/workspace/history-video/proxy-preload.cjs
// Routes ALL Node HTTP(S) through the egress proxy (needed: AWS SDK v3
// ignores proxy env vars and its TLS handshake dies on the transparent proxy).
const { bootstrap } = require('global-agent');
bootstrap();
