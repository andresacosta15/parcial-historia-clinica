const KEYCLOAK_URL = "http://localhost:8081";
const REALM = "historia-clinica";
const CLIENT_ID = "frontend";
const BUS_URL = "http://localhost:8000";

let keycloak = new Keycloak({ url: KEYCLOAK_URL, realm: REALM, clientId: CLIENT_ID });
let userRoles = [];
let userToken = null;

// ========== INICIALIZACIÓN ==========
keycloak.init({ onLoad: 'check-sso' }).then(authenticated => {
  if (authenticated) {
    userToken = keycloak.token;
    userRoles = keycloak.realmAccess.roles;
    document.getElementById('login-section').style.display = 'none';
    document.getElementById('app-section').style.display = 'block';
    document.getElementById('user-info').style.display = 'flex';
    document.getElementById('username').textContent = keycloak.tokenParsed.preferred_username;
    document.getElementById('role-badge').textContent = userRoles[0].toUpperCase();
    mostrarVistaPorRol();
  }
}).catch(err => console.error('Error Keycloak:', err));

function login() { keycloak.login(); }
function logout() { keycloak.logout(); }

function mostrarVistaPorRol() {
  document.querySelectorAll('.vista').forEach(v => v.style.display = 'none');
  if (userRoles.includes('paciente')) document.getElementById('vista-paciente').style.display = 'block';
  else if (userRoles.includes('admisionista')) document.getElementById('vista-admisionista').style.display = 'block';
  else if (userRoles.includes('medico')) document.getElementById('vista-medico').style.display = 'block';
  else if (userRoles.includes('auditor')) document.getElementById('vista-reporte').style.display = 'block';
}

function toast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show ' + type;
  setTimeout(() => t.className = 'toast', 3000);
}

// ========== API HELPER ==========
async function apiCall(path, options = {}) {
  try {
    await keycloak.updateToken(30);
    userToken = keycloak.token;
  } catch (e) { console.error('Error refrescando token', e); }
  options.headers = options.headers || {};
  options.headers['Authorization'] = 'Bearer ' + userToken;
  if (!options.headers['Content-Type'] && options.method !== 'GET') {
    options.headers['Content-Type'] = 'application/json';
  }
  const resp = await fetch(BUS_URL + path, options);
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${err}`);
  }
  return resp.json();
}

// ========== RENDER HELPERS ==========
function renderPacientes(entries) {
  if (!entries || entries.length === 0) return '<p class="info">No hay pacientes</p>';
  let html = '<table class="data-table"><tr><th>Sede</th><th>Nombre</th><th>Documento</th><th>Género</th><th>Nacimiento</th></tr>';
  entries.forEach(e => {
    const p = e.resource;
    const nombre = p.name?.[0] ? `${p.name[0].family}, ${p.name[0].given?.join(' ') || ''}` : 'Sin nombre';
    const doc = p.identifier?.[0]?.value || '?';
    html += `<tr>
      <td>${e._sede ? `<span class="sede-badge sede-${e._sede}">${e._sede}</span>` : '?'}</td>
      <td>${nombre}</td>
      <td>${doc}</td>
      <td>${p.gender || '?'}</td>
      <td>${p.birthDate || '?'}</td>
    </tr>`;
  });
  html += '</table>';
  return html;
}

function renderHistoriaUnificada(data) {
  if (!data.datos || Object.keys(data.datos).length === 0) {
    return '<p class="info">No se encontraron datos del paciente en ninguna sede.</p>';
  }
  let html = `<div class="resumen-unificado">
    <p><strong>Sedes con datos:</strong> ${data.sedes_con_datos.join(', ')}</p>
    <p><strong>Sedes no disponibles:</strong> ${data.sedes_no_disponibles.length ? data.sedes_no_disponibles.join(', ') : 'ninguna'}</p>
  </div>`;
  for (const [sede, sedeData] of Object.entries(data.datos)) {
    html += `<div class="sede-card">
      <h3><span class="sede-badge sede-${sede}">${sede}</span></h3>`;
    for (const [recurso, valor] of Object.entries(sedeData)) {
      const total = valor.total || 0;
      html += `<p><strong>${recurso}:</strong> ${total} registros</p>`;
      if (valor.entry && valor.entry.length > 0) {
        html += '<ul class="recursos-list">';
        valor.entry.slice(0, 5).forEach(e => {
          const r = e.resource;
          if (r.resourceType === 'Patient') {
            html += `<li>👤 ${r.name?.[0]?.family}, ${r.name?.[0]?.given?.join(' ')}</li>`;
          } else if (r.resourceType === 'Encounter') {
            html += `<li>🏥 Encounter ${r.status}</li>`;
          } else if (r.resourceType === 'Condition') {
            html += `<li>🩺 ${r.code?.coding?.[0]?.display || 'Diagnóstico'}</li>`;
          }
        });
        html += '</ul>';
      }
    }
    html += '</div>';
  }
  return html;
}

// ========== VISTA PACIENTE ==========
async function cargarMiHistoria() {
  const username = keycloak.tokenParsed.preferred_username;
  const el = document.getElementById('historia-paciente');
  el.innerHTML = '<p class="loading">Cargando...</p>';
  try {
    const data = await apiCall(`/patients/${username}/bundle`);
    el.innerHTML = renderHistoriaUnificada(data);
  } catch (e) {
    el.innerHTML = `<p class="error">Error: ${e.message}</p>`;
  }
}

async function descargarBundle() {
  const username = keycloak.tokenParsed.preferred_username;
  try {
    const data = await apiCall(`/patients/${username}/bundle`);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/fhir+json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `bundle-${username}.json`; a.click();
    URL.revokeObjectURL(url);
    toast('Bundle descargado', 'success');
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function verAccesos() {
  const el = document.getElementById('accesos-paciente');
  el.innerHTML = '<p class="info">La auditoría completa es visible solo para el rol Auditor. Contacta al auditor para ver quién accedió a tu historia.</p>';
}

// ========== VISTA ADMISIONISTA ==========
async function buscarPaciente() {
  const doc = document.getElementById('buscar-doc').value.trim();
  const sede = document.getElementById('buscar-sede').value;
  const el = document.getElementById('resultado-busqueda');
  if (!doc) { toast('Ingresa un documento', 'error'); return; }
  el.innerHTML = '<p class="loading">Buscando...</p>';
  try {
    const headers = sede ? { 'X-Sede': sede } : {};
    const data = await apiCall('/patients', { headers });
    const entries = (data.entry || []).filter(e => {
      const id = e.resource.identifier?.[0]?.value;
      return id === doc;
    });
    if (entries.length === 0) {
      el.innerHTML = `<p class="info">No se encontró el paciente ${doc}</p>`;
      return;
    }
    el.innerHTML = renderPacientes(entries);
    if (entries.length > 1) {
      toast(`⚠️ ${entries.length} coincidencias — posible duplicado entre sedes`, 'warning');
    }
  } catch (e) {
    el.innerHTML = `<p class="error">Error: ${e.message}</p>`;
  }
}

async function registrarPaciente() {
  const doc = document.getElementById('reg-doc').value.trim();
  const nombre = document.getElementById('reg-nombre').value.trim();
  const apellido = document.getElementById('reg-apellido').value.trim();
  const sexo = document.getElementById('reg-sexo').value;
  const fecha = document.getElementById('reg-fecha').value.trim();
  const sede = document.getElementById('reg-sede').value;
  const el = document.getElementById('resultado-registro');
  if (!doc || !nombre) { toast('Documento y nombre son obligatorios', 'error'); return; }
  el.innerHTML = '<p class="loading">Registrando...</p>';
  const hl7 = `MSH|^~\\&|WEB|${sede.toUpperCase()}|HAPI|${sede.toUpperCase()}|20260101120000||ADT^A01|MSG${Date.now()}|P|2.5\rPID|1||${doc}^^^HOSP^MR||${apellido}^${nombre}||${fecha}|${sexo}\rPV1|1|I|${sede.toUpperCase()}^C1||||||||||||||||ENC${Date.now()}`;
  try {
    const data = await apiCall('/ingest/hl7', {
      method: 'POST',
      headers: { 'X-Sede': sede, 'Idempotency-Key': `reg-${doc}-${Date.now()}` },
      body: JSON.stringify({ message: hl7 })
    });
    el.innerHTML = `<p class="success">✅ Paciente registrado en <strong>${data.sede}</strong></p>`;
    toast('Paciente registrado', 'success');
  } catch (e) {
    el.innerHTML = `<p class="error">Error: ${e.message}</p>`;
  }
}

async function cargarEstadoSedes() {
  const el = document.getElementById('estado-sedes');
  el.innerHTML = '<p class="loading">Consultando...</p>';
  try {
    const data = await apiCall('/sedes/estado');
    let html = '<div class="sedes-grid">';
    for (const [sede, estado] of Object.entries(data.sedes)) {
      const disponible = estado === 'disponible';
      html += `<div class="sede-status ${disponible ? 'ok' : 'fail'}">
        <div class="sede-name">${sede.charAt(0).toUpperCase() + sede.slice(1)}</div>
        <div class="sede-indicator">${disponible ? '🟢' : '🔴'}</div>
        <div class="sede-estado">${estado}</div>
      </div>`;
    }
    html += '</div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<p class="error">Error: ${e.message}</p>`;
  }
}

// ========== VISTA MÉDICO ==========
async function cargarHistoriaUnificada() {
  const doc = document.getElementById('med-doc').value.trim();
  const el = document.getElementById('historia-unificada');
  if (!doc) { toast('Ingresa un documento', 'error'); return; }
  el.innerHTML = '<p class="loading">Cargando historia unificada...</p>';
  try {
    const data = await apiCall(`/patients/${doc}/bundle`);
    el.innerHTML = renderHistoriaUnificada(data);
  } catch (e) {
    el.innerHTML = `<p class="error">Error: ${e.message}</p>`;
  }
}

async function registrarDiagnostico() {
  const patientId = document.getElementById('diag-patient').value.trim();
  const code = document.getElementById('diag-code').value.trim();
  const desc = document.getElementById('diag-desc').value.trim();
  const sede = document.getElementById('diag-sede').value;
  const el = document.getElementById('resultado-diagnostico');
  if (!patientId || !code) { toast('Documento y código CIE-10 son obligatorios', 'error'); return; }
  el.innerHTML = '<p class="loading">Registrando...</p>';
  try {
    const data = await apiCall(
      `/diagnostico?patient_id=${encodeURIComponent(patientId)}&codigo_cie10=${encodeURIComponent(code)}&descripcion=${encodeURIComponent(desc)}`,
      { method: 'POST', headers: { 'X-Sede': sede } }
    );
    el.innerHTML = `<p class="success">✅ Diagnóstico registrado en <strong>${data.sede}</strong></p>`;
    toast('Diagnóstico registrado', 'success');
  } catch (e) {
    el.innerHTML = `<p class="error">Error: ${e.message}</p>`;
  }
}

// ========== VISTA REPORTE ==========
async function cargarReporte() {
  const el = document.getElementById('reporte-contenido');
  el.innerHTML = '<p class="loading">Generando reporte...</p>';
  try {
    const data = await apiCall('/reporte');
    let html = '<div class="sedes-grid">';
    for (const [sede, estado] of Object.entries(data.sedes)) {
      const disponible = estado === 'disponible';
      html += `<div class="sede-status ${disponible ? 'ok' : 'fail'}">
        <div class="sede-name">${sede.charAt(0).toUpperCase() + sede.slice(1)}</div>
        <div class="sede-indicator">${disponible ? '🟢' : '🔴'}</div>
        <div class="sede-estado">${estado}</div>
      </div>`;
    }
    html += '</div>';
    html += '<h3>Recursos por sede</h3>';
    html += '<table class="data-table"><tr><th>Sede</th><th>Patient</th><th>Encounter</th><th>Observation</th><th>Condition</th></tr>';
    for (const [sede, stats] of Object.entries(data.tablero_por_sede)) {
      html += `<tr>
        <td><span class="sede-badge sede-${sede}">${sede}</span></td>
        <td>${stats.Patient}</td>
        <td>${stats.Encounter}</td>
        <td>${stats.Observation}</td>
        <td>${stats.Condition}</td>
      </tr>`;
    }
    html += '</table>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<p class="error">Error: ${e.message}</p>`;
  }
}

async function verificarAuditoria() {
  const el = document.getElementById('auditoria-contenido');
  el.innerHTML = '<p class="loading">Verificando auditoría...</p>';
  try {
    const data = await apiCall('/audit/verify');
    el.innerHTML = `<div class="audit-result">
      <h3>🔐 Auditoría</h3>
      <p class="success">${data.audit_report}</p>
    </div>`;
  } catch (e) {
    el.innerHTML = `<p class="error">Error: ${e.message}</p>`;
  }
}
