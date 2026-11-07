// scripts/seed_mongo.js
// ============================================================
// DevForge AI — Seed de desarrollo para MongoDB — CICLO 2
//
// Crea: 3 usuarios, 1 proyecto con 3 miembros y 1 diagrama UML
// completo (clases, atributos, operaciones con parámetros, interfaz
// y 5 tipos de relación), con los MISMOS nombres de campos que los
// documentos Beanie (app/models/, Tandas 2-3).
//
// Ejecución (desde la raíz del repo, con mongosh instalado):
//   mongosh "mongodb://localhost:27017" --file scripts/seed_mongo.js
//   mongosh "mongodb://usuario:clave@host:27017" --file scripts/seed_mongo.js
//
// ¡OJO! Este seed hace dropDatabase() de la BD de DESARROLLO indicada
// en BD_DESTINO. NUNCA lo apuntes a devforge_prod_db ni a producción:
// está pensado para levantar el entorno local con datos de prueba.
//
// Nota: el índice único de usuarios.email NO se crea aquí: init_beanie
// lo crea solo al arrancar el backend (reemplazo de las migraciones).
// ============================================================

const BD_DESTINO = "devforge_db";      // misma MONGODB_DB del .env de desarrollo
const DROP = true;                     // true = borra la BD antes de sembrar

const db = db.getSiblingDB(BD_DESTINO);

if (DROP) {
  print(`Eliminando la BD '${BD_DESTINO}' (DROP=true)...`);
  db.dropDatabase();
}

// ------------------------------------------------------------
// Utilidades
// ------------------------------------------------------------
// Los ids de los elementos embebidos del Diagrama (ClaseUML, AtributoUML,
// OperacionUML, ParametroOperacionUML, InterfazUML, RelacionUML) son uuid
// HEX de 32 caracteres generados por la app (uuid4().hex, Tanda 3).
// Aquí se generan igual, en variables, para que las relaciones apunten
// a los mismos ids.
function uuidHex() {
  let s = "";
  for (let i = 0; i < 32; i++) s += Math.floor(Math.random() * 16).toString(16);
  return s;
}

function ahora() { return new Date(); }

// Hash bcrypt REAL de la contraseña "devforge123" (rondas 12).
// Verificado con bcrypt.checkpw. NO es un hash inventado.
// En producción los usuarios se crean por POST /api/v1/auth/registro.
const HASH_DEVFORGE123 = "$2b$12$L6K3zxS0QyWDuSygyxpxPupres/HeItBOxaJcFZLZdW9Xs2oH89WK";

// ------------------------------------------------------------
// 1) Usuarios (colección "usuarios" — app/models/usuario.py)
//    campos: nombre_completo, email (único), password_hash,
//            rol (ADMIN|LIDER|DESARROLLADOR), activo, created_at
// ------------------------------------------------------------
const ts = ahora();
const rAdmin = db.usuarios.insertOne({
  nombre_completo: "Ana Administradora",
  email: "admin@devforge.ai",
  password_hash: HASH_DEVFORGE123,
  rol: "ADMIN",
  activo: true,
  created_at: ts,
});
const rLider = db.usuarios.insertOne({
  nombre_completo: "Bruno Líder",
  email: "lider@devforge.ai",
  password_hash: HASH_DEVFORGE123,
  rol: "LIDER",
  activo: true,
  created_at: ts,
});
const rDev = db.usuarios.insertOne({
  nombre_completo: "Carla Desarrolladora",
  email: "dev@devforge.ai",
  password_hash: HASH_DEVFORGE123,
  rol: "DESARROLLADOR",
  activo: true,
  created_at: ts,
});

const idAdmin = rAdmin.insertedId;
const idLider = rLider.insertedId;
const idDev = rDev.insertedId;

// ------------------------------------------------------------
// 2) Proyecto (colección "proyectos" — app/models/proyecto.py)
//    campos: nombre, descripcion, id_propietario, estado
//            (ACTIVO|ARCHIVADO), miembros[] EMBEBIDOS
//            {id_usuario, rol_en_proyecto (PROPIETARIO|EDITOR|LECTOR),
//            joined_at}, created_at, updated_at
// ------------------------------------------------------------
const rProyecto = db.proyectos.insertOne({
  nombre: "Plataforma de Matrículas",
  descripcion: "Proyecto demo del seed: sistema de matrículas universitarias.",
  id_propietario: idLider,
  estado: "ACTIVO",
  miembros: [
    { id_usuario: idLider, rol_en_proyecto: "PROPIETARIO", joined_at: ts },
    { id_usuario: idDev,   rol_en_proyecto: "EDITOR",      joined_at: ts },
    { id_usuario: idAdmin, rol_en_proyecto: "LECTOR",      joined_at: ts },
  ],
  created_at: ts,
  updated_at: ts,
});
const idProyecto = rProyecto.insertedId;

// ------------------------------------------------------------
// 3) Diagrama (colección "diagramas" — app/models/diagrama.py)
//    Todo EMBEBIDO (lectura atómica del lienzo en 1 consulta):
//      clases[]  {id uuid, nombre, es_abstracta, estereotipo, pos_x,
//                 pos_y, id_creador, created_at, updated_at,
//                 atributos[] {id, nombre, tipo_dato, visibilidad
//                 (+|-|#|~), es_estatico, valor_defecto, orden},
//                 operaciones[] {id, nombre, tipo_retorno, visibilidad,
//                 es_estatico, orden, parametros[] {id, nombre,
//                 tipo_dato, orden}}}
//      interfaces[] {id, nombre, pos_x, pos_y, operaciones[] {id,
//                 nombre, tipo_retorno}}
//      relaciones[] {id, id_clase_origen (uuid str), id_clase_destino,
//                 tipo_relacion (ASOCIACION|AGREGACION|COMPOSICION|
//                 DEPENDENCIA|GENERALIZACION|REALIZACION),
//                 multiplicidad_origen/destino, nombre_asociacion,
//                 rol_origen, rol_destino}
//    Cabecera: id_proyecto, nombre, version_uml, numero_version,
//              id_creador, created_at, updated_at
// ------------------------------------------------------------

// --- ids de clases (uuid hex, compartidos con las relaciones) ---
const idPersona = uuidHex();
const idEstudiante = uuidHex();
const idCurso = uuidHex();
const idMatri = uuidHex();

const idAttrNombre = uuidHex();
const idAttrEmail = uuidHex();
const idAttrFecha = uuidHex();
const idAttrNota = uuidHex();

const idOpRegistrarse = uuidHex();
const idOpParamFechas = uuidHex();
const idOpInscribirse = uuidHex();
const idOpParamCurso = uuidHex();
const idOpValidar = uuidHex();

const idInterfaz = uuidHex();
const idOpInterfaz = uuidHex();

const tsDiag = ahora();

const diagrama = {
  _id: ObjectId(),
  id_proyecto: idProyecto,
  nombre: "Diagrama de Clases — Matrículas",
  version_uml: "2.5.1",
  numero_version: 1,
  id_creador: idLider,
  created_at: tsDiag,
  updated_at: tsDiag,

  clases: [
    {
      id: idPersona,
      nombre: "Persona",
      es_abstracta: true,
      estereotipo: null,
      pos_x: 40.0, pos_y: 40.0,
      id_creador: idLider,
      created_at: tsDiag, updated_at: tsDiag,
      atributos: [
        { id: idAttrNombre, nombre: "nombre",  tipo_dato: "String",   visibilidad: "-", es_estatico: false, valor_defecto: null, orden: 0 },
        { id: idAttrEmail,  nombre: "email",   tipo_dato: "String",   visibilidad: "-", es_estatico: false, valor_defecto: null, orden: 1 },
      ],
      operaciones: [
        { id: idOpRegistrarse, nombre: "registrarse", tipo_retorno: "void", visibilidad: "+", es_estatico: false, orden: 0,
          parametros: [
            { id: idOpParamFechas, nombre: "fecha", tipo_dato: "DateTime", orden: 0 },
          ] },
      ],
    },
    {
      id: idEstudiante,
      nombre: "Estudiante",
      es_abstracta: false,
      estereotipo: null,
      pos_x: 40.0, pos_y: 240.0,
      id_creador: idLider,
      created_at: tsDiag, updated_at: tsDiag,
      atributos: [
        { id: idAttrFecha, nombre: "fechaIngreso", tipo_dato: "DateTime", visibilidad: "-", es_estatico: false, valor_defecto: null, orden: 0 },
      ],
      operaciones: [
        { id: idOpInscribirse, nombre: "inscribirse", tipo_retorno: "boolean", visibilidad: "+", es_estatico: false, orden: 0,
          parametros: [
            { id: idOpParamCurso, nombre: "curso", tipo_dato: "Curso", orden: 0 },
          ] },
      ],
    },
    {
      id: idCurso,
      nombre: "Curso",
      es_abstracta: false,
      estereotipo: null,
      pos_x: 320.0, pos_y: 240.0,
      id_creador: idDev,
      created_at: tsDiag, updated_at: tsDiag,
      atributos: [
        { id: idAttrNota, nombre: "creditos", tipo_dato: "int", visibilidad: "-", es_estatico: false, valor_defecto: "0", orden: 0 },
      ],
      operaciones: [
        { id: idOpValidar, nombre: "validarCupo", tipo_retorno: "boolean", visibilidad: "+", es_estatico: false, orden: 0, parametros: [] },
      ],
    },
  ],

  interfaces: [
    {
      id: idInterfaz,
      nombre: "Serializable",
      pos_x: 320.0, pos_y: 40.0,
      operaciones: [
        { id: idOpInterfaz, nombre: "serializar", tipo_retorno: "String" },
      ],
    },
  ],

  relaciones: [
    { // GENERALIZACION: hijo → padre (Estudiante ES UNA Persona)
      id: uuidHex(),
      id_clase_origen: idEstudiante, id_clase_destino: idPersona,
      tipo_relacion: "GENERALIZACION",
      multiplicidad_origen: null, multiplicidad_destino: null,
      nombre_asociacion: null, rol_origen: null, rol_destino: null,
    },
    { // COMPOSICION 1 — 0..* con nombre y roles (convención del lienzo)
      id: uuidHex(),
      id_clase_origen: idEstudiante, id_clase_destino: idCurso,
      tipo_relacion: "COMPOSICION",
      multiplicidad_origen: "1", multiplicidad_destino: "0..*",
      nombre_asociacion: "inscripciones", rol_origen: "estudiante", rol_destino: "curso",
    },
    { // AGREGACION
      id: uuidHex(),
      id_clase_origen: idCurso, id_clase_destino: idPersona,
      tipo_relacion: "AGREGACION",
      multiplicidad_origen: "0..*", multiplicidad_destino: "1..*",
      nombre_asociacion: null, rol_origen: null, rol_destino: null,
    },
    { // DEPENDENCIA (punteada)
      id: uuidHex(),
      id_clase_origen: idEstudiante, id_clase_destino: idMatri,
      tipo_relacion: "DEPENDENCIA",
      multiplicidad_origen: null, multiplicidad_destino: null,
      nombre_asociacion: null, rol_origen: null, rol_destino: null,
    },
    { // ASOCIACION simple
      id: uuidHex(),
      id_clase_origen: idPersona, id_clase_destino: idCurso,
      tipo_relacion: "ASOCIACION",
      multiplicidad_origen: "1", multiplicidad_destino: "0..*",
      nombre_asociacion: "dicta", rol_origen: null, rol_destino: null,
    },
  ],
};

// La clase "Matricula" referenciada por la DEPENDENCIA:
diagrama.clases.push({
  id: idMatri,
  nombre: "Matricula",
  es_abstracta: false,
  estereotipo: null,
  pos_x: 320.0, pos_y: 440.0,
  id_creador: idDev,
  created_at: tsDiag, updated_at: tsDiag,
  atributos: [],
  operaciones: [],
});

const rDiag = db.diagramas.insertOne(diagrama);

// ------------------------------------------------------------
// Resumen
// ------------------------------------------------------------
print("");
print("============================================================");
print(`Seed completado en la BD '${BD_DESTINO}':`);
print(`  usuarios:  ${db.usuarios.countDocuments()}  (contraseña de todos: devforge123)`);
print(`  proyectos: ${db.proyectos.countDocuments()}`);
print(`  diagramas: ${db.diagramas.countDocuments()}  (clases=${diagrama.clases.length}, interfaces=${diagrama.interfaces.length}, relaciones=${diagrama.relaciones.length}, _id=${rDiag.insertedId})`);
print("");
print("Los índices (email único, id_proyecto+id_diagrama, etc.) los crea");
print("init_beanie al arrancar el backend — no hace falta crearlos aquí.");
print("============================================================");
