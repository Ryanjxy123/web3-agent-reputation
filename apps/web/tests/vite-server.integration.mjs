import assert from 'node:assert/strict';
import { mkdtemp, mkdir, realpath, rm, writeFile } from 'node:fs/promises';
import { createServer as createHttpServer } from 'node:http';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createServer, normalizePath } from 'vite';

const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const configFile = fileURLToPath(new URL('../vite.config.ts', import.meta.url));

// This function runs unchanged in Node (no Origin) and in the browser (with Origin).
async function probeChannel({ url, messages, ids }) {
  const socket = new WebSocket(url, 'vite-hmr');
  const packets = [];
  try {
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('WebSocket probe timed out')), 5000);
      const pending = new Set(ids.map(id => id.replace('send', 'response')));
      let barrier = false;
      socket.addEventListener('error', () => {
        clearTimeout(timeout);
        reject(new Error('WebSocket probe failed'));
      });
      socket.addEventListener('open', () => {
        for (const message of messages) socket.send(message);
        socket.send(JSON.stringify({ type: 'custom', event: 'sec2:barrier', data: 'alive' }));
      });
      socket.addEventListener('message', event => {
        const packet = JSON.parse(String(event.data));
        packets.push(packet);
        if (packet.event === 'vite:invoke') pending.delete(packet.data.id);
        if (packet.event === 'sec2:barrier' && packet.data === 'alive') barrier = true;
        if (barrier && pending.size === 0) {
          clearTimeout(timeout);
          resolve();
        }
      });
    });
    return packets;
  } finally {
    socket.close();
  }
}

test('Vite resource access, malformed input, HMR and API proxy', { timeout: 30000 }, async t => {
  const temporaryParent = await realpath(tmpdir());
  const temporary = await mkdtemp(path.join(temporaryParent, 'reputation-vite-sec2-'));
  const root = path.join(temporary, 'web');
  const marker = 'SEC2_SYNTHETIC_DENIED_CONTENT';
  const files = [
    path.join(temporary, 'outside.txt'),
    path.join(root, '.env.synthetic'),
    path.join(root, 'synthetic.pem'),
  ];
  const requests = [];
  const api = createHttpServer(async (request, response) => {
    let body = '';
    for await (const chunk of request) body += chunk;
    requests.push(request.url);
    response.writeHead(request.url.startsWith('/health') ? 200 : request.method === 'POST' ? 202 : 409, {
      'content-type': 'application/json', 'x-sec2-response': 'controlled',
    });
    response.end(JSON.stringify({ method: request.method, url: request.url, body, header: request.headers['x-sec2-request'], database: 'ready' }));
  });
  const previousOrigin = process.env.PLATFORM_API_ORIGIN;
  let server;
  let browser;
  try {
    await mkdir(root);
    for (const file of files) await writeFile(file, marker);
    await writeFile(path.join(root, 'allowed.txt'), 'SEC2_NORMAL_RESOURCE');
    await writeFile(path.join(root, 'index.html'), '<p id="state">pending</p><script type="module" src="/main.js"></script>');
    await writeFile(path.join(root, 'value.js'), "export const value = 'before';\n");
    await writeFile(path.join(root, 'main.js'), `import { value } from './value.js';
document.querySelector('#state').textContent = value;
if (import.meta.hot) import.meta.hot.accept('./value.js', module => {
  document.querySelector('#state').textContent = module.value;
});\n`);
    await new Promise(resolve => api.listen(0, '127.0.0.1', resolve));
    process.env.PLATFORM_API_ORIGIN = `http://127.0.0.1:${api.address().port}`;
    server = await createServer({
      configFile, root, envDir: root, cacheDir: path.join(temporary, 'cache'), logLevel: 'silent',
      server: { host: '127.0.0.1', port: 0, fs: { allow: [root] } },
    });
    server.ws.on('sec2:barrier', (data, client) => client.send('sec2:barrier', data));
    await server.listen();
    const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
    const wsOrigin = origin.replace('http:', 'ws:');
    const read = resource => fetch(origin + resource, { signal: AbortSignal.timeout(5000) });

    await t.test('HTTP serves normal resources and rejects synthetic forbidden files', async () => {
      const allowed = await read('/allowed.txt?raw&import');
      const allowedBody = await allowed.text();
      assert.equal(allowed.status, 200, allowedBody);
      assert.match(allowedBody, /SEC2_NORMAL_RESOURCE/);
      for (const file of files) {
        for (const query of ['', '?raw&import', '?inline&import']) {
          const response = await read(encodeURI('/@fs/' + normalizePath(file)) + query);
          assert.equal(response.status, 403, `${path.basename(file)}${query}`);
          assert.ok(!(await response.text()).includes(marker));
        }
      }
      for (const resource of ['/@fs/%E0%A4%A?raw', '/@fs/%00?raw']) {
        const response = await read(resource);
        const body = await response.text();
        assert.ok(!body.includes(marker));
        if (response.status === 200) assert.match(body, /<p id="state">pending<\/p>/);
        else assert.ok(response.status >= 400);
      }
    });

    const calls = [];
    for (const file of [...files, path.join(root, 'allowed.txt')]) {
      const fsUrl = '/@fs/' + normalizePath(file);
      for (const url of [pathToFileURL(file).href + '?raw', fsUrl + '?raw', fsUrl + '?inline', '/@fs/' + encodeURIComponent(normalizePath(file)) + '?raw']) {
        calls.push({ name: 'fetchModule', data: [url, null, {}] });
      }
    }
    for (const url of [null, 7, {}, '%E0%A4%A', '/@fs/%00?raw']) calls.push({ name: 'fetchModule', data: [url, null, {}] });
    calls.push({ name: 'unknownMethod', data: [] });
    const ids = calls.map((_, index) => `send:sec2-${index}`);
    const messages = [
      '{invalid json', 'null', JSON.stringify({ type: 'unexpected', event: 'vite:invoke' }),
      ...calls.map((call, index) => JSON.stringify({ type: 'custom', event: 'vite:invoke', data: { id: ids[index], ...call } })),
    ];
    const checkPackets = packets => {
      assert.ok(packets.some(packet => packet.type === 'connected'));
      assert.ok(!JSON.stringify(packets).includes(marker));
      const replies = packets.filter(packet => packet.event === 'vite:invoke');
      assert.equal(replies.length, calls.length);
      for (let index = 0; index < calls.length; index += 1) {
        const reply = replies.find(packet => packet.data.id === ids[index].replace('send', 'response'));
        assert.ok(reply?.data.data.error, `missing rejection for ${ids[index]}`);
        assert.ok(!('result' in reply.data.data));
        if (calls[index].name === 'fetchModule') assert.match(reply.data.data.error.message, /fetchModule is disabled/);
      }
    };
    await t.test('WebSocket without Origin cannot invoke resource loading', async () => {
      checkPackets(await probeChannel({ url: wsOrigin, messages, ids }));
    });

    browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE });
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(origin);
    await page.waitForFunction(() => document.querySelector('#state')?.textContent === 'before');
    await t.test('browser WebSocket with valid HMR token also rejects resource loading', async () => {
      checkPackets(await page.evaluate(probeChannel, { url: `${wsOrigin}/?token=${server.config.webSocketToken}`, messages, ids }));
    });
    await t.test('normal HMR and GET/POST API proxies remain functional after abnormal input', async () => {
      const timeOrigin = await page.evaluate(() => performance.timeOrigin);
      await writeFile(path.join(root, 'value.js'), "export const value = 'after';\n");
      await page.waitForFunction(() => document.querySelector('#state')?.textContent === 'after');
      assert.equal(await page.evaluate(() => performance.timeOrigin), timeOrigin, 'HMR must update without reloading');
      assert.deepEqual(errors, []);
      const health = await read('/health/ready');
      assert.equal(health.status, 200);
      assert.equal((await health.json()).database, 'ready');
      const get = await fetch(origin + '/api/controlled?sample=1', { headers: { 'x-sec2-request': 'get' }, signal: AbortSignal.timeout(5000) });
      assert.equal(get.status, 409);
      assert.equal(get.headers.get('x-sec2-response'), 'controlled');
      assert.deepEqual(await get.json(), { method: 'GET', url: '/api/controlled?sample=1', body: '', header: 'get', database: 'ready' });
      const post = await fetch(origin + '/api/controlled', { method: 'POST', headers: { 'content-type': 'application/json', 'x-sec2-request': 'post' }, body: '{"synthetic":true}', signal: AbortSignal.timeout(5000) });
      assert.equal(post.status, 202);
      assert.equal(post.headers.get('x-sec2-response'), 'controlled');
      assert.deepEqual(await post.json(), { method: 'POST', url: '/api/controlled', body: '{"synthetic":true}', header: 'post', database: 'ready' });
      assert.deepEqual(requests, ['/health/ready', '/api/controlled?sample=1', '/api/controlled']);
    });
  } finally {
    if (previousOrigin === undefined) delete process.env.PLATFORM_API_ORIGIN;
    else process.env.PLATFORM_API_ORIGIN = previousOrigin;
    await browser?.close();
    await server?.close();
    await new Promise(resolve => api.close(resolve));
    assert.equal(path.dirname(temporary), temporaryParent);
    await rm(temporary, { recursive: true, force: true });
  }
});
