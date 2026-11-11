const KEYCLOAK_URL = "http://localhost:8081";
const REALM = "historia-clinica";
const CLIENT_ID = "frontend";
const BUS_URL = "http://localhost:8000";

let keycloak = new Keycloak({
  url: KEYCLOAK_URL,
  realm: REALM,
  clientId: CLIENT_ID
});

let userRoles = [];
let userToken = null;

// Una sola inicialización
keycloak.init({ onLoad: 'check-sso' }).then(authenticated => {
  if (authenticated) {
    userToken = keycloak.token;
    userRoles = keycloak.realmAccess.roles;
    document.getElementById('login-section').style.display = 'none';
    document.getElementById('app-section').style.display = 'block';
    document.getElementById('user-info').style.display = 'flex';
    document.getElementById('username').textContent = keycloak.tokenParsed.preferred_username + ' (' + userRoles.join(', ') + ')';
    mostrarVistaPorRol();
  }
}).catch(err => {
  console.error('Error de inicialización de Keycloak', err);
});

function login() {
  keycloak.login();
}

function logout() {
  keycloak.logout();
}

function mostrarVistaPorRol() {
  document.querySelectorAll('.vista').forEach(v => v.style.display = 'none');
  if (userRoles.includes('paciente')) {
    document.getElementById('vista-paciente').style.display = 'block';
  } else if (userRoles.includes('admisionista')) {
    document.getElementById('vista-admisionista').style.display = 'block';
  } else if (userRoles.includes('medico')) {
    document.getElementById('vista-medico').style.display = 'block';
  } else if (userRoles.includes('auditor')) {
    document.getElementById('vista-reporte').style.display = 'block';
  }
}

async function apiCall(path, options = {}) {
  // Refrescar token si es necesario
  try {
    await keycloak.updateToken(30);
    userToken = keycloak.token;
  } catch (e) {
    console.error('Error refrescando token', e);
  }
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

async function cargarMiHistoria() {
  const username = keycloak.tokenParsed.preferred_username;
  try {
    const data = await apiCall(`/patients/${username}/bundle`);
    document.getElementById('historia-paciente').innerHTML =
      '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
  } catch (e) {
    document.getElementById('historia-paciente').textContent = 'Error: ' + e.message;
  }
}

async function descargarBundle() {
  const username = keycloak.tokenParsed.preferred_username;
  try {
    const data = await apiCall(`/patients/${username}/bundle`);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/fhir+json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bundle-${username}.json`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function listarPacientes() {
  try {
    const data = await apiCall('/patients');
    const container = document.getElementById('lista-pacientes') || document.getElementById('lista-pacientes-medico');
    const entries = data.entry || [];
    let html = '<h3>Pacientes (' + (data.total || 0) + ')</h3><ul>';
    entries.forEach(e => {
      const p = e.resource;
      const nombre = p.name ? (p.name[0].family + ', ' + p.name[0].given.join(' ')) : 'Sin nombre';
      const doc = p.identifier ? p.identifier[0].value : 'Sin documento';
      html += `<li><strong>${nombre}</strong> - Documento: ${doc} (ID: ${p.id})</li>`;
    });
    html += '</ul>';
    container.innerHTML = html;
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function registrarDiagnostico() {
  const patientId = document.getElementById('diag-patient').value;
  const code = document.getElementById('diag-code').value;
  const desc = document.getElementById('diag-desc').value;
  try {
    const data = await apiCall(`/diagnostico?patient_id=${encodeURIComponent(patientId)}&codigo_cie10=${encodeURIComponent(code)}&descripcion=${encodeURIComponent(desc)}`, { method: 'POST' });
    document.getElementById('resultado-diagnostico').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
  } catch (e) {
    document.getElementById('resultado-diagnostico').textContent = 'Error: ' + e.message;
  }
}

async function cargarReporte() {
  try {
    const data = await apiCall('/reporte');
    document.getElementById('reporte-contenido').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
  } catch (e) {
    document.getElementById('reporte-contenido').textContent = 'Error: ' + e.message;
  }
}
