const out = document.getElementById('out');
const show = (x) => { out.textContent = typeof x === 'string' ? x : JSON.stringify(x, null, 2); };
const fail = (e) => { out.textContent = 'Hata: ' + (e && e.message ? e.message : e); };
const $ = (id) => document.getElementById(id);

if (!window.htstudio) {
  show('window.htstudio bulunamadı. Bu sayfayı HtStudio Launcher içinde aç.');
}

$('save').onclick = () =>
  htstudio.fs.writeText('notlar/not.txt', $('note').value).then((n) => show(n + ' bayt kaydedildi.')).catch(fail);

$('load').onclick = () =>
  htstudio.fs.readText('notlar/not.txt').then((t) => { $('note').value = t; show('Yüklendi.'); }).catch(fail);

$('folder').onclick = async () => {
  try {
    const dir = await htstudio.fs.pickFolder();            // seçmek = o klasöre izin vermek
    if (!dir) return show('İptal edildi.');
    const items = await htstudio.fs.list(dir);
    $('files').innerHTML = '';
    items.slice(0, 50).forEach((f) => {
      const li = document.createElement('li');
      li.textContent = (f.isDir ? '[klasör] ' : '') + f.name;
      $('files').appendChild(li);
    });
    show(dir + ' içinde ' + items.length + ' öğe var.');
  } catch (e) { fail(e); }
};

$('copy').onclick = () => htstudio.clipboard.writeText('HtStudio ile kopyalandı').then(() => show('Panoya kopyalandı.')).catch(fail);
$('notify').onclick = () => htstudio.notify('HtStudio', 'Merhaba!').then((ok) => show(ok ? 'Bildirim gönderildi.' : 'Bildirim kullanılamıyor.')).catch(fail);
$('info').onclick = () => htstudio.info().then(show).catch(fail);

$('geo').onclick = () =>
  navigator.geolocation.getCurrentPosition(
    (p) => show({ enlem: p.coords.latitude, boylam: p.coords.longitude }),
    (e) => fail(e.message));

$('cam').onclick = async () => {
  try {
    const s = await navigator.mediaDevices.getUserMedia({ video: true });
    $('video').srcObject = s;
    $('video').hidden = false;
    show('Kamera açık.');
  } catch (e) { fail(e); }
};
