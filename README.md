# 🏥 Plataforma Distribuida de Interoperabilidad Clínica

Sistema distribuido de historia clínica electrónica basado en **HL7 FHIR R4**, con un **Bus de Servicios de Salud (HSB)**, **Keycloak** para seguridad por roles, **auditoría encadenada por hash** y **cuatro vistas por rol**. Todo el sistema se levanta con un solo comando usando Docker Compose.

## 🚀 Instalación y despliegue

```bash
# 1. Clonar el repositorio
git clone https://github.com/andresacosta15/parcial-historia-clinica.git
cd parcial-historia-clinica

# 2. Levantar todo el sistema (3 sedes, bus, keycloak, frontend)
docker compose up -d --build

# 3. Verificar que los 10 contenedores están arriba
docker compose ps

Frontend: http://localhost:3000

Keycloak: http://localhost:8081 (admin/admin)

Bus (API): http://localhost:8000/docs

👥 Usuarios de prueba
Rol	Usuario	Contraseña
Paciente	paciente1	paciente123
Admisionista	admision1	admision123
Médico	medico1	medico123
Auditor	auditor1	auditor123

Frontend (3000) → Bus (8000) → 3x HAPI FHIR (8082, 8083, 8084)
                        ↓
                    Redis (6379) ← cola de reintentos
                        ↓
                    Keycloak (8081)
                        
Sedes: Sincelejo, Cartagena, Corozal
Cada sede tiene su propio PostgreSQL (14) y HAPI FHIR (v5.5.2)

📋 Requisitos cumplidos
Requisito	Estado
RF1: HL7 v2 + CSV	✅
RF2: FHIR R4 (Patient, Encounter, Condition)	✅
RF3: HSB con idempotencia y enrutamiento	✅
RF4: 3 sedes distribuidas + consulta unificada	✅
RF5: Keycloak (4 roles) + auditoría hash	✅
RF6: 4 vistas por rol	✅
RNF: docker compose up + resiliencia	✅
📚 Documentación
Informe final: docs/INFORME.md

UML: docs/uml/

Capturas: docs/capturas/

🔌 Endpoints principales
Método	Endpoint	Rol requerido
POST	/ingest/hl7	Admisionista, Médico
POST	/ingest/csv	Admisionista
GET	/patients	Admisionista, Médico, Auditor
GET	/patients/{id}/bundle	Paciente (solo suyo), Médico, Auditor
POST	/diagnostico	Médico
GET	/reporte	Auditor, Médico
GET	/audit/verify	Auditor
GET	/sedes/estado	Público
GET	/metrics	Público

🧪 Pruebas rápidas
bash
# Verificar estado de las 3 sedes
curl http://localhost:8000/sedes/estado

# Verificar que las 3 FHIR responden
curl http://localhost:8082/fhir/metadata
curl http://localhost:8083/fhir/metadata
curl http://localhost:8084/fhir/metadata
🔐 Seguridad
Keycloak con 4 roles (paciente, admisionista, medico, auditor)

JWT validado contra JWKS de Keycloak

Auditoría encadenada por hash (auditchain) en SQLite

Idempotencia con Idempotency-Key para evitar duplicados

🎯 Resiliencia
Si una sede cae:

bash
docker compose stop hapi-fhir-cartagena
curl http://localhost:8000/sedes/estado
# {"sedes":{"sincelejo":"disponible","cartagena":"no disponible","corozal":"disponible"}}
La vista unificada sigue funcionando con las otras 2 sedes.

📄 Licencia
Proyecto académico para el parcial final de la asignatura. Uso educativo.



