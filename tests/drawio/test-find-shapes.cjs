const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname,
  '../../plugins/drawio/skills/drawio/scripts/find-shapes.js'), 'utf8');

async function search(query, index, images) {
  const output = [];
  const requests = [];
  await vm.runInNewContext(script, {
    process: { argv: ['node', 'find-shapes.js', query], exit(code) { throw Error(`exit ${code}`); } },
    console: { log(line) { output.push(line); }, error(line) { throw Error(line); } },
    AbortSignal,
    async fetch(url) {
      requests.push(url);
      return { async json() { return requests.length === 1 ? index : { images }; } };
    },
  });
  return { output: output.join('\n'), requests };
}

test('matches all query words and resolves relative shape images', async () => {
  const result = await search('Azure SQL', [
    { tags: 'azure sql database', title: 'SQL', w: 40, h: 50,
      style: 'shape=image;image=img/lib/azure2/sql.svg;' },
    { tags: 'azure storage', title: 'Storage', w: 40, h: 50, style: 'shape=rect;' },
  ], []);
  assert.match(result.output, /SQL 40x50 .*image=https:\/\/app.diagrams.net\/img\/lib\/azure2\/sql.svg/);
  assert.doesNotMatch(result.output, /Storage/);
});

test('falls back to icon search and rejects unsafe image URLs', async () => {
  const result = await search('brand & logo', [], [
    { title: 'Brand', url: 'https://example.com/brand.svg' },
    { title: 'Unsafe', url: 'javascript:alert(1)' },
    { title: 'Injected', url: 'https://example.com/a;shape=rect' },
  ]);
  assert.match(result.requests[1], /q=brand%20%26%20logo$/);
  assert.match(result.output, /Brand 48x48/);
  assert.doesNotMatch(result.output, /Unsafe|Injected/);
});
