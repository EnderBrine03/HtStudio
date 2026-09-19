/* HtStudio (tarayıcı) tarafında EXE derleme.
 * Gerekli: JSZip  (https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js)
 *
 *   const stub  = await (await fetch(STUB_URL)).arrayBuffer();   // HtStudioRuntime.exe
 *   const blob  = await buildExe(stub, {
 *                   'app/index.html': htmlString,
 *                   'app/style.css' : cssString,
 *                   'app/logo.png'  : uint8Array
 *                 }, {
 *                   id: 'com.kullanici.uygulamam', name: 'Uygulamam', version: '1.0.0',
 *                   target: { type: 'html', path: 'app/index.html' },
 *                   gui: { shape: 'horizontal', accent: '#3b6bff',
 *                          background: { color: '#0d0d1a', image: 'app/bg.jpg' } }
 *                 });
 *   // blob'u indir: a.href = URL.createObjectURL(blob); a.download = 'Uygulamam.exe'; a.click();
 */
async function buildExe(stubBuffer, files, config) {
  const zip = new JSZip();
  zip.file('launcher.json', JSON.stringify(config, null, 2));
  for (const [p, data] of Object.entries(files)) zip.file(p, data);
  const z = await zip.generateAsync({ type: 'uint8array', compression: 'DEFLATE' });

  const footer = new Uint8Array(12);
  footer.set(new TextEncoder().encode('HTSPACK1'), 0);
  new DataView(footer.buffer).setUint32(8, z.length, true);

  return new Blob([stubBuffer, z, footer], { type: 'application/vnd.microsoft.portable-executable' });
}
