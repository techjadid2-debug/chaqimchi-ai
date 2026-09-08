/* O'rnatuvchi paneli: do'kon ro'yxati, kamera, chizma va topshiriqlar.
 *
 * Inline `<script>` dan chiqarildi — CSP `script-src` da
 * `'unsafe-inline'` yo'q.  `GeometryPanel` va `ZoneEditor` bu fayldan
 * OLDIN yuklanadi (`defer` tartibni saqlaydi).
 */
const KEY='enes_installer_token';let token=localStorage.getItem(KEY)||'';let account=null;let activeSite='';const $=id=>document.getElementById(id);const esc=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
async function api(path,options={}){const headers={...(options.headers||{})};if(token)headers.Authorization=`Bearer ${token}`;const response=await fetch(path,{...options,headers});const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.detail||'So‘rov bajarilmadi');return data}
function message(id,text,error=false){const box=$(id);box.textContent=text;box.className=`toast ${error?'toast-err':'toast-ok'}`;box.hidden=false}
$('loginForm').addEventListener('submit',async e=>{e.preventDefault();try{const data=await api('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('loginUsername').value,password:$('loginPassword').value})});if(data.account.role!=='installer')throw new Error('Bu login o‘rnatuvchi akkaunti emas');token=data.access_token;localStorage.setItem(KEY,token);await boot()}catch(err){message('loginMessage',err.message,true)}});
$('registerForm').addEventListener('submit',async e=>{e.preventDefault();try{const data=await api('/api/v1/auth/installer/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({full_name:$('regName').value,phone:$('regPhone').value,company:$('regCompany').value||null,username:$('regUsername').value,password:$('regPassword').value,consent:$('regConsent').checked})});token=data.access_token;localStorage.setItem(KEY,token);message('registerMessage',data.message);await boot()}catch(err){message('registerMessage',err.message,true)}});
async function boot(){if(!token)return;try{account=(await api('/api/v1/auth/me')).account;if(account.role!=='installer')throw new Error('O‘rnatuvchi akkaunti emas');$('auth').hidden=true;$('app').hidden=false;$('accountName').textContent=`${account.full_name} · ${account.username}`;if(account.status==='pending'){$('pending').hidden=false;$('jobsSection').hidden=true;return}if(account.status!=='active')throw new Error('Akkaunt bloklangan');await loadJobs()}catch(err){token='';localStorage.removeItem(KEY);$('auth').hidden=false;$('app').hidden=true;message('loginMessage',err.message,true)}}
async function loadJobs(){const data=await api('/api/v1/installer/assignments');$('jobs').innerHTML=data.assignments.length?data.assignments.map(a=>`<article class="job"><small>${esc(a.status)}</small><h3>${esc(a.site_name)}</h3><p class="muted">${esc(a.address||'Manzil kiritilmagan')}</p><p>Aloqa: <b>${esc(a.connection)}</b> · Kamera: <b>${a.cameras_active}/${a.cameras_expected||'?'}</b></p><button class="btn btn-primary" data-act="open-site" data-site="${esc(a.site_id)}">Ishni ochish</button></article>`).join(''):'<div class="pending">Hozircha obyekt biriktirilmagan.</div>'}
async function openSite(siteId){activeSite=siteId;try{const data=await api(`/api/v1/installer/sites/${siteId}/onboarding`);$('detailTitle').textContent=data.site.name;renderDetail(data);$('detailOverlay').hidden=false;setupGeometry()}catch(err){alert(err.message)}}
function renderDetail(data){
  $('detailBody').innerHTML=`<div class="progress"><i style="width:${data.percent}%"></i></div><p><b>${data.completed}/${data.total}</b> bosqich · ${data.percent}%</p><div class="step-list">${data.steps.map(s=>`<div class="step" data-done="${s.done?'1':'0'}">${s.done?'✓':'○'} ${esc(s.label)}</div>`).join('')}</div><h3>O‘rnatish buyrug‘i</h3>${data.install_command?`<code class="command">${esc(data.install_command)}</code><button class="btn" data-act="copy-command">Nusxalash</button>`:'<p class="muted">Faol pairing kodi yo‘q.</p>'}<button class="btn" data-act="new-pairing">Yangi pairing kodi</button><h3 style="margin-top:22px">Kameralarni sozlash</h3><div class="camera-builder"><h4>Hikvision / Dahua RTSP shabloni</h4><div class="camera-builder-grid"><div><label>Brend</label><select id="cameraBrand"><option value="hikvision">Hikvision / HiLook</option><option value="dahua">Dahua</option><option value="manual">Boshqa / qo‘lda</option></select></div><div><label>NVR IP</label><input id="cameraHost" inputmode="decimal" placeholder="192.168.1.64"></div><div><label>RTSP port</label><input id="cameraPort" inputmode="numeric" value="554"></div><div><label>NVR foydalanuvchi</label><input id="cameraUser" autocomplete="off" placeholder="enes-view"></div><div><label>NVR parol</label><input id="cameraPass" type="password" autocomplete="new-password"></div><div><label>NVR kanal</label><input id="cameraChannel" type="number" min="1" max="64" value="1"></div></div><button class="btn" type="button" data-act="build-rtsp">Substream RTSP yaratish</button><p class="muted">Alohida faqat live-view huquqidagi NVR akkauntidan foydalaning. Parol saqlangach forma tozalanadi.</p></div><form class="camera-form" data-act="save-camera"><div><label>ID</label><select id="cameraId">${[1,2,3,4].map(n=>`<option value="camera-0${n}">camera-0${n}</option>`).join('')}</select></div><div><label>Nomi</label><input id="cameraLabel" required placeholder="Asosiy kirish"></div><div><label>RTSP substream</label><input id="cameraRtsp" required placeholder="rtsp://user:password@NVR/..." type="password"></div><button class="btn btn-primary" type="submit">Saqlash</button></form><div id="cameraList"></div>
  <div class="geometry">
    <h3 style="margin-top:0">Chiziq va zona</h3>
    <p class="hint muted">Kadr ustida chizing. <b>Chiziq</b> — kirganlarni sanaydi (2 marta bosing). <b>Zona</b> — navbat, taqiqlangan joy yoki uzoq turishni kuzatadi (nuqta qo‘yib, oxirida ikki marta bosing). O‘ng tugma — o‘chiradi. Nuqtani sudrab ko‘chirish mumkin.<br>Yashil o‘q <b>ichkari</b> tomonni ko‘rsatadi — teskari bo‘lsa “Yo‘nalishni almashtirish”ni bosing.</p>
    <div class="row" style="gap:8px;margin-bottom:10px">
      <select id="geoCamera"></select>
      <select id="geoMode"><option value="line">Chiziq (kirish/chiqish)</option><option value="zone">Zona</option></select>
      <button class="btn" type="button" id="geoReload">Rasmni yangilash</button>
    </div>
    <canvas id="geoCanvas" width="640" height="360"></canvas>
    <div id="shapeList" class="shape-list"></div>
    <button class="btn btn-primary" type="button" id="geoSave">Chiziq va zonani saqlash</button>
    <span id="geoStatus" class="muted" style="margin-left:10px"></span>
  </div>
  <div class="row" style="margin-top:18px"><button class="btn" data-act="set-status" data-status="in_progress">Ish boshlandi</button><button class="btn" data-act="set-status" data-status="ready">Tekshiruvga tayyor</button><button class="btn btn-primary" data-act="set-status" data-status="completed">Yakunlandi</button></div>`;
  loadCameras();
}
function buildRtsp(silent=false){
  const brand=$('cameraBrand').value;
  if(brand==='manual'){if(!silent)$('cameraRtsp').focus();return $('cameraRtsp').value.trim()}
  const host=$('cameraHost').value.trim().replace(/^rtsps?:\/\//i,'').replace(/\/.*$/,'');
  const port=Number($('cameraPort').value||554),channel=Number($('cameraChannel').value||1);
  const user=$('cameraUser').value,pass=$('cameraPass').value;
  if(!host||!user||!pass||!Number.isInteger(port)||port<1||port>65535||!Number.isInteger(channel)||channel<1){if(!silent)alert('NVR IP, port, kanal, foydalanuvchi va parolni to‘liq kiriting');return ''}
  const auth=`${encodeURIComponent(user)}:${encodeURIComponent(pass)}@`;
  const path=brand==='hikvision'?`/Streaming/Channels/${channel}02`:`/cam/realmonitor?channel=${channel}&subtype=1`;
  $('cameraRtsp').value=`rtsp://${auth}${host}:${port}${path}`;
  return $('cameraRtsp').value;
}
async function loadCameras(){try{const data=await api(`/api/v1/installer/sites/${activeSite}/cameras`);$('cameraList').innerHTML=data.cameras.length?data.cameras.map(c=>`<div class="step"><b>${esc(c.camera_id)} · ${esc(c.label)}</b><br><small>${esc(c.probe_status)}${c.codec?` · ${esc(c.codec)} ${c.width}×${c.height}`:''}${c.preview_requested?' · rasm so‘raldi…':''}</small> <button class="btn btn-sm" data-act="ask-preview" data-camera="${esc(c.camera_id)}">Rasmni ko‘rish</button> <button class="btn btn-sm" data-act="delete-camera" data-camera="${esc(c.camera_id)}">O‘chirish</button>${c.has_preview?`<div class="preview"><img alt="${esc(c.label)}" src="/api/v1/installer/sites/${esc(activeSite)}/cameras/${esc(c.camera_id)}/preview?t=${Date.now()}"></div>`:''}</div>`).join(''):'<p class="muted">Kamera hali kiritilmagan.</p>'}catch(err){$('cameraList').textContent=err.message}}
// Rasm qurilmadan keyingi heartbeat'da keladi (~60 s). O'rnatuvchiga aniq
// vaqt aytiladi — "biroz kuting" desak u ishlamayapti deb o'ylaydi.
async function askPreview(cameraId){
  try{
    const data=await api(`/api/v1/installer/sites/${activeSite}/cameras/${cameraId}/preview`,{method:'POST'});
    await loadCameras();
    alert(`Rasm so‘raldi. Sotqin uni ${data.wait_sec} soniyagacha yuboradi — shu vaqtdan keyin “Yangilash” tugmasini bosing.`);
  }catch(err){alert(err.message)}
}
async function saveCamera(event){event.preventDefault();try{const generated=buildRtsp(true);const rtsp=generated||$('cameraRtsp').value.trim();if(!rtsp)throw new Error('RTSP substream manzilini kiriting yoki shablondan yarating');await api(`/api/v1/installer/sites/${activeSite}/cameras/${$('cameraId').value}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:$('cameraLabel').value,rtsp_url:rtsp,enabled:true})});$('cameraPass').value='';$('cameraRtsp').value='';await loadCameras();await openSite(activeSite)}catch(err){alert(err.message)}}
async function deleteCamera(id){if(!confirm('Kamera sozlamasi o‘chirilsinmi?'))return;try{await api(`/api/v1/installer/sites/${activeSite}/cameras/${id}`,{method:'DELETE'});await loadCameras()}catch(err){alert(err.message)}}
async function newPairing(){if(!confirm('Yangi bir martalik pairing kodi yaratilsinmi?'))return;try{const data=await api(`/api/v1/installer/sites/${activeSite}/pairing`,{method:'POST'});renderDetail(data.onboarding)}catch(err){alert(err.message)}}
async function setStatus(status){try{await api(`/api/v1/installer/sites/${activeSite}/status`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});await loadJobs();alert('Holat yangilandi')}catch(err){alert(err.message)}}
async function copyCommand(button){const code=button.previousElementSibling.textContent;await navigator.clipboard.writeText(code);button.textContent='Nusxalandi'}

// ── Chiziq va zona ─────────────────────────────────────────────────
// Mantiq `geometry-panel.js` da.  Ilgari bu yerda o'z nusxasi
// turardi va admin paneli ham o'shani ishlatardi; admin React'ga
// (`GeometryEditor.tsx`) ko'chgach bu fayl faqat o'rnatuvchiga
// qoldi — va aynan shuning uchun undan «javon» belgisi tushib
// qolgani uzoq vaqt sezilmadi.
function setupGeometry(){
  if(typeof GeometryPanel==='undefined')return;
  const base=`/api/v1/installer/sites/${activeSite}`;
  GeometryPanel.mount({
    els:{
      canvas:$('geoCanvas'),camera:$('geoCamera'),mode:$('geoMode'),
      status:$('geoStatus'),list:$('shapeList'),
      save:$('geoSave'),reload:$('geoReload'),
    },
    api,
    paths:{
      config:`${base}/config`,
      cameras:`${base}/cameras`,
      preview:id=>`${base}/cameras/${id}/preview`,
      askPreview:id=>`${base}/cameras/${id}/preview`,
    },
    onSaved:()=>openSite(activeSite),
  });
}

$('closeDetail').onclick=()=>{$('detailOverlay').hidden=true};$('refresh').onclick=loadJobs;$('logout').onclick=()=>{localStorage.removeItem(KEY);location.reload()};

// Ishlov beruvchilar BITTA joyda, hujjat darajasida: tugmalarning
// ko'pi `innerHTML` bilan qayta chiziladi va har chizishdan keyin
// qaytadan bog'lash kerak bo'lardi.  Naqsh `geometry-panel.js` dagi
// bilan bir xil.
document.addEventListener('click',event=>{
  const el=event.target.closest('[data-act]');
  if(!el||el.tagName==='FORM')return;
  const act=el.dataset.act;
  if(act==='open-site')openSite(el.dataset.site);
  else if(act==='copy-command')copyCommand(el);
  else if(act==='new-pairing')newPairing();
  else if(act==='build-rtsp')buildRtsp();
  else if(act==='set-status')setStatus(el.dataset.status);
  else if(act==='ask-preview')askPreview(el.dataset.camera);
  else if(act==='delete-camera')deleteCamera(el.dataset.camera);
});
document.addEventListener('submit',event=>{
  const form=event.target.closest('[data-act="save-camera"]');
  if(form)saveCamera(event);
});

boot();
