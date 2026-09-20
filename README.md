# DevForge AI — Backend (Capa 1)

Backend de la plataforma CASE colaborativa **DevForge AI**: usuarios,
proyectos, modelado UML colaborativo en tiempo real, trazabilidad,
generación automática de backend Spring Boot, IA asistente (voz/texto/visión)
y sincronización offline.

> **Nota:** este backend **no es** el que se genera automáticamente a partir
> del diagrama de clases (ese es Spring Boot, producido por
> `app/code_generator/`). Este es el backend fijo de la plataforma.

---

## Stack

| Capa | Tecnología |
|---|---|
| Framework web | FastAPI (async) |
| Lenguaje | Python 3.10.10 |
| Base de datos | PostgreSQL |
| ORM | SQLAlchemy 2.x async + asyncpg |
| Migraciones | Alembic |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Tiempo real | WebSocket nativo (Starlette) |
| IA de visión | OpenCV + pytesseract |
| Plantillas | Jinja2 |
| Servidor (prod) | Gunicorn + UvicornWorker detrás de Nginx |

---

## Estructura

devforge-backend/
├── app/
│ ├── main.py # Entrada FastAPI
│ ├── config.py # Settings (Pydantic v2)
│ ├── database.py # Engine async, Base, get_db
│ ├── core/ # Seguridad, dependencias, excepciones
│ ├── models/ # 25 tablas ORM
│ ├── schemas/ # Esquemas Pydantic
│ ├── repositories/ # Acceso a datos (solo flush)
│ ├── services/ # Lógica de negocio (con commit)
│ ├── api/v1/ # 13 routers REST
│ ├── websocket/ # Colaboración en tiempo real
│ ├── code_generator/ # Motor Spring Boot
│ ├── ai_vision/ # Reconocimiento de bocetos
│ └── utils/ # XMI, validadores
├── alembic/ # Migraciones
├── generated_projects/ # Salidas del generador
├── tests/ # Tests
├── gunicorn.conf.py # Config Gunicorn prod
├── nginx/ # Config Nginx prod
├── requirements.txt
├── .env.example
├── .env.produccion
└── README.md


---

## Requisitos del sistema

- **Python 3.10+**
- **PostgreSQL 14+**
- **Tesseract OCR** (para reconocimiento de bocetos):
  ```bash
  sudo apt install tesseract-ocr tesseract-ocr-spa