# 🏥 Plataforma Distribuida de Interoperabilidad Clínica

Sistema distribuido de historia clínica electrónica basado en **HL7 FHIR R4**, con un **Bus de Servicios de Salud (HSB)**, **Keycloak** para seguridad por roles, **auditoría encadenada por hash** y **cuatro vistas por rol**. Todo el sistema se levanta con un solo comando usando Docker Compose.

## 📋 Requisitos previos

- Docker y Docker Compose instalados.
- Python 3.11+ (solo si se ejecuta el bus fuera de Docker).

## 🚀 Instalación y despliegue

1. Clona el repositorio:
   ```bash
   git clone https://github.com/andresacosta15/parcial-historia-clinica
   cd parcial-historia-clinica
Levanta todos los servicios:

bash
docker compose up -d --build
Verifica que los contenedores estén corriendo:

bash
docker ps
Deberías ver: hapi-db, hapi-fhir, keycloak, bus y frontend.

Abre el frontend en el navegador:

text
http://localhost:3000
👥 Usuarios de prueba
Rol	Usuario	Contraseña
Paciente	paciente1	paciente123
Admisionista	admision1	admision123
Médico	medico1	medico123
Auditor	auditor1	auditor123
🔌 Endpoints principales
Método	Endpoint	Descripción	Rol requerido
GET	/health	Health check	Ninguno
POST	/ingest/hl7	Ingesta HL7 v2	Admisionista, Médico
POST	/ingest/csv	Ingesta CSV	Admisionista
GET	/patients	Lista pacientes	Admisionista, Médico, Auditor
GET	/patients/{id}/bundle	Bundle FHIR del paciente	Paciente (solo suyo), Médico, Auditor
POST	/diagnostico	Registra diagnóstico CIE-10	Médico
GET	/reporte	Reporte unificado con tablero	Auditor, Médico
GET	/audit/verify	Verifica integridad de auditoría	Auditor
GET	/metrics	Métricas Prometheus	Ninguno
🏗️ Arquitectura
text
┌─────────────────┐
│   Frontend      │
│  (localhost:3000)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌─────────────────┐
│   Keycloak      │◄─────┤   Bus (FastAPI) │
│  (localhost:8081)│      │  (localhost:8000)│
└─────────────────┘      └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │   HAPI FHIR     │
                         │  (localhost:8080)│
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │  PostgreSQL     │
                         │  (hapi-db)      │
                         └─────────────────┘
📁 Estructura del proyecto
text
parcial-historia-clinica/
├── bus/                    # Bus de Servicios de Salud (FastAPI)
├── frontend/               # Frontend con las 4 vistas por rol
├── keycloak/               # Configuración del realm
├── hapi-config/            # Configuración de HAPI FHIR
├── hapi-extra-classes/     # Módulo Flyway para PostgreSQL
├── docker-compose.yml      # Orquestación unificada
└── README.md
📝 Notas
Los datos son sintéticos. No se usan datos reales de pacientes.

La base de datos se borra si se ejecuta docker compose down -v. Para conservar datos, usa docker compose down sin -v.

El endpoint /metrics expone métricas en formato Prometheus para monitoreo.

📄 Licencia
Proyecto académico para el parcial final de la asignatura. Uso educativo.
